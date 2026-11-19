"""API tests for the two study kinds, atomic corrections and refusal surfacing."""

import json

import pytest
from fastapi.testclient import TestClient

from src.config.database import Base, Session, engine
from src.main import app
from src.models.run import Run
from src.models.user import User
from src.services.runs import compute
from src.utils.security import hash_password


@pytest.fixture(scope='module')
def client():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('admin', 'analyst', 'viewer'):
            email = role + '@test.local'
            if not db.query(User).filter_by(email=email).first():
                db.add(User(email=email, role=role, password_hash=hash_password('pw')))
        db.commit()
    return TestClient(app)


def auth(client, role='admin'):
    token = client.post('/auth/login', json={'email': role + '@test.local', 'password': 'pw'}).json()['token']
    return {'Authorization': 'Bearer ' + token}


def make_study(client, headers, name, kind):
    response = client.post('/studies', json={'name': name, 'source_filename': 'f.csv', 'kind': kind}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()['id']


def shelf(group, entry, leak=None, broken=None, loss=None):
    return {'group': group, 'entry': entry, 'leak': leak, 'break': broken, 'loss': loss}


def run_and_compute(client, headers, study_id, parameters):
    response = client.post('/runs', json={'study_id': study_id, 'name': 'test run', 'parameters': parameters}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    with Session() as db:
        run = db.get(Run, body['id'])
        result = compute(run.snapshot, run.parameters, run.kind)
    return body, result


def test_study_kind_defaults_to_legacy_fisher(client):
    headers = auth(client)
    response = client.post('/studies', json={'name': 'legacy', 'source_filename': 'f.csv'}, headers=headers)
    assert response.json()['kind'] == 'seal_fisher'
    listed = {s['name']: s for s in client.get('/studies', headers=headers).json()}
    assert listed['legacy']['kind_label'] == '试封计数比较'


def test_legacy_fisher_run_still_works(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'fisher run', 'seal_fisher')
    for key, value in (('x', {'group': 'A', 'success': 8, 'failure': 2}),
                       ('y', {'group': 'B', 'success': 9, 'failure': 1})):
        assert client.post(f'/studies/{study_id}/observations',
                           json={'source_key': key, 'values': value}, headers=headers).status_code == 200
    body, result = run_and_compute(client, headers, study_id, {})
    assert body['kind'] == 'seal_fisher'
    assert 0 <= result['metrics']['Fisher双侧p'] <= 1
    assert 'A组合格率' in result['metrics']


def test_shelf_run_reports_risk_difference_and_at_risk_basis(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'shelf run', 'shelf_risk')
    rows = [
        {'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
        {'source_key': 'A2', 'values': shelf('A', 0, loss=30)},
        {'source_key': 'B1', 'values': shelf('B', 0, broken=10)},
        {'source_key': 'B2', 'values': shelf('B', 0, loss=30)},
    ]
    assert client.post(f'/studies/{study_id}/observations/batch', json={'rows': rows}, headers=headers).status_code == 200
    body, result = run_and_compute(client, headers, study_id, {'day': 10})
    metrics = result['metrics']
    assert metrics['A组漏封累计发生率'] == pytest.approx(0.5)
    assert metrics['B组漏封累计发生率'] == pytest.approx(0)
    assert metrics['B减A漏封风险差'] == pytest.approx(-0.5)
    assert metrics['A组指定日在险试件'] == 2
    assert metrics['B组指定日在险试件'] == 2
    assert result['columns'][0] == '工艺'
    assert result['assumptions']


def test_shelf_day_outside_support_is_refused_on_the_run(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'shelf refused', 'shelf_risk')
    rows = [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
            {'source_key': 'B1', 'values': shelf('B', 0, leak=10)}]
    client.post(f'/studies/{study_id}/observations/batch', json={'rows': rows}, headers=headers)
    response = client.post('/runs', json={'study_id': study_id, 'name': 'refuse run', 'parameters': {'day': 40}}, headers=headers)
    assert response.status_code == 200
    with Session() as db:
        run = db.get(Run, response.json()['id'])
        with pytest.raises(Exception) as excinfo:
            compute(run.snapshot, run.parameters, run.kind)
    assert '拒绝出结论' in str(excinfo.value)


def test_unknown_parameters_are_rejected_per_kind(client):
    headers = auth(client)
    shelf_id = make_study(client, headers, 'params shelf', 'shelf_risk')
    client.post(f'/studies/{shelf_id}/observations/batch',
                json={'rows': [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
                               {'source_key': 'B1', 'values': shelf('B', 0, leak=10)}]}, headers=headers)
    assert client.post('/runs', json={'study_id': shelf_id, 'name': 'bad', 'parameters': {'alpha': 0.05}}, headers=headers).status_code == 422
    fisher_id = make_study(client, headers, 'params fisher', 'seal_fisher')
    client.post(f'/studies/{fisher_id}/observations',
                json={'source_key': 'x', 'values': {'group': 'A', 'success': 1, 'failure': 1}}, headers=headers)
    client.post(f'/studies/{fisher_id}/observations',
                json={'source_key': 'y', 'values': {'group': 'B', 'success': 1, 'failure': 1}}, headers=headers)
    assert client.post('/runs', json={'study_id': fisher_id, 'name': 'bad', 'parameters': {'day': 30}}, headers=headers).status_code == 422


def test_batch_correction_is_atomic(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'atomic batch', 'shelf_risk')
    rows = [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
            {'source_key': 'B1', 'values': shelf('B', 0, leak=20)}]
    assert client.post(f'/studies/{study_id}/observations/batch', json={'rows': rows}, headers=headers).status_code == 200
    # One row is invalid: the whole correction must be rejected and nothing written.
    ids = {r['source_key']: r['id'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    bad = [{'source_key': 'A1', 'row_id': ids['A1'], 'values': shelf('A', 0, leak=5)},
           {'source_key': 'B1', 'row_id': ids['B1'], 'values': shelf('B', 0, leak=5, loss=6)}]
    assert client.post(f'/studies/{study_id}/observations/batch', json={'rows': bad}, headers=headers).status_code == 422
    stored = {r['source_key']: r['values'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    assert stored['A1']['leak'] == 10
    assert stored['B1']['leak'] == 20


def test_batch_correction_updates_both_groups_by_row_id(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'both sides', 'shelf_risk')
    client.post(f'/studies/{study_id}/observations/batch',
                json={'rows': [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
                               {'source_key': 'B1', 'values': shelf('B', 0, leak=10)}]}, headers=headers)
    ids = {r['source_key']: r['id'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    corrected = [{'source_key': 'A1', 'row_id': ids['A1'], 'values': shelf('A', 0, leak=4)},
                 {'source_key': 'B1', 'row_id': ids['B1'], 'values': shelf('B', 0, broken=4)}]
    response = client.post(f'/studies/{study_id}/observations/batch', json={'rows': corrected}, headers=headers)
    assert response.status_code == 200
    stored = {r['source_key']: r['values'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    assert stored['A1']['leak'] == 4
    assert stored['B1']['break'] == 4 and stored['B1']['leak'] is None
    assert len(stored) == 2


def test_run_snapshot_is_never_half_corrected(client):
    """A queued run freezes one full state; a later batch does not leak into it."""
    headers = auth(client)
    study_id = make_study(client, headers, 'snapshot isolation', 'shelf_risk')
    client.post(f'/studies/{study_id}/observations/batch',
                json={'rows': [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
                               {'source_key': 'B1', 'values': shelf('B', 0, leak=10)}]}, headers=headers)
    before, _ = run_and_compute(client, headers, study_id, {'day': 10})
    ids = {r['source_key']: r['id'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    client.post(f'/studies/{study_id}/observations/batch',
                json={'rows': [{'source_key': 'A1', 'row_id': ids['A1'], 'values': shelf('A', 0, leak=2)},
                               {'source_key': 'B1', 'row_id': ids['B1'], 'values': shelf('B', 0, leak=2)}]}, headers=headers)
    after, _ = run_and_compute(client, headers, study_id, {'day': 2})
    before_values = {row['source_key']: row['values'] for row in before['snapshot']}
    after_values = {row['source_key']: row['values'] for row in after['snapshot']}
    assert before_values['A1']['leak'] == 10 and before_values['B1']['leak'] == 10
    assert after_values['A1']['leak'] == 2 and after_values['B1']['leak'] == 2
    assert before['checksum'] != after['checksum']


def test_batch_new_row_with_existing_source_key_is_rejected(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'dup key', 'shelf_risk')
    client.post(f'/studies/{study_id}/observations/batch',
                json={'rows': [{'source_key': 'A1', 'values': shelf('A', 0, leak=10)},
                               {'source_key': 'B1', 'values': shelf('B', 0, leak=10)}]}, headers=headers)
    response = client.post(f'/studies/{study_id}/observations/batch',
                           json={'rows': [{'source_key': 'A1', 'values': shelf('A', 0, leak=3)}]}, headers=headers)
    assert response.status_code == 409
    stored = {r['source_key']: r['values'] for r in client.get(f'/studies/{study_id}/observations', headers=headers).json()}
    assert stored['A1']['leak'] == 10 and len(stored) == 2


def test_invalid_shelf_field_combination_is_rejected(client):
    headers = auth(client)
    study_id = make_study(client, headers, 'invalid shelf', 'shelf_risk')
    response = client.post(f'/studies/{study_id}/observations',
                           json={'source_key': 'A1', 'values': shelf('A', 5, leak=4)}, headers=headers)
    assert response.status_code == 422
    response = client.post(f'/studies/{study_id}/observations',
                           json={'source_key': 'A1', 'values': shelf('A', 0, leak=4, broken=4)}, headers=headers)
    assert response.status_code == 422


def test_viewer_cannot_write_shelf_rows(client):
    headers = auth(client, 'viewer')
    study_id = {s['name']: s['id'] for s in client.get('/studies', headers=headers).json()}['shelf run']
    response = client.post(f'/studies/{study_id}/observations/batch',
                           json={'rows': [{'source_key': 'Z', 'values': shelf('A', 0, leak=1)}]}, headers=headers)
    assert response.status_code == 403
