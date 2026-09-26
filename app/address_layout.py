"""Housing address numbers when the printed م / ز / د markers were not recognised.

Two independent readings of the same address row:
  1. Coloured pen (blue/red) ink is separated from ALL black print by colour, split
     into its separate numbers by the wide gaps between them, and read right to
     left in the card's fixed printed order: المحلة (م) then الزقاق (ز) then الدار (د).
     Each group is read by the digit model and by the general OCR.
  2. The full-line OCR digits of the row (markers usually come out as ٠, e.g.
     «٥٧٠٣٨٠٤٦٠٠» = 57 د 38 ز 460 م), split only when exactly one split exists.
Readers vote. Roles taken from the printed order are marked approximate unless two
readers agree. Nothing is completed or guessed.
"""
import re

import cv2
import numpy as np

from . import arabic_ocr, handwritten_digits as hd

ROLE_ORDER = ('mahalla_number', 'street', 'house_number')  # printed right to left: م … ز … د


def colour_pen_mask(rgb, pen_width=None):
    """Mask of a clearly coloured pen (blue or red) only, excluding all black print.

    Returns (mask, colour) or (None, None) for black/grey handwriting, where printed
    text cannot be separated by colour.
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, sat, val = (hsv[:, :, i].astype(np.int16) for i in range(3))
    masks = {'blue': (hue >= 95) & (hue <= 140) & (sat > 60) & (val < 225),
             'red': ((hue <= 10) | (hue >= 165)) & (sat > 80) & (val < 235)}
    colour, mask = max(masks.items(), key=lambda kv: kv[1].sum())
    if mask.sum() < .004 * mask.size:
        return None, None
    mask = mask.astype(np.uint8) * 255
    if pen_width:
        # Drop thin stamp lines of the same colour, as in handwritten_digits.pen_mask().
        core = max(1.6, .42 * pen_width)
        radius = max(1, int(round(core)))
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        mask = cv2.bitwise_and(cv2.dilate(((distance >= core) * 255).astype(np.uint8), kernel), mask)
    return mask, colour


def number_groups(mask, pen_width, max_groups=4):
    """Split one written line into its separate numbers by the wide gaps between them.

    Returns [(x1, x2)] from right to left.
    """
    found = hd.pieces(mask, pen_width)
    if not found:
        return []
    found, digit_height, _ = hd.on_one_line(found)
    full = sorted([p for p in found if p['box'][3] - p['box'][1] >= .45 * digit_height], key=lambda p: p['box'][0])
    if not full:
        return []
    groups = [[full[0]['box'][0], full[0]['box'][2]]]
    for p in full[1:]:
        if p['box'][0] - groups[-1][1] > 1.1 * digit_height:
            groups.append([p['box'][0], p['box'][2]])
        else:
            groups[-1][1] = max(groups[-1][1], p['box'][2])
    if len(groups) > max_groups:
        return []
    pad = int(.35 * digit_height)
    return [(max(0, a - pad), min(mask.shape[1], b + pad)) for a, b in reversed(groups)]


def parse_address_digits(text):
    """Split the full-line OCR digits of the address row, e.g. «٥٧٠٣٨٠٤٦٠٠».

    The line comes left to right: house, د, street, ز, mahalla, م, and the markers are
    usually read as ٠. Returns {role: number} only when exactly one split is possible.
    """
    from .focused_fields import normalize
    digits = re.sub(r'\D', '', normalize(text))
    n = len(digits)
    parses = set()
    for a in range(1, 5):
        for b in range(1, 5):
            c = n - a - b - 3
            if not 1 <= c <= 4:
                continue
            if digits[a] != '0' or digits[a + 1 + b] != '0' or digits[-1] != '0':
                continue
            house, street, mahalla = digits[:a], digits[a + 1:a + 1 + b], digits[a + 2 + b:n - 1]
            if any(x.startswith('0') for x in (house, street, mahalla)):
                continue
            parses.add((mahalla, street, house))
    return dict(zip(ROLE_ORDER, parses.pop())) if len(parses) == 1 else None


def address_line_text(lines, region):
    """Digits of the full-line OCR reading(s) on the address row, ordered left to right."""
    from .focused_fields import box_of
    box = np.asarray(region['box'])
    parts = []
    for line in lines:
        b = box_of(line)
        if b is None or not box[:, 1].min() <= b[:, 1].mean() <= box[:, 1].max():
            continue
        digits = re.sub(r'[^0-9٠-٩۰-۹]', '', line.get('text', ''))
        if len(digits) >= 3 and b[:, 0].min() < box[:, 0].max():
            parts.append((float(b[:, 0].min()), digits))
    return ''.join(d for _, d in sorted(parts))


def read_by_layout(image, region, lines, pen_width):
    """Readings per role from the coloured-ink groups and from the full-line OCR."""
    from .focused_fields import crop_box, normalize
    from .housing_handwriting import ink_variants, original_box
    crop = crop_box(image, region['box'])
    out = {}
    mask, _ = colour_pen_mask(crop, pen_width)
    if mask is not None:
        groups = number_groups(mask, pen_width)
        if len(groups) == 3:
            for role, (x1, x2) in zip(ROLE_ORDER, groups):
                model = hd.read_digits(mask=mask[:, x1:x2], pen_width=pen_width)
                reads = arabic_ocr.recognize_crops([work for _, work in ink_variants(crop[:, x1:x2])])
                values = [re.sub(r'\D', '', normalize(o['text'])) for o in reads if o['confidence'] >= .5]
                values = [v for v in values if 1 <= len(v) <= 5 and not v.startswith('0')]
                out[role] = {'model': model, 'ocr': max(set(values), key=values.count) if values else None,
                             'box': original_box((x1, 0, x2, crop.shape[0]), region, crop)}
    parsed = parse_address_digits(address_line_text(lines, region))
    if parsed:
        for role, value in parsed.items():
            out.setdefault(role, {'model': None, 'ocr': None, 'box': region['box']})['line'] = value
    return out


def layout_fields(fields, readings):
    """Fill empty address roles from layout readings; agreement raises confidence."""
    from .housing_handwriting import digit_vote
    from .understanding import field
    # The address-area reading (crop of the whole written line) is another full-line
    # reading: «١٣٠٢٦٠٦٧٣٠» = 13 د 26 ز 673 م.
    address = fields.get('address') or {}
    texts = [address.get('value'), address.get('raw_text')] + [c.get('value') for c in address.get('candidates', [])]
    parses = [p for p in (parse_address_digits(t) for t in texts if t) if p]
    if parses and all(p == parses[0] for p in parses):
        readings = dict(readings)
        for role, value in parses[0].items():
            entry = dict(readings.get(role) or {'model': None, 'ocr': None, 'box': address.get('box')})
            entry.setdefault('line', value)
            if entry['line'] != value:
                entry['line_area'] = value
            else:
                entry['line_area'] = None
            readings[role] = entry
    for role, r in readings.items():
        existing = fields.get(role, {})
        if existing.get('value') or existing.get('verified') or existing.get('method') == 'manual':
            continue
        model = r.get('model') or {}
        votes = {}
        for engine, value, conf in [('eastern_digit_model', model.get('value'), model.get('confidence') or 0),
                                    ('ppocr_v5_arabic', r.get('ocr'), .8), ('full_line_ocr', r.get('line'), .8),
                                    ('address_area_ocr', r.get('line_area'), .8)]:
            if value:
                votes.setdefault(value, []).append((engine, conf))
        if not votes:
            continue
        if model.get('value'):
            for other in {r.get('ocr'), r.get('line')} - {None, model['value']}:
                if digit_vote(model, other) == other:
                    votes[other].append(('eastern_digit_model_alternative', .5))
        ranked = sorted(votes.items(), key=lambda kv: (len({e for e, _ in kv[1]}), max(c for _, c in kv[1])), reverse=True)
        value, support = ranked[0]
        readers = {e for e, _ in support if e != 'eastern_digit_model_alternative'}
        agree = len(readers) >= 2
        conflict = len(ranked) > 1 and not agree
        confidence = round(min(.95, max(c for _, c in support) + (.1 if agree else 0)) * (1 if agree else .85), 3)
        candidates = [{'value': v, 'confidence': round(max(c for _, c in s), 3), 'engine': '+'.join(sorted({e for e, _ in s}))}
                      for v, s in ranked]
        fields[role] = field(role, value, confidence, r.get('box'), 'address_layout',
                             'uncertain' if agree else 'conflict' if conflict else 'approximate',
                             approximate=not agree, role_from_order=True, candidates=candidates, agreement=agree,
                             note='لم تُقرأ الرموز المطبوعة م/ز/د؛ حُدد الحقل من ترتيبها الثابت في البطاقة (المحلة ثم الزقاق ثم الدار). '
                                  + ('اتفق قارئان مستقلان على الرقم.' if agree else 'راجع الرقم مع الصورة.'))
    return fields
