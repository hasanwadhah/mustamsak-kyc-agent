"""Learning from the reviewer's corrections: exact labels only, local samples, a safe install gate."""
import json

import numpy as np
import pytest

from app import handwritten_digits as hd, learning, storage
from test_housing_digits import needs_model, written


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for folder in ('batches', 'images', 'exports'):
        (tmp_path / folder).mkdir(exist_ok=True)
    return tmp_path


def reading(value):
    return {'value': value, 'call': 7, 'digits': []}


def piece(digit):
    return {'mask': np.full((5, 5), 255, np.uint8), 'digit': digit, 'probability': .9, 'call': 7}


def test_samples_are_labelled_only_when_the_digits_line_up_exactly():
    pieces = [piece(9), piece(5)]
    assert [d for _, d in learning.labelled_pieces(reading('95'), pieces, '15')] == ['1', '5']  # a misread is fixed by the label
    assert learning.labelled_pieces(reading('905'), pieces, '15') == []   # different length
    assert learning.labelled_pieces(reading('15'), pieces, '105') == []   # zero in a different place
    assert learning.labelled_pieces(reading('15'), [piece(1)], '15') == []  # a piece is missing
    assert [d for _, d in learning.labelled_pieces(reading('40'), [piece(4)], '40')] == ['4']  # zeros are dots, not samples
    fused = dict(reading('95'), occluded=True)
    assert learning.labelled_pieces(fused, pieces, '15') == []  # a digit fused with a stamp is never a sample


@needs_model
def test_each_reading_owns_its_collected_pieces():
    hd.collector = []
    try:
        a = hd.read_digits(mask=written('42'), pen_width=6)
        b = hd.read_digits(mask=written('673'), pen_width=6)
        collected = hd.collector
    finally:
        hd.collector = None
    mine = [p for p in collected if p['call'] == b['call']]
    assert a['call'] != b['call'] and [p['digit'] for p in mine] == [6, 7, 3]
    assert [d for _, d in learning.labelled_pieces(b, mine, '673')] == ['6', '7', '3']


def test_only_typed_or_confirmed_housing_numbers_are_learned():
    def f(key, value, method='eastern_digit_model'):
        return {'key': key, 'value': value, 'method': method}
    doc = {'kind': 'housing', 'side': 'front', 'fields': [f('house_number', '15', 'manual'), f('street', '42'),
                                                          f('name', 'سليم', 'manual'), f('mahalla_number', 'غير واضح', 'manual')]}
    previous = {'house_number': {'value': '95'}, 'street': {'value': '42'}}
    assert learning.reviewed_values(doc, previous, verified=False) == {'house_number': '15'}
    assert learning.reviewed_values(doc, previous, verified=True) == {'house_number': '15', 'street': '42'}
    assert learning.reviewed_values(dict(doc, kind='national_id'), previous, verified=True) == {}


def test_saving_a_corrected_card_queues_learning(data, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    queued = []
    monkeypatch.setattr(learning, 'capture_later', lambda bid, did, values: queued.append(values))
    batch = {'id': 'b' * 32, 'name': 'x', 'created': '2026-09-25T00:00:00', 'status': 'ready', 'progress': 100, 'message': '',
             'sources': [], 'documents': [{'id': 'd' * 32, 'kind': 'housing', 'side': 'front', 'group': 'g', 'reviewed': False,
                                           'fields': [{'key': 'house_number', 'label': 'رقم الدار', 'value': '95', 'method': 'eastern_digit_model'}]}]}
    storage.save_batch(batch)
    with TestClient(main.app) as client:
        r = client.patch(f"/api/batches/{'b' * 32}/documents/{'d' * 32}",
                         json={'kind': 'housing', 'side': 'front', 'group': 'g', 'reviewed': False,
                               'fields': [{'key': 'house_number', 'label': 'رقم الدار', 'value': '15'}]})
    assert r.status_code == 200 and queued == [{'house_number': '15'}]


def test_switch_counts_and_too_few_samples(data):
    from fastapi.testclient import TestClient
    from app import main
    with TestClient(main.app) as client:
        s = client.get('/api/learning').json()
        assert s['enabled'] is True and s['total'] == 0
        assert client.put('/api/learning', json={'enabled': False}).json()['enabled'] is False
        assert not learning.enabled() and learning.capture_later('b', 'd', {'street': '42'}) is None
        r = client.post('/api/learning/train')
        assert r.status_code == 409 and 'أقل من' in r.json()['detail']


def model_file(path, **meta):
    np.savez_compressed(path, meta=np.array(json.dumps(meta)))


@pytest.mark.parametrize('new_madbase,installed', [(.99, True), (.95, False)])
def test_a_new_model_is_installed_only_if_it_does_not_get_worse(data, monkeypatch, tmp_path, new_madbase, installed):
    monkeypatch.setattr(learning, 'ROOT', tmp_path)
    (tmp_path / 'models').mkdir()
    current = tmp_path / 'models' / 'eastern_digits_cnn.npz'
    model_file(current, madbase_test_accuracy=.991, madbase_test_accuracy_under_overlap=.938)
    monkeypatch.setattr(hd, 'CNN_PATH', current)
    for i in range(learning.MIN_SAMPLES):
        folder = data / 'digit-samples' / str(i % 9 + 1)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{i}.png').write_bytes(b'x')

    def runner():
        model_file(tmp_path / 'models' / 'eastern_digits_cnn.candidate.npz', madbase_test_accuracy=new_madbase,
                   madbase_test_accuracy_under_overlap=.94, own_samples_check_accuracy=.9, own_samples_check_size=8)
        return 0
    learning.start_training(runner=runner)
    learning._training.join(10)
    state = learning.status()['training']
    assert state['state'] == ('installed' if installed else 'rejected')
    assert json.loads(str(np.load(current)['meta']))['madbase_test_accuracy'] == (new_madbase if installed else .991)
    assert (tmp_path / 'models' / 'eastern_digits_cnn.previous.npz').exists() == installed
