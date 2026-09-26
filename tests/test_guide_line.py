"""Printed dotted guide lines: never read as zeros, and used to find the م / ز / د markers (synthetic)."""
import cv2
import numpy as np

from app import handwritten_digits as hd
from app.housing_handwriting import guide_line_markers
from test_housing_digits import needs_model, written


def dotted(mask, y, x1, x2, size=10, pitch=18, skip=()):
    """Print a row of equal square dots, as under the fields of a housing card."""
    for x in range(x1, x2, pitch):
        if not any(a <= x <= b for a, b in skip):
            mask[y:y + size, x:x + size] = 255
    return mask


@needs_model
def test_big_guide_dots_are_not_read_as_zeros():
    mask = written('42')
    mask = np.pad(mask, ((0, 0), (300, 300)))
    dotted(mask, 88, 5, mask.shape[1] - 10, skip=[(310, mask.shape[1] - 330)])  # dots on both sides of the number
    dotted(mask, 88, 330, 345)  # one dot peeking out between the digits
    assert hd.read_digits(mask=mask, pen_width=6)['value'] == '42'


@needs_model
def test_a_handwritten_zero_is_kept_next_to_a_dotted_line():
    mask = np.pad(written('40'), ((0, 0), (300, 300)))
    dotted(mask, 100, 5, mask.shape[1] - 10, skip=[(300, mask.shape[1] - 300)])
    assert hd.read_digits(mask=mask, pen_width=6)['value'] == '40'


def test_markers_are_found_on_the_dotted_line_and_stamp_bits_are_ignored():
    h, w = 190, 1240
    mask = np.zeros((h, w), np.uint8)
    markers = {'د': 560, 'ز': 870, 'م': 1175}
    dotted(mask, 90, 300, 1165, size=8, pitch=18, skip=[(x - 12, x + 26) for x in markers.values()] + [(360, 460), (650, 720), (960, 1110)])
    for x in markers.values():
        mask[64:100, x:x + 20] = 255  # printed letter sitting on the line
    for x in (370, 420, 660, 690, 970, 1020, 1060):
        cv2.line(mask, (x + 30, 20), (x, 130), 255, 7)  # tall handwritten strokes
    mask[58:64, 525:543] = 255  # stamp fragment floating above the line
    crop = np.full((h, w, 3), 235, np.uint8)
    found = guide_line_markers(crop, mask, 3.8)
    assert found and {k: v[0] for k, v in found.items()} == markers
    mask[64:100, 870:890] = 0  # one marker missing: no roles from guessing
    assert guide_line_markers(crop, mask, 3.8) is None


def test_housing_back_serial_needs_two_agreeing_readers(monkeypatch):
    from app import arabic_ocr, housing_back

    def line(text, x1, y1, x2, y2, confidence=.97):
        return {'text': text, 'confidence': confidence, 'box': [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}
    image = np.full((600, 900, 3), 240, np.uint8)
    lines = [line('التسلسل', 230, 110, 340, 150), line('٥١٦٣٣٤٧', 60, 175, 360, 225)]
    focused = []
    monkeypatch.setattr(arabic_ocr, 'recognize_crops', lambda crops, language='arabic': focused)
    focused[:] = [{'text': '٥١٦٣٣٤٧', 'confidence': .95}]
    agreed = housing_back.serial_field(image, lines)
    assert agreed['value'] == '5163347' and agreed['status'] == 'uncertain' and agreed['agreement']
    # The stamp hides the last digit from the full-card pass: never choose, show both.
    lines[1] = line('٢٤٨١٩٠', 60, 175, 330, 225)
    focused[:] = [{'text': '٢٤٨١٩٠٩', 'confidence': .9}]
    split = housing_back.serial_field(image, lines)
    assert split['value'] == '' and split['status'] == 'conflict'
    assert [c['value'] for c in split['candidates']] == ['248190', '2481909']
    assert housing_back.serial_field(image, [line('نموذج', 700, 40, 850, 80)]) is None


def digit_reading(value, probabilities, sizes=None):
    sizes = sizes or [(40, 50)] * len(value)
    x, digits = 0, []
    for ch, p, (w, h) in zip(value, probabilities, sizes):
        digits.append({'digit': int(ch), 'probability': p, 'alternatives': [], 'box': [x, 0, x + w, h]})
        x += w + 10
    return {'value': value, 'confidence': float(np.prod(probabilities) ** (1 / len(value))), 'digits': digits,
            'box': [[0, 0], [9, 0], [9, 9], [0, 9]]}


def test_one_weak_digit_never_overrules_the_other_reader():
    from app import understanding as u
    from app.housing_handwriting import combine_digit_readings
    fields = {'mahalla_number': u.field('mahalla_number', '673', .9, None, 'housing_ink_components', 'uncertain')}
    # «٦٧٣» broken into pieces read as «69771»: two digits at 61% and 65%.
    combine_digit_readings(fields, {'mahalla_number': digit_reading('69771', [1, .61, .99, .65, 1])})
    f = fields['mahalla_number']
    assert f['value'] == '673' and f['status'] == 'conflict' and '69771' in [c['value'] for c in f['candidates']]


def test_a_digit_fused_with_a_stamp_leaves_the_field_blank_with_a_suggestion():
    from app.housing_handwriting import combine_digit_readings, mark_occluded
    readings = {'street': digit_reading('47', [1, 1]), 'form_number': digit_reading('3184', [1, 1, 1, 1]),
                'house_number': digit_reading('95', [.61, 1], sizes=[(118, 105), (42, 42)])}
    mark_occluded(readings)
    assert readings['house_number'].get('occluded') and not readings['street'].get('occluded')
    fields = {}
    combine_digit_readings(fields, {'house_number': readings['house_number']})
    f = fields['house_number']
    assert f['value'] == '' and f['status'] == 'unreadable' and f['candidates'][0]['value'] == '95' and 'ختم' in f['note']


def test_flagged_blank_replaces_only_an_empty_field():
    from app import understanding as u
    from app.focused_fields import merge_refined
    flagged = u.field('house_number', '', None, None, 'eastern_digit_model', 'unreadable', note='ختم يغطي الرقم',
                      candidates=[{'value': '95'}])
    empty = merge_refined([u.field('house_number')], {'house_number': flagged})
    assert empty[0]['status'] == 'unreadable' and empty[0]['candidates'][0]['value'] == '95'
    kept = merge_refined([u.field('house_number', '15', None, None, 'manual', 'manual')], {'house_number': flagged})
    assert kept[0]['value'] == '15'


@needs_model
def test_a_stamp_dot_above_a_digit_is_not_a_zero():
    mask = np.pad(written('5'), ((0, 0), (0, 60)))
    ys, xs = np.nonzero(mask)
    cv2.circle(mask, (int(xs.max()) + 14, int(ys.min()) - 6), 5, 255, -1)  # speck above the digit's top
    assert hd.read_digits(mask=mask, pen_width=6)['value'] == '5'


@needs_model
def test_a_digit_broken_by_a_faint_joint_is_read_whole():
    mask = written('673')
    x = np.nonzero(mask)[1].max() - 45
    mask[52:55, x:] = 0  # the ٣ loses a thin band, as a faint pen joint does on a photo
    assert len(hd.pieces(mask, 6)) > 3
    assert hd.read_digits(mask=mask, pen_width=6)['value'] == '673'


def test_pen_ink_is_separated_from_a_lighter_stamp_of_the_same_hue():
    rgb = np.full((120, 200, 3), 235, np.uint8)
    mask = np.zeros((120, 200), np.uint8)
    for y in (40, 60, 80):  # stamp lettering: light violet-blue
        cv2.line(rgb, (10, y), (190, y), (150, 150, 215), 4)
        cv2.line(mask, (10, y), (190, y), 255, 4)
    cv2.line(rgb, (100, 5), (120, 115), (25, 30, 110), 6)  # the pen stroke of «١»: dark blue, crossing it
    cv2.line(mask, (100, 5), (120, 115), 255, 6)
    layer = hd.pen_layer(rgb, mask)
    ys, xs = np.nonzero(layer)
    assert layer.sum() and xs.min() >= 90 and xs.max() <= 130 and ys.max() - ys.min() > 90
    assert hd.pen_layer(np.full((120, 200, 3), (25, 30, 110), np.uint8), mask) is None  # one ink: nothing to separate


def test_missing_markers_are_completed_from_the_printed_form_layout():
    from app.housing_handwriting import MARKER_TEMPLATE, template_markers
    h, w = 120, 700
    crop = np.full((h, w, 3), 235, np.uint8)
    for key, ratio in MARKER_TEMPLATE.items():
        x = int(ratio * w)
        cv2.rectangle(crop, (x - 5, 50), (x + 5, 68), (30, 30, 30), -1)  # a small printed letter
    known = {'د': (int(MARKER_TEMPLATE['د'] * w) - 5, 50, 11, 19, 180)}  # only د was recognised by OCR
    found = template_markers(crop, known)
    assert found and {k: round((v[0] + v[2] / 2) / w, 2) for k, v in found.items()} == {k: round(r, 2) for k, r in MARKER_TEMPLATE.items()}
    assert template_markers(crop, {}) is None  # no recognised letter: no roles from position alone
    blank = np.full((h, w, 3), 235, np.uint8)
    cv2.rectangle(blank, (known['د'][0], 50), (known['د'][0] + 10, 68), (30, 30, 30), -1)
    assert template_markers(blank, known) is None  # the other markers are not where the form puts them


def test_a_zero_must_be_written_in_the_number_s_ink_and_never_lead():
    rgb = np.full((60, 200, 3), 235, np.uint8)
    blue, black = (40, 60, 170), (30, 30, 30)

    def piece(x, colour, zero=False):
        size = 8 if zero else 30
        box = [x, 15, x + size, 15 + size]
        cv2.rectangle(rgb, (box[0], box[1]), (box[2] - 1, box[3] - 1), colour, -1)
        return {'digit': 0 if zero else 4, 'probability': .9, 'box': box,
                '_piece': {'box': box, 'mask': np.full((size, size), 255, np.uint8)}}
    digits = [piece(10, blue, zero=True), piece(30, blue), piece(70, blue), piece(110, blue, zero=True), piece(130, black, zero=True)]
    kept = hd.plausible_zeros(digits, rgb)
    # leading ٠ dropped, the blue ٠ after the digits kept, the black printed dot dropped
    assert [d['digit'] for d in kept] == [4, 4, 0] and kept[-1]['box'][0] == 110
    assert [d['digit'] for d in hd.plausible_zeros([dict(d) for d in digits])] == [4, 4, 0, 0]  # colours unknown: only the lead rule


@needs_model
def test_the_marker_line_wins_over_a_heavier_stamp_arc_and_a_clean_number_keeps_its_confidence():
    digits = written('11')  # the number on the printed line (rows 30–90)
    mask = np.zeros((220, digits.shape[1] + 200), np.uint8)
    mask[100:220, 100:100 + digits.shape[1]] = digits[:120]
    cv2.ellipse(mask, (mask.shape[1] // 2, 40), (mask.shape[1] // 2 - 5, 45), 0, 180, 360, 255, 14)  # heavy stamp arc above
    marker_y = 160  # the printed د beside the number sits on its line
    reading = hd.read_digits(mask=mask, pen_width=6, line_y=marker_y)
    assert reading['value'] == '11'
    assert reading['confidence'] > .9 and reading['overlap'] < .35  # the arc is beside the digits, not over them


def test_blurred_markers_are_found_on_the_form_layout_without_being_read():
    from app.housing_handwriting import MARKER_TEMPLATE, label_anchored_markers
    h, w = 114, 724
    crop = np.full((h, w, 3), 232, np.uint8)
    cv2.line(crop, (20, 66), (w - 20, 66), (70, 70, 70), 2)  # the dotted line, fused into a stroke by blur
    places = {'م': 692, 'ز': 522, 'د': 358}  # typical marker positions (.96 / .72 / .49)
    for x in places.values():
        cv2.rectangle(crop, (x, 52), (x + 10, 68), (40, 40, 40), -1)
    cv2.rectangle(crop, (317, 64), (327, 76), (40, 40, 40), -1)  # a digit fragment below the line, nearer د's place
    crop = cv2.GaussianBlur(crop, (0, 0), 1.6)
    found = label_anchored_markers(crop)
    assert found and all(abs(found[k][0] - x) <= 3 for k, x in places.items())  # blur spreads edges by a pixel
    assert label_anchored_markers(np.full((h, w, 3), 232, np.uint8)) is None
    assert set(MARKER_TEMPLATE) == set(places)


def test_a_readable_full_address_line_wins_over_guessed_marker_places(monkeypatch):
    from app import housing_handwriting as hh
    guessed = []
    monkeypatch.setattr(hh, 'address_markers', lambda image, region, partial=False: (np.full((120, 740, 3), 235, np.uint8), {}))
    monkeypatch.setattr(hh, 'guide_line_markers', lambda crop, mask, pen_width: None)
    monkeypatch.setattr(hh, 'label_anchored_markers', lambda crop: guessed.append(1) or {'م': (1, 1, 1, 1, 1)})
    image = np.full((600, 1000, 3), 235, np.uint8)
    region = {'box': [[0, 450], [760, 450], [760, 570], [0, 570]]}
    line = {'text': '٤٣٠٢٨٠٦٥٧٠٠', 'box': [[150, 500], [700, 500], [700, 540], [150, 540]]}  # «43 د 28 ز 657 م» read as one line
    mask = np.zeros(image.shape[:2], np.uint8)
    assert hh.find_address_markers(image, region, mask, 3.0, [line])[1] is None and not guessed
    assert hh.find_address_markers(image, region, mask, 3.0, [])[1] and guessed  # nothing read: the layout guess is the last resort
