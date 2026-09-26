"""The AI training dashboard API (app/training_center.py, app/training_api.py)."""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import learning, main, storage, training_center as tc


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    monkeypatch.setattr(learning, 'ROOT', tmp_path)  # never a real model, checkpoint or training run
    for folder in ['batches', 'images', 'exports']:
        (tmp_path / folder).mkdir()
    with TestClient(main.app) as c:
        yield c


def png(path, value=255):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((30, 20), value, np.uint8)
    image[5:25, 8:12] = 0
    cv2.imwrite(str(path), image)


def test_overview_counts_samples_and_gives_advice(client, tmp_path):
    png(tmp_path / 'digit-samples' / '2' / 'corr-a-street-0.png')
    png(tmp_path / 'number-strips' / '42__street-doc1.png')
    o = client.get('/api/training').json()
    assert o['data']['digits']['2'] == 1 and o['data']['strips'] == 1
    assert o['data']['strips_by_field']['زقاق'] == 1
    assert any('شرائح' in t for t in o['advice'])
    assert {m['id'] for m in o['models']} == {'digits', 'numbers'}


def test_samples_are_listed_shown_relabelled_and_deleted(client, tmp_path):
    png(tmp_path / 'digit-samples' / '3' / 'corr-a-street-0.png')
    png(tmp_path / 'number-strips' / '43__street-doc1.png')
    items = client.get('/api/training/samples/digits').json()['items']
    assert items[0]['id'] == '3/corr-a-street-0.png'
    image = client.get('/api/training/samples/digits/image', params={'id': items[0]['id']})
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    moved = client.patch('/api/training/samples/digits', params={'id': items[0]['id']}, json={'label': '2'}).json()
    assert moved['id'] == '2/corr-a-street-0.png' and (tmp_path / 'digit-samples' / '2' / 'corr-a-street-0.png').exists()
    renamed = client.patch('/api/training/samples/strips', params={'id': '43__street-doc1.png'}, json={'label': '42'}).json()
    assert renamed['id'] == '42__street-doc1.png'
    assert client.patch('/api/training/samples/strips', params={'id': '42__street-doc1.png'}, json={'label': '4a'}).status_code == 400
    assert client.delete('/api/training/samples/strips', params={'id': '42__street-doc1.png'}).json()['ok']
    assert not list((tmp_path / 'number-strips').glob('*.png'))


@pytest.mark.parametrize('kind,bad', [('digits', '../settings.json'), ('digits', '2/../../x.png'), ('strips', '..\\x.png'),
                                      ('strips', '12__../../a.png'), ('digits', 'C:/Windows/win.ini')])
def test_sample_ids_cannot_reach_other_files(client, kind, bad):
    assert client.get(f'/api/training/samples/{kind}/image', params={'id': bad}).status_code in (400, 404)
    assert client.delete(f'/api/training/samples/{kind}', params={'id': bad}).status_code in (400, 404)


def test_starting_needs_something_to_train(client):
    r = client.post('/api/training/start', json={'models': ['digits', 'numbers'], 'steps': 500})
    assert r.status_code == 409  # no samples, no checkpoint in this test root
    assert client.post('/api/training/start', json={'models': ['numbers'], 'steps': 50}).status_code == 422
    assert client.post('/api/training/stop').status_code == 409


def test_progress_is_parsed_from_this_runs_part_of_the_log(client, tmp_path):
    log = learning.log_file()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('old run\nstep 200 loss 9.0 1s/step\n', encoding='utf-8')
    offset = log.stat().st_size
    with log.open('a', encoding='utf-8') as f:
        f.write('=== phase numbers\nplan steps 1500\nstep 200 loss 0.5 1s/step\n  held-out writers: 88.500% whole numbers right (step 250)\n')
    learning._write_state({'state': 'installed', 'log_offset': offset, 'steps': 1500})
    p = client.get('/api/training/progress').json()
    assert p['phase'] == 'numbers' and p['total_steps'] == 1500
    assert p['numbers']['steps'] == [200] and p['numbers']['loss'] == [0.5]
    assert p['numbers']['held_out'] == [[250, 0.885]]


def test_rollback_swaps_so_it_can_be_undone(client, tmp_path, monkeypatch):
    from app import number_reader as nr
    current, previous = tmp_path / 'number_reader.npz', tmp_path / 'number_reader.previous.npz'
    current.write_bytes(b'new')
    previous.write_bytes(b'old')
    monkeypatch.setattr(nr, 'MODEL_PATH', current)
    assert client.post('/api/training/rollback', json={'model': 'numbers'}).status_code == 200
    assert current.read_bytes() == b'old' and previous.read_bytes() == b'new'
    client.post('/api/training/rollback', json={'model': 'numbers'})
    assert current.read_bytes() == b'new'
    assert learning.history()[-1]['state'] == 'rollback'


def test_evaluation_separates_kept_aside_samples(client, tmp_path):
    for i in range(5):
        png(tmp_path / 'digit-samples' / '1' / f's{i}.png')
    r = client.post('/api/training/evaluate').json()
    assert r['digits']['total'] == 5 and r['digits']['kept_aside'] == 1
    assert len(client.get('/api/training').json()['evaluations']) == 1
