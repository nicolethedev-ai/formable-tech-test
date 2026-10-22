import re, yaml
from datetime import date

ONT = yaml.safe_load(open('ontology/firmable_ontology.yaml', encoding='utf-8'))
ABN_W = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]

def valid_abn(s):
    if not re.fullmatch('[0-9]{11}', s or ''):
        return False
    d = [int(c) for c in s]
    d[0] -= 1                       # bước đặc thù của ABN
    return sum(a * b for a, b in zip(d, ABN_W)) % 89 == 0

def valid_acn(s):
    if not re.fullmatch('[0-9]{9}', s or ''):
        return False
    d = [int(c) for c in s]
    total = sum(a * b for a, b in zip(d[:8], range(8, 0, -1)))
    return (10 - total % 10) % 10 == d[8]

CHECKSUMS = {'entity.abn': valid_abn, 'entity.acn': valid_acn}

def validate(canonical_field, value):
    group, _, name = canonical_field.partition('.')
    spec = ONT.get(group, {}).get(name)
    if not isinstance(spec, dict):
        return False, 'canonical_field not in ontology'
    v = str(value)
    if 'pattern' in spec and not re.fullmatch(spec['pattern'], v):
        return False, 'pattern mismatch'
    if spec.get('type') == 'enum' and v not in spec['values']:
        return False, 'not in enum'
    if spec.get('type') == 'date':
        try:
            date.fromisoformat(v)
        except ValueError:
            return False, 'bad date'
    if canonical_field in CHECKSUMS and not CHECKSUMS[canonical_field](v):
        return False, 'checksum failed'
    return True, ''