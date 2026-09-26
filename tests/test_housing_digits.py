"""Handwritten Eastern Arabic numbers, housing labels and name suggestions (synthetic data only)."""
import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import arabic_ocr, handwritten_digits as hd, housing_handwriting as hh, understanding as u
from app.focused_fields import housing_role
from app.housing_names import lexicon_suggestions

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trainer', ROOT / 'scripts' / 'train_eastern_digits.py')
trainer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trainer)
needs_model = pytest.mark.skipif(not hd.available(), reason='run scripts/train_eastern_digits.py first')


def written(number, seed=3, height=60, zero_size=11):
    """Draw a handwritten-style number (left to right) as a pen mask, like a scanned field."""
    rng = np.random.default_rng(seed)
    canvas = np.zeros((120, 40 + 70 * len(number)), np.uint8)
    x = 20
    for ch in number:
        if ch == '0':
            cv2.circle(canvas, (x + 12, 60), zero_size // 2, 255, -1)
            x += 40
            continue
        glyph = trainer.draw_strokes(trainer.STROKES[int(ch)][0], rng, size=96)
        ys, xs = np.nonzero(glyph)
        glyph = glyph[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        glyph = cv2.resize(glyph, (max(8, int(glyph.shape[1] * height / glyph.shape[0])), height))
        canvas[30:30 + height, x:x + glyph.shape[1]] |= glyph
        x += glyph.shape[1] + 18
    return (canvas > 100).astype(np.uint8) * 255


@needs_model
@pytest.mark.parametrize('number', ['673', '47', '3184', '16', '8'])
def test_reads_handwritten_numbers_digit_by_digit(number):
    reading = hd.read_digits(mask=written(number), pen_width=6)
    assert reading and reading['value'] == number
    assert len(reading['digits']) == len(number) and all(0 <= d['probability'] <= 1 for d in reading['digits'])


@needs_model
def test_arabic_zero_is_a_dot_but_guide_dots_and_specks_are_not():
    assert hd.read_digits(mask=written('40'), pen_width=6)['value'] == '40'
    mask = written('42')
    for x in range(0, mask.shape[1], 12):  # printed dotted guide line
        cv2.circle(mask, (x, 100), 1, 255, -1)
    cv2.circle(mask, (mask.shape[1] - 5, 5), 3, 255, -1)  # a speck far above the line
    assert hd.read_digits(mask=mask, pen_width=6)['value'] == '42'


@needs_model
def test_nothing_readable_gives_none_not_a_guess():
    assert hd.read_digits(mask=np.zeros((80, 200), np.uint8), pen_width=5) is None


@needs_model
def test_far_away_ink_is_not_part_of_the_number():
    mask = written('42')
    mask = np.hstack([mask, np.zeros((mask.shape[0], 300), np.uint8)])
    cv2.line(mask, (mask.shape[1] - 10, 30), (mask.shape[1] - 10, 90), 255, 6)  # card border far to the right
    assert hd.read_digits(mask=mask, pen_width=6, anchor='left')['value'] == '42'


def test_digit_vote_accepts_only_the_models_own_alternatives():
    reading = {'digits': [{'digit': 9, 'alternatives': [{'digit': 4}, {'digit': 6}]}, {'digit': 6, 'alternatives': []}]}
    assert hh.digit_vote(reading, '46') == '46'
    assert hh.digit_vote(reading, '16') is None       # 1 was not among the model's choices
    assert hh.digit_vote(reading, '466') is None      # different length: no positional vote


def test_combining_readers_agrees_conflicts_and_respects_manual_values():
    reading = {'value': '42', 'confidence': .95, 'box': None, 'digits': [{'digit': 4, 'probability': .95, 'alternatives': []},
                                                                           {'digit': 2, 'probability': .95, 'alternatives': []}]}
    fields = {'street': u.field('street', '42', .7, None, 'housing_ink_components', 'approximate')}
    hh.combine_digit_readings(fields, {'street': reading})
    assert fields['street']['agreement'] and fields['street']['status'] == 'uncertain' and fields['street']['confidence'] == .95
    fields = {'street': u.field('street', '4', .7, None, 'housing_ink_components', 'approximate')}
    hh.combine_digit_readings(fields, {'street': reading})
    assert fields['street']['status'] == 'conflict' and {c['value'] for c in fields['street']['candidates']} >= {'42'}
    manual = {'street': u.field('street', '41', None, None, 'manual', 'manual')}
    hh.combine_digit_readings(manual, {'street': reading})
    assert manual['street']['value'] == '41' and manual['street']['method'] == 'manual'
    new = hh.combine_digit_readings({}, {'house_number': dict(reading, value='15', confidence=.6)})
    assert new['house_number']['value'] == '15' and new['house_number']['approximate']


def test_housing_labels_are_found_despite_ocr_slips():
    assert housing_role('منوان الكن') == 'address'
    assert housing_role('رقم الاستمارة') == 'form_number'
    assert housing_role('اسم راب الاسرة') == 'name'
    assert housing_role('جمهورية العراق') is None


def test_name_suggestions_fix_ocr_slips_but_never_invent_unknown_names():
    assert lexicon_suggestions(['رين المابدين كريم جواد'])[0] == 'زين العابدين كريم جواد'
    assert lexicon_suggestions(['اسم غريب الأفير']) == []
    assert lexicon_suggestions(['محمد احمد زيد علي']) == []  # already known names: nothing to suggest


def test_handwritten_arabic_indic_numbers_are_never_replaced_by_the_english_model():
    line = arabic_ocr.merge_readings({'text': '٦٧٣', 'confidence': .7}, {'text': '7ur', 'confidence': .9})
    assert line['text'] == '٦٧٣' and line['engine'] == 'ppocr_v5_arabic'
    line = arabic_ocr.merge_readings({'text': '٣٨٢٧٥', 'confidence': .9}, {'text': '18272', 'confidence': .95})
    assert line['text'] == '٣٨٢٧٥'  # the same ink read twice is not two numbers


def test_address_line_is_split_only_when_unambiguous():
    from app.address_layout import parse_address_digits
    assert parse_address_digits('٥٧٠٣٨٠٤٦٠٠') == {'mahalla_number': '460', 'street': '38', 'house_number': '57'}
    assert parse_address_digits('١٣٠٢٦٠٦٧٣٠') == {'mahalla_number': '673', 'street': '26', 'house_number': '13'}
    assert parse_address_digits('٦٧٣٠') is None       # markers not all read
    assert parse_address_digits('١٠٠١٠٠١٠٠') == {'mahalla_number': '10', 'street': '10', 'house_number': '10'}
    assert parse_address_digits('١٢٠٣٤٠٥٠٦٠') is None  # 506/34/12 or 6/3405/12: no guess


def test_layout_fallback_fills_empty_roles_but_never_overrides_people():
    from app.address_layout import layout_fields
    fields = {'address': u.field('address', '١٣٠٢٦٠٦٧٣٠', .8, None, 'housing_label_line', 'approximate'),
              'street': u.field('street', '44', None, None, 'manual', 'manual')}
    layout_fields(fields, {})
    assert fields['mahalla_number']['value'] == '673' and fields['house_number']['value'] == '13'
    assert fields['mahalla_number']['role_from_order'] and fields['mahalla_number']['approximate']
    assert fields['street']['value'] == '44'  # a person's entry wins


def test_english_readings_of_arabic_words_are_not_merged_as_numbers():
    line = arabic_ocr.merge_readings({'text': 'وزارة الداخلية', 'confidence': .95}, {'text': '1189', 'confidence': .56})
    assert line['text'] == 'وزارة الداخلية'
