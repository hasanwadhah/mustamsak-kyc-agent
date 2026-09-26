"""Handwritten-name suggestions from several readings, and learning names from the reviewer."""
import random

import cv2
import numpy as np
import pytest

from app import handwritten_digits as hd, learning, storage
from app.housing_names import add_name_suggestions, consensus_suggestions, lexicon_suggestions
from app import understanding as u


def test_readings_that_each_hold_part_of_the_name_are_combined():
    # One view reads the first names, another the last two (a stamp covers part of each).
    readings = [{'value': 'كريم سعيلا جو', 'variant': 'color'}, {'value': 'ريم سعيدجواد', 'variant': 'pen_layer'},
                {'value': 'كريع سعيل جوا', 'variant': 'normalized'}]
    # Two views lean to «سعيل»; the one without the stamp reads «سعيد جواد»: the name is offered.
    assert 'كريم سعيد جواد' in [v for v, _ in consensus_suggestions(readings)]


def test_joined_split_and_compound_names():
    assert consensus_suggestions(['عليكريم حمير', 'عليكريم حميد'])[0][0] == 'علي كريم حميد'  # joined names
    assert consensus_suggestions(['عم ر جاسمعبد الأفير', 'عمر جاسمعد الأ فير'])[0][0] == 'عمر جاسم عبد الأمير'
    assert lexicon_suggestions(['رين المابدين كريم جواد'])[0] == 'زين العابدين كريم جواد'


def test_unknown_names_and_form_text_get_no_suggestion():
    assert lexicon_suggestions(['اسم غريب الأفير']) == []
    for text in ('مديرية الجنسية العامة', 'رقم الاستمارة', 'قصثف ضصثق طظكم'):
        assert consensus_suggestions([text]) == []


def test_a_variant_reading_the_right_name_is_offered_not_hidden():
    field = u.field('name', 'عليلية جواد', .9, None, 'housing_label_line', 'approximate',
                    readings=[{'value': 'عليلية جواد', 'variant': 'color'}, {'value': 'علي كريم جواد', 'variant': 'contrast'},
                              {'value': 'عليكريم جوار', 'variant': 'ink'}])
    add_name_suggestions(field)
    assert field['value'] == 'عليلية جواد'  # never replaced
    assert field['candidates'][0]['value'] == 'علي كريم جواد' and field['candidates'][0]['confidence'] is None


def test_suggestions_survive_ocr_noise_on_unseen_names():
    from scripts.evaluate_names import corrupt, random_name
    rng = random.Random(3)
    hits = 0
    for _ in range(30):
        truth = random_name(rng, 3)
        found = [v for v, _ in consensus_suggestions([corrupt(truth, 'medium', rng) for _ in range(3)])]
        hits += truth in found
    assert hits >= 24  # ≈ 90% in scripts/evaluate_names.py; a floor that catches regressions


def test_typed_or_confirmed_names_join_the_local_vocabulary(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    doc = {'kind': 'housing', 'side': 'front', 'fields': [
        {'key': 'name', 'value': 'مصطفى شنيشل يوسف', 'method': 'manual'}, {'key': 'street', 'value': '58', 'method': 'manual'}]}
    assert learning.learn_names(doc, {'name': {'value': 'ملافى وي روف'}}, verified=False) == ['مصطفى', 'شنيشل', 'يوسف']
    assert 'شنيشل' in learning.known_name_words()
    # A rare name the vocabulary did not know is now suggested from later readings of it.
    assert 'مصطفى شنيشل يوسف' in [v for v, _ in consensus_suggestions(['مصطفى شنيثل يوسف', 'مصطفى شنيسل يوسف'])]


def test_a_thin_pencil_number_is_kept_by_its_own_strip_mask():
    rgb = np.full((110, 520, 3), 238, np.uint8)
    cv2.line(rgb, (40, 20), (40, 100), (60, 60, 60), 9)  # thick pen elsewhere on the card
    for x in (180, 260, 340):
        cv2.line(rgb, (x, 25), (x + 30, 95), (120, 120, 120), 2)  # thin grey pencil strokes
    mask, width = hd.local_mask(rgb[:, 150:])
    assert width < 5 and mask.any() and (mask > 0).sum() > 3 * 70


def rendered_line(text, size=34):
    """A name written on a pale line (a printed font stands in for the handwriting)."""
    from PIL import Image, ImageDraw
    from scripts.synthetic_kyc import font, visual
    image = Image.new('RGB', (620, 70), (236, 240, 232))
    ImageDraw.Draw(image).text((20, 12), visual(text), font=font('arial.ttf', size), fill=(70, 70, 70))
    return np.array(image)


def test_the_line_image_picks_the_name_the_ocr_text_garbled():
    from app import arabic_ocr
    from app.name_decoder import suggest, LineScorer
    if not arabic_ocr.available():
        pytest.skip('local OCR models not installed')
    crop = rendered_line('مصطفى جاسم يوسف')
    scorer = LineScorer(crop)
    assert -3 < scorer('مصطفى جاسم يوسف') and scorer('مصطفى جاسم يوسف') > scorer('مصطفى علي يوسف')  # the image itself favours the true middle name
    ranked = suggest(crop, [{'value': 'مصطفى جاسن يوسف', 'variant': 'color'}, {'value': 'مصطفي جاسم يوسق', 'variant': 'normalized'}])
    assert ranked and ranked[0][0] == 'مصطفى جاسم يوسف'
