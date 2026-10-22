import json
from src.core.validators import valid_abn, valid_acn, validate
from src.core.transforms import TRANSFORMS
from src.core.engine import extract

def test_abn():
    assert valid_abn('51824753556')
    assert not valid_abn('51824753557')
    assert not valid_abn('1234567890')

def test_acn():
    assert valid_acn('000000019')
    assert not valid_acn('000000018')

def test_validate_enum_and_unknown_field():
    assert validate('address.state', 'NSW')[0]
    assert not validate('address.state', 'Sydney')[0]
    assert not validate('entity.favourite_colour', 'red')[0]

def test_transforms():
    assert TRANSFORMS['digits_only']('51 824 753 556') == '51824753556'
    assert TRANSFORMS['date_parse']('03/02/2021', formats=['%d/%m/%Y']) == '2021-02-03'
    assert TRANSFORMS['map']('new south wales', table={'NEW SOUTH WALES': 'NSW'}) == 'NSW'

def test_engine_mini(tmp_path):
    extract('tests/fixtures/mini.yaml', 'tests/fixtures/mini.csv', out_dir=str(tmp_path))
    obs = [json.loads(l) for l in open(tmp_path / 'observations' / 'mini.json')]
    rej = [json.loads(l) for l in open(tmp_path / 'rejects' / 'mini.json')]
    assert len(obs) == 6          # r1: 3, r2: 2 (ABN sai bị loại), r3: 1 (không ABN, bang 'Sydney' không map được)
    assert len(rej) == 1 and rej[0]['reason'] == 'checksum failed'
    assert all(o['licence'] and o['extractor_version'] and o['source_record_id'] for o in obs)