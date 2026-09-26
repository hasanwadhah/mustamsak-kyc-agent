"""Mustamsak's own number reader (app/number_reader.py) and its votes (docs/HANDWRITING.md)."""
import numpy as np
import pytest

from app import number_reader as nr
from app.housing_handwriting import sequence_votes


def test_narrow_strips_are_padded_with_their_own_colour_and_height_is_fixed():
    strip = np.full((80, 30, 3), (200, 230, 180), np.uint8)
    image = nr.to_input(strip)
    assert image.shape == (nr.HEIGHT, nr.MIN_WIDTH, 3)
    assert (image[:, 0] == (200, 230, 180)).all()
    assert nr.to_input(np.zeros((40, 4000, 3), np.uint8)).shape[1] == nr.MAX_WIDTH


def test_ctc_decoding_collapses_repeats_and_keeps_digits_split_by_blank():
    # frames: blank, 7, 7, blank, 7, 0(=digit 0), blank  -> "770"
    classes = [0, 8, 8, 0, 8, 1, 0]
    log_probs = np.log(np.full((len(classes), 11), .01))
    for t, k in enumerate(classes):
        log_probs[t, k] = np.log(.9)
    assert [d for d, _ in nr.decode(log_probs)] == [7, 7, 0]


def test_missing_model_reads_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(nr, 'MODEL_PATH', tmp_path / 'none.npz')
    nr.reset()
    assert nr.read(np.zeros((40, 100, 3), np.uint8)) is None
    nr.reset()


def reading(value, p=.97):
    return {'value': value, 'confidence': p, 'box': [[0, 0]], 'digits': [{'digit': int(c), 'probability': p} for c in value]}


def test_agreement_turns_a_single_reader_value_into_two_readers():
    fields = {'house_number': {'key': 'house_number', 'value': '15', 'confidence': .7, 'single_reader': True,
                               'approximate': True, 'status': 'approximate', 'candidates': []}}
    sequence_votes(fields, {'house_number': reading('15')})
    f = fields['house_number']
    assert f['value'] == '15' and not f['single_reader'] and not f['approximate'] and f['sequence_agrees']


def test_two_readers_beat_one_but_stay_approximate():
    fields = {'street': {'key': 'street', 'value': '45', 'method': 'eastern_digit_model', 'confidence': .8, 'status': 'conflict',
                         'candidates': [{'value': '42', 'engine': 'ocr'}]}}
    sequence_votes(fields, {'street': reading('42')})
    f = fields['street']
    assert f['value'] == '42' and f['approximate'] and f['status'] == 'conflict'
    assert any(c['value'] == '45' for c in f['candidates'])


def test_unsure_or_lone_readings_are_only_suggestions():
    fields = {'street': {'key': 'street', 'value': '45', 'candidates': [{'value': '42', 'engine': 'ocr'}]},
              'house_number': {'key': 'house_number', 'value': '', 'status': 'unreadable', 'candidates': []}}
    sequence_votes(fields, {'street': reading('42', p=.6), 'house_number': reading('9')})
    assert fields['street']['value'] == '45'
    assert fields['house_number']['value'] == ''
    assert fields['house_number']['candidates'][-1]['engine'] == 'number_reader'


@pytest.mark.parametrize('lock', [{'verified': True}, {'method': 'manual'}, {'status': 'manual'}])
def test_reviewed_values_are_never_touched(lock):
    fields = {'street': {'key': 'street', 'value': '45', 'candidates': [{'value': '42', 'engine': 'ocr'}]} | lock}
    before = dict(fields['street'])
    sequence_votes(fields, {'street': reading('42')})
    assert fields['street'] == before


def test_corrected_strips_are_saved_by_value_only_when_a_reader_saw_the_number(tmp_path, monkeypatch):
    from app import learning, storage
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    strip = np.full((40, 90, 3), 220, np.uint8)
    strips = {'house_number': strip, 'street': strip}
    readings = {'house_number': {'value': '16'}, 'street': {'value': '9'}}
    learning.save_strips(strips, readings, {}, {'house_number': '15', 'street': '42'}, 'doc1')
    saved = sorted(p.name for p in (tmp_path / 'number-strips').glob('*.png'))
    assert saved == ['15__house_number-doc1.png']  # «9» shares nothing with «42»: not saved
    learning.save_strips(strips, readings, {}, {'house_number': '16'}, 'doc1')
    assert sorted(p.name for p in (tmp_path / 'number-strips').glob('*.png')) == ['16__house_number-doc1.png']
    assert learning.strip_count() == 1
