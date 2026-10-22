import re
from datetime import datetime

def t_trim(v):
    return v.strip() if isinstance(v, str) else v

def t_upper(v):
    return v.upper() if isinstance(v, str) else v

def t_lower(v):
    return v.lower() if isinstance(v, str) else v

def t_digits_only(v):
    return re.sub('[^0-9]', '', str(v)) or None

def t_regex_extract(v, pattern, group=1):
    m = re.search(pattern, str(v))
    return m.group(group) if m else None

def t_date_parse(v, formats):
    for f in formats:
        try:
            return datetime.strptime(str(v).strip(), f).date().isoformat()
        except ValueError:
            pass
    return None

def t_split(v, sep, index=0):
    parts = str(v).split(sep)
    return parts[index].strip() if len(parts) > index else None

def t_map(v, table, default=None):
    return table.get(str(v).strip().upper(), default)   # khoá của table viết HOA

def t_null_if(v, values):
    return None if str(v).strip().upper() in {x.upper() for x in values} else v

def t_constant(v, value):
    return value

TRANSFORMS = {n[2:]: f for n, f in list(globals().items()) if n.startswith('t_')}