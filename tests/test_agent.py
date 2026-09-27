"""The KYC agent screen's API (app/agent_api.py) and the "whole file in one photo" separation."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import agent_api, main, storage, vision


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for folder in ['batches', 'images', 'exports']:
        (tmp_path / folder).mkdir()
    with TestClient(main.app) as c:
        yield c


needs_demo = pytest.mark.skipif(not (agent_api.DEMO / 'labels.json').exists(), reason='demo files not generated')


@needs_demo
def test_demo_cases_are_fictional_and_complete(client):
    r = client.get('/api/demo/cases').json()
    assert r['fictional'] is True and r['cases']
    case = r['cases'][0]
    assert [f.split('_', 1)[1] for f in case['files']] == ['id_front.jpg', 'id_back.jpg', 'license.jpg', 'tax.jpg']
    assert client.get(f"/api/demo/files/{case['files'][0]}").headers['content-type'] == 'image/jpeg'


@pytest.mark.parametrize('name', ['../labels.json', 'labels.json', '..%2Fapp%2Fmain.py', 'case000_id_front.png', 'x.jpg'])
def test_demo_files_cannot_reach_anything_else(client, name):
    assert client.get(f'/api/demo/files/{name}').status_code == 404


@needs_demo
def test_a_demo_case_goes_through_the_normal_upload_path(client, monkeypatch):
    started = []
    monkeypatch.setattr(main, 'start_batch', lambda items, token, name=None: started.append((items, name)) or {'id': 'b'})
    case = client.get('/api/demo/cases').json()['cases'][0]
    assert client.post(f"/api/demo/cases/{case['id']}", json={'mode': 'pile'}).status_code == 202
    items, name = started[0]
    assert [n for n, _ in items] == [case['pile']] and 'one photo' in name
    assert client.post('/api/demo/cases/nope', json={}).status_code == 404
    main.pending.clear()


def test_evaluation_endpoint_reports_what_exists(client, monkeypatch, tmp_path):
    monkeypatch.setattr(agent_api, 'REPORTS', tmp_path)
    assert client.get('/api/evaluation').json() == {'heldout': None, 'tune': None}
    (tmp_path / 'kyc-heldout.json').write_text('{"images": 64, "kyc": {"details": [1, 2]}}', encoding='utf-8')
    r = client.get('/api/evaluation').json()
    assert r['heldout'] == {'images': 64, 'kyc': {}}  # per-case details stay out of the page


def test_the_agent_screen_and_the_workspace_are_both_served(client):
    assert 'KYC Document Agent' in client.get('/').text
    assert 'مستمسك' in client.get('/workspace').text


@needs_demo
def test_a_whole_file_on_a_desk_is_separated_into_its_four_documents():
    import importlib.util
    spec = importlib.util.spec_from_file_location('demo_pile', agent_api.ROOT / 'scripts' / 'demo_pile.py')
    demo_pile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo_pile)
    if not (demo_pile.DEMO / 'case000_id_front_template.png').exists():
        pytest.skip('demo templates not generated')
    for seed in (1, 2, 3):
        photo = demo_pile.pile(0, np.random.default_rng(seed))[:, :, ::-1]
        assert len(vision.detect_regions(photo)) == 4


def test_a_single_card_photo_is_still_one_document():
    image = np.full((900, 1200, 3), 60, np.uint8)
    image[150:750, 200:1100] = 235  # one card filling most of the photo
    image[250:450, 260:420] = 150   # its portrait box: not a document of its own
    assert len(vision.detect_regions(image)) == 1


def test_the_guided_tour_is_available_on_both_screens(client):
    for page in ('/', '/workspace'):
        html = client.get(page).text
        assert '/static/tour.js' in html and '/static/tour.css' in html
    tour = client.get('/static/tour.js').text
    assert 'agentSteps' in tour and 'workspaceSteps' in tour and "tour=ws" in tour
