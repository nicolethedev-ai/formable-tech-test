import os
os.environ.setdefault('BEDROCK_MODEL_ID', 'test-model')
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['USE_S3'] = '0'

import json, random
import pytest
from src.core.validators import valid_abn
from src.core.engine import extract
from src.agent import steps
from src.agent.run import run_step
from src.adapters.storage import Storage

GOOD = {
    'dataset_kind': 'licence register',
    'record_id': {'strategy': 'field', 'field': 'LIC_NO', 'how': 'LIC_NO is unique per row'},
    'fields': [
        {'source_field': 'ABN_NUMBER', 'canonical_field': 'entity.abn', 'transforms': [{'name': 'digits_only'}],
         'field_confidence': 0.95, 'rationale': 'abn_like=1.0'},
        {'source_field': 'LICENSEE', 'canonical_field': 'entity.legal_name', 'transforms': [{'name': 'trim'}],
         'field_confidence': 0.8, 'rationale': 'company names'},
        {'source_field': 'STATE_NAME', 'canonical_field': 'address.state',
         'transforms': [{'name': 'upper'}, {'name': 'map', 'table': {'NEW SOUTH WALES': 'NSW'}}],
         'field_confidence': 0.9, 'rationale': 'state names'}],
    'unmapped': [{'source_field': 'NOTES', 'reason': 'free text'}]}

def bad():
    b = json.loads(json.dumps(GOOD))
    b['fields'][0]['source_field'] = 'LIC_NO'     # sai cột: ABN thật bị bỏ sót
    return b

@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rng = random.Random(1)
    rows = ['LIC_NO,LICENSEE,ABN_NUMBER,STATE_NAME,NOTES']
    for i in range(80):
        abn = str(rng.randrange(10**10, 10**11))
        while not valid_abn(abn):
            abn = str(rng.randrange(10**10, 10**11))
        rows.append('L%04d,Company %d Pty Ltd,%s,New South Wales,note %d' % (i, i, abn, i))
    p = tmp_path / 'fake.csv'
    p.write_text(chr(10).join(rows), encoding='utf-8')
    st = dict(source_id='fake', args={}, steps={}, configs=[], validations=[],
              meta=dict(source_id='fake', path=str(p), format='csv', title='Fake licences',
                        organization='Fake Dept', notes='licence register', licence='cc-by',
                        resource_url='http://x', metadata_modified='2026-01-01T00:00:00'))
    steps.inspect_step(st)
    steps.sample_step(st)
    return st

def test_inspect_and_sample(state):
    assert state['reader']['format'] == 'csv' and state['reader']['delimiter'] == ','
    assert state['n_records'] == 80
    assert not set(state['propose_idx']) & set(state['holdout_idx'])      # holdout tách biệt
    assert state['profile']['ABN_NUMBER']['abn_like'] == 1.0
    assert state['profile']['LICENSEE']['abn_like'] == 0.0

def test_good_config_passes(state):
    res = steps.validate_config(state, steps.finalize(GOOD, state, 1))
    assert res['ok'], res['issues']
    assert res['metrics']['abn_pass_rate'] == 1.0

def test_validate_catches_wrong_and_invented_columns(state):
    b = bad()
    b['fields'].append({'source_field': 'NO_SUCH_COL', 'canonical_field': 'entity.website',
                        'field_confidence': 0.9, 'rationale': 'x'})
    res = steps.validate_config(state, steps.finalize(b, state, 1))
    codes = {i['code'] for i in res['issues']}
    assert not res['ok']
    assert {'checksum_fail', 'missed_abn', 'unknown_source_field'} <= codes

def test_revision_loop_feeds_errors_back(state, monkeypatch):
    calls = []
    def fake_llm(system, user, tool=None, max_tokens=0, step='', source_id=''):
        calls.append((step, user))
        return json.loads(json.dumps(bad() if step == 'propose' else GOOD))
    monkeypatch.setattr(steps, 'call_llm', fake_llm)
    steps.propose_step(state)
    steps.refine_step(state)
    assert [c[0] for c in calls] == ['propose', 'revise']
    assert 'checksum_fail' in calls[1][1]          # lỗi cụ thể được đưa lại cho model
    assert len(state['configs']) == 2 and state['final_validation']['ok']

def test_revision_loop_gives_up(state, monkeypatch):
    monkeypatch.setattr(steps, 'call_llm', lambda *a, **k: bad())
    steps.propose_step(state)
    steps.refine_step(state)
    assert len(state['configs']) == steps.MAX_REVISIONS + 1
    assert not state['final_validation']['ok']

def test_cannot_approve_failing_config(state, monkeypatch):
    monkeypatch.setattr(steps, 'call_llm', lambda *a, **k: bad())
    steps.propose_step(state)
    steps.refine_step(state)
    state['args'] = {'decision': 'approve'}
    steps.approve_step(state)
    assert state['approval']['decision'] == 'blocked'
    assert not os.path.exists('configs/fake.yaml')

def test_approved_config_runs_in_engine(state):
    state['final_config'] = steps.finalize(GOOD, state, 1)
    state['final_validation'] = steps.validate_config(state, state['final_config'])
    state['configs'] = [state['final_config']]
    state['args'] = {'decision': 'approve'}
    steps.approve_step(state)
    assert state['approval']['decision'] == 'approved'
    summary = extract('configs/fake.yaml', state['meta']['path'], out_dir='out')
    assert summary['records'] == 80
    assert sum(1 for _ in open('out/observations/fake.json')) == 240    # 3 field x 80 dòng

def test_run_step_skips_done_and_records_failure(state):
    st = Storage()
    state['steps']['x'] = {'status': 'done'}
    run_step(state, 'x', lambda s: 1 / 0, st)       # đã done thì không được chạy
    def boom(s):
        raise RuntimeError('network down')
    with pytest.raises(RuntimeError):
        run_step(state, 'y', boom, st)
    assert state['steps']['y']['status'] == 'failed'
    assert st.get_json('state/fake/state.json')['steps']['y']['status'] == 'failed'

def test_finalize_falls_back_to_hash_for_unusable_record_id(state):
    m = json.loads(json.dumps(GOOD))
    m['record_id'] = {'strategy': 'field', 'field': 'None', 'how': 'x'}
    assert steps.finalize(m, state, 1)['record_id']['strategy'] == 'hash'