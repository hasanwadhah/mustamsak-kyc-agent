"""Cards photographed small, faded or on a busy background (synthetic images only)."""
import cv2
import numpy as np

from app import handwritten_digits as hd, vision
from app.focused_fields import plausible_office


def pale_card():
    """Pale green paper with a darker green seal ring and faded red handwriting."""
    rgb = np.full((300, 600, 3), (225, 236, 215), np.uint8)
    cv2.circle(rgb, (300, 150), 110, (170, 205, 120), 18)  # the seal: darker green, not ink
    for x in (120, 200, 280):
        cv2.line(rgb, (x, 100), (x + 25, 190), (228, 180, 172), 7)  # faded red strokes, as pale as on the real photo
    return rgb


def test_faded_coloured_ink_is_found_but_the_green_seal_is_not():
    rgb = pale_card()
    faint = hd.faint_ink(rgb)
    assert faint[140:150, 125:150].any() and faint[140:150, 205:230].any()  # the red strokes
    assert not faint[140:160, 395:420].any() and not faint[30:50, 290:310].any()  # the seal ring
    normal, _ = hd.pen_mask(rgb)
    extended, _ = hd.pen_mask(rgb, faint=True)
    assert normal[100:200, 110:320].sum() < extended[100:200, 110:320].sum()  # a second pass, not the default


def test_only_small_crops_are_enlarged():
    small = np.zeros((242, 382, 3), np.uint8)
    assert vision.readable_size(small).shape[1] == 1000
    normal = np.zeros((600, 899, 3), np.uint8)
    assert vision.readable_size(normal) is normal  # a normal card is read exactly as photographed


def test_office_names_are_words_not_noise():
    assert plausible_office('الغزالية') and plausible_office('٩ نيسان') and plausible_office('الزهور')
    assert not plausible_office('١عه') and not plausible_office('Co') and not plausible_office('ال')


def test_tilt_is_measured_from_the_printed_lines_and_undone():
    def line(angle, y):
        a = np.radians(angle)
        x0, x1 = 100, 500
        return {'text': 'نص', 'box': [[x0, y], [x1, y + (x1 - x0) * np.tan(a)], [x1, y + 30 + (x1 - x0) * np.tan(a)], [x0, y + 30]]}
    lines = [line(4, y) for y in (50, 150, 250)] + [{'text': 'قصير', 'box': [[0, 0], [20, 5], [20, 25], [0, 20]]}]
    assert abs(vision.text_angle(lines, 800) - 4) < .1
    assert vision.text_angle(lines[:2], 800) == 0.0  # too little evidence: leave the card as it is
    image = np.full((300, 600, 3), 240, np.uint8)
    cv2.line(image, (100, 100), (500, int(100 + 400 * np.tan(np.radians(4)))), (0, 0, 0), 3)
    straight = vision.straighten(image, 4)
    ys, xs = np.nonzero(straight[:, :, 0] < 100)
    assert np.ptp(ys) < 8  # the line is horizontal again


def test_even_lighting_restores_contrast_of_a_washed_out_photo():
    image = np.full((200, 300, 3), 225, np.uint8)
    cv2.putText(image, '4 2', (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 3, (120, 120, 170), 8)
    washed = np.clip(image.astype(np.float32) * 1.15 + 20, 0, 255).astype(np.uint8)
    fixed = vision.even_lighting(washed)
    assert int(fixed.min()) < int(washed.min()) and fixed[5, 5, 0] >= 225  # darker ink, paper stays white


def test_blurred_labels_still_place_the_rows_from_the_printed_form():
    from app.focused_fields import housing_regions, HOUSING_TEMPLATE_ROWS

    def line(text, y, x1=700, x2=950):
        return {'text': text, 'confidence': .5, 'box': [[x1, y - 12], [x2, y - 12], [x2, y + 12], [x1, y + 12]]}
    image = np.full((674, 1000, 3), 235, np.uint8)
    # Garbled labels as OCR reads them on a blurred card, at typical heights.
    lines = [line('مطب مطوسة', 378), line('لصمرب الأسرة', 448), line('قر السارة', 589), line('٤٣٠٢٨٠٦٥٧٠٠', 520, 150, 700)]
    rows = {r['key']: r for r in housing_regions(image, lines, 'front')}
    assert set(rows) == set(HOUSING_TEMPLATE_ROWS) and all(r['layout_uncertain'] for r in rows.values())
    name = np.asarray(rows['name']['box'])
    assert name[:, 1].min() < 448 < name[:, 1].max()  # snapped to the garbled «اسم رب الاسرة» label
    assert not housing_regions(image, [line('مجرد نص', 400)], 'front')  # no sign of the card: no rows invented
