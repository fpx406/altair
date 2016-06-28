"""
Utility routines
"""
import re
import warnings

import pandas as pd
import numpy as np


TYPECODE_MAP = {'ordinal': 'O',
                'nominal': 'N',
                'quantitative': 'Q',
                'temporal': 'T'}

INV_TYPECODE_MAP = {v:k for k,v in TYPECODE_MAP.items()}

TYPE_ABBR = TYPECODE_MAP.values()


def parse_shorthand(shorthand, valid_fields=None):
    """
    Parse the shorthand expression for aggregation, field, and type.

    These are of the form:

    - "col_name"
    - "col_name:O"
    - "average(col_name)"
    - "average(col_name):O"

    Parameters
    ----------
    shorthand: str
        Shorthand string
    valid_names : list (optional)
        An optional list of valid field names

    Returns
    -------
    D : dict
        Dictionary containing the field, aggregate, and typecode
    """
    if not shorthand:
        return {}

    from ..schema import AggregateOp
    valid_aggregates = AggregateOp().values
    valid_typecodes = list(TYPECODE_MAP) + list(INV_TYPECODE_MAP)

    # build regular expressions
    units = dict(field='(?P<field>.*)',
                 type='(?P<type>{0})'.format('|'.join(valid_typecodes)),
                 aggregate='(?P<aggregate>{0})'.format('|'.join(valid_aggregates)))
    patterns = [r'{field}',
                r'{field}:{type}',
                r'{aggregate}\({field}\)',
                r'{aggregate}\({field}\):{type}']
    regexps = [re.compile('\A' + p.format(**units) + '\Z', re.DOTALL)
               for p in patterns]

    matches = [exp.match(shorthand).groupdict() for exp in regexps
               if exp.match(shorthand)]
    if valid_fields is None:
        # Return last (i.e. most complex) valid match
        match_to_return = matches[-1]
    else:
        # return the simplest match which is a valid column name
        for match in matches:
            if match['field'] in valid_fields:
                match_to_return = match
                break
        else: # nobreak
            raise ValueError('No matching field for shorthand: '
                             '{0}'.format(matches[0]))

    # Use short form of the type expression
    typ = match_to_return.get('type', None)
    if typ:
        match_to_return['type'] = TYPECODE_MAP.get(typ, typ)
    return match_to_return


def construct_shorthand(field=None, aggregate=None, type=None):
    if field is None:
        return ''

    sh = field

    if aggregate is not None:
        sh = '{0}({1})'.format(aggregate, sh)

    if type is not None:
        type = TYPECODE_MAP.get(type, type)
        if type not in TYPE_ABBR:
            raise ValueError('Unrecognized Type: {0}'.format(type))
        sh = '{0}:{1}'.format(sh, type)

    return sh


def infer_vegalite_type(data, name=None):
    """
    From an array-like input, infer the correct vega typecode
    ('O', 'N', 'Q', or 'T')

    Parameters
    ----------
    data: Numpy array or Pandas Series
    field: str column name
    """
    # See if we can read the type from the name
    if name is not None:
        parsed = parse_shorthand(field)
        if parsed.get('type'):
            return parsed['type']

    # Otherwise, infer based on the dtype of the input
    typ = pd.lib.infer_dtype(data)

    # TODO: Once this returns 'O', please update test_select_x and test_select_y in test_api.py

    if typ in ['floating', 'mixed-integer-float', 'integer',
               'mixed-integer', 'complex']:
        typecode = 'quantitative'
    elif typ in ['string', 'bytes', 'categorical', 'boolean', 'mixed', 'unicode']:
        typecode = 'nominal'
    elif typ in ['datetime', 'datetime64', 'timedelta',
                 'timedelta64', 'date', 'time', 'period']:
        typecode = 'temporal'
    else:
        warnings.warn("I don't know how to infer vegalite type from '{0}'.  "
                      "Defaulting to nominal.".format(typ))
        typecode = 'nominal'

    return TYPECODE_MAP[typecode]


def sanitize_dataframe(df):
    """Sanitize a DataFrame to prepare it for serialization.

    * Make a copy
    * Raise ValueError if it has a hierarchical index.
    * Convert categoricals to strings.
    * Convert np.int dtypes to Python int objects
    * Convert floats to objects and replace NaNs by None.
    * Convert DateTime dtypes into appropriate string representations
    """
    df = df.copy()

    if isinstance(df.index, pd.core.index.MultiIndex):
        raise ValueError('Hierarchical indices not supported')
    if isinstance(df.columns, pd.core.index.MultiIndex):
        raise ValueError('Hierarchical indices not supported')

    for col_name, dtype in df.dtypes.iteritems():
        if str(dtype) == 'category':
            # XXXX: work around bug in to_json for categorical types
            # https://github.com/pydata/pandas/issues/10778
            df[col_name] = df[col_name].astype(str)
        elif np.issubdtype(dtype, np.integer):
            # convert integers to objects; np.int is not JSON serializable
            df[col_name] = df[col_name].astype(object)
        elif np.issubdtype(dtype, np.floating):
            # For floats, convert nan->None: np.float is not JSON serializable
            col = df[col_name].astype(object)
            df[col_name] = col.where(col.notnull(), None)
        elif str(dtype).startswith('datetime'):
            # Convert datetimes to strings
            # astype(str) will choose the appropriate resolution
            df[col_name] = df[col_name].astype(str).replace('NaT', '')
    return df
