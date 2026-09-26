import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import kyc, main, pipeline, storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    monkeypatch.setattr(kyc, 'calibration', lambda: None)
    for folder in ['batches', 'images', 'exports']:
        (tmp_path / folder).mkdir()
    with TestClient(main.app) as c:
        yield c


def field(key, value, confidence=.97, status='read'):
    return {'key': key, 'label': key, 'value': value, 'confidence': confidence, 'status': status, 'verified': False}


def test_batch_kyc_endpoint_reports_decision_and_never_changes_the_batch(client):
    b = pipeline.new_batch('kyc')
    b['status'] = 'ready'
    b['documents'] = [{'id': storage.uid(), 'kind': 'national_id', 'side': 'front', 'image_id': storage.uid(), 'capture': [],
                       'fields': [field('name', 'محمد حسين علي'), field('national_number', '199012345678'),
                                  field('document_number', 'AB1234567', .5, 'uncertain')]}]
    storage.save_batch(b)
    before = storage.get_batch(b['id'])
    r = client.get(f'/api/batches/{b["id"]}/kyc?profile=individual')
    assert r.status_code == 200
    body = r.json()
    assert body['decision'] == 'review' and body['profile'] == 'individual'
    assert any(x['field_key'] == 'document_number' for x in body['reasons'])
    assert storage.get_batch(b['id']) == before
    assert client.get(f'/api/batches/{b["id"]}/kyc?threshold=2').status_code == 422
    assert client.get('/api/batches/' + 'a' * 32 + '/kyc').status_code == 404


def test_policy_endpoint(client):
    body = client.get('/api/kyc/policy').json()
    assert .5 <= body['threshold'] < 1 and 'merchant' in body['profiles'] and body['calibration']['fitted'] is False


def test_capture_check_endpoint_asks_for_retake_on_a_cut_off_card(client):
    frame = np.full((900, 1300, 3), 45, np.uint8)
    frame[500:900, 700:1300] = 220  # A light card running off the bottom-right corner.
    for y in range(540, 880, 30):
        cv2.putText(frame, 'ABC 12345', (720, y), cv2.FONT_HERSHEY_SIMPLEX, .8, (20, 20, 20), 2)
    ok, png = cv2.imencode('.png', frame)
    r = client.post('/api/capture-check', files={'file': ('card.png', png.tobytes(), 'image/png')})
    assert r.status_code == 200 and r.json()['retake']
    assert client.post('/api/capture-check', files={'file': ('x.png', b'not an image', 'image/png')}).status_code == 422
