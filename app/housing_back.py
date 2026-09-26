"""The printed serial number (التسلسل) on the back of the housing card.

It is printed in Arabic-Indic digits under the label «التسلسل /», and the office
stamp often covers its last digits. Two readings of the same row are compared: the
full-card OCR lines and a focused OCR of the row itself (with room on both sides for
digits the full-card pass dropped). Agreement gives a value to check; disagreement
is a visible conflict with both readings. No digit is ever completed or guessed.
"""
import re

import numpy as np

from . import arabic_ocr

LABEL = 'التسلسل'


def _digits(text):
    from .focused_fields import normalize
    return re.sub(r'\D', '', normalize(text))


def _digit_line(line):
    """A line that is (almost) only digits: the printed number, not a label."""
    text = re.sub(r'[\s/.:\-]', '', str(line.get('text', '')))
    digits = _digits(text)
    return len(digits) >= 2 and len(digits) >= .7 * len(text)


def serial_field(image, lines):
    """{'key': 'card_serial', …} read from the row under the «التسلسل» label, or None without that label."""
    from .focused_fields import box_of, crop_box, normalize
    from .housing_handwriting import ink_variants
    from .textmatch import contains_phrase
    from .understanding import field
    labels = [l for l in lines if box_of(l) is not None and contains_phrase(normalize(l.get('text', '')), LABEL, limit=1)]
    if not labels:
        return None
    lb = box_of(labels[0])
    top, bottom = lb[:, 1].min(), lb[:, 1].max()
    lh = max(8.0, bottom - top)
    below = [l for l in lines if box_of(l) is not None and _digit_line(l)
             and bottom - .3 * lh < box_of(l)[:, 1].mean() < bottom + 4 * lh
             and box_of(l)[:, 0].mean() < lb[:, 0].max() + 2 * lh]
    if not below:
        return field('card_serial', note='لم يُقرأ رقم تحت «التسلسل»؛ أدخله من الصورة.')
    # The row nearest the label; parts of one printed number share its height.
    first_y = min(box_of(l)[:, 1].mean() for l in below)
    row = sorted((l for l in below if abs(box_of(l)[:, 1].mean() - first_y) < .6 * lh), key=lambda l: box_of(l)[:, 0].min())
    full_line = ''.join(_digits(l['text']) for l in row)
    boxes = np.vstack([box_of(l) for l in row])
    h, w = image.shape[:2]
    x1, x2 = max(0, boxes[:, 0].min() - 2 * lh), min(w - 1, boxes[:, 0].max() + 3 * lh)
    y1, y2 = max(0, boxes[:, 1].min() - .3 * lh), min(h - 1, boxes[:, 1].max() + .3 * lh)
    box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    crop = crop_box(image, box)
    reads = arabic_ocr.recognize_crops([work for _, work in ink_variants(crop)]) if crop.size else []
    focused = [_digits(r['text']) for r in reads if r['confidence'] >= .6 and len(_digits(r['text'])) >= 3]
    focused_value = max(set(focused), key=focused.count) if focused else ''
    line_conf = min(float(l.get('confidence') or 0) for l in row)
    candidates = [{'value': full_line, 'confidence': round(line_conf, 3), 'engine': 'full_line_ocr'}]
    if focused_value and focused_value != full_line:
        candidates.append({'value': focused_value, 'confidence': max(r['confidence'] for r in reads if _digits(r['text']) == focused_value),
                           'engine': 'serial_row_ocr'})
    if focused_value == full_line:
        return field('card_serial', full_line, round(line_conf, 3), box, 'serial_two_readers', 'uncertain', agreement=True,
                     candidates=candidates, note='قرأ محركان الرقم المطبوع نفسه؛ راجعه مع الصورة، فالختم قد يغطي رقمًا.')
    if focused_value and len(focused_value) != len(full_line):
        # One reader saw more digits (a digit under the stamp) — do not choose; show both.
        return field('card_serial', '', None, box, 'serial_two_readers', 'conflict', candidates=candidates,
                     note='اختلف عدد الأرقام بين القراءتين؛ قد يغطي الختم رقمًا. اختر القيمة الصحيحة من الصورة.')
    return field('card_serial', full_line, round(min(line_conf, .8), 3), box, 'full_line_ocr',
                 'conflict' if focused_value else 'approximate', approximate=True, candidates=candidates,
                 note='قراءة واحدة للرقم المطبوع أو قراءتان مختلفتان؛ قارنها بالصورة.')
