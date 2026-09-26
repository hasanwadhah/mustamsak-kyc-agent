"""Read handwritten Eastern Arabic numbers (٠١٢٣٤٥٦٧٨٩) on Iraqi forms, one digit at a time.

General OCR models misread Iraqi handwritten digits (٢ written like "c" and ٤ like
"ع" are confused, short groups such as ٤٢ are dropped). This module:
  1. isolates pen ink (blue / black / red) from paper, security print and thin stamp lines,
  2. removes printed guide dots, splits the ink into digit pieces,
  3. recognises ٠ as a solid dot by size and shape, and ١..٩ with a small CNN trained on
     real handwriting (MADBase, 700 writers) plus synthetic Iraqi-style strokes
     (scripts/train_digit_cnn.py; 99% on MADBase's held-out test set), run here in numpy.
     A synthetic-only MLP (scripts/train_eastern_digits.py) is the fallback,
  4. composes the number left to right (digits are written left to right).
It reports per-digit probabilities; it never guesses a digit it could not see.
"""
import itertools
from pathlib import Path

import cv2
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / 'models' / 'eastern_digits.npz'
# Preferred: a CNN trained on real handwriting (MADBase) + synthetic strokes
# (scripts/train_digit_cnn.py), run here in numpy. The MLP is the synthetic-only fallback.
CNN_PATH = Path(__file__).resolve().parents[1] / 'models' / 'eastern_digits_cnn.npz'
CLASSES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 'noise']
_model = None
_cnn = None
# When a list, read_digits() appends every digit piece it classifies ({'mask', 'digit',
# 'probability', 'call'}), so its pieces can be saved as training samples
# (scripts/export_digit_samples.py, app/learning.py). 'call' matches the reading's 'call'.
collector = None
_calls = itertools.count(1)
_HOG = cv2.HOGDescriptor((28, 28), (14, 14), (7, 7), (7, 7), 9)


def available():
    return CNN_PATH.exists() or MODEL_PATH.exists()


def cnn():
    global _cnn
    if _cnn is None:
        with np.load(CNN_PATH, allow_pickle=False) as data:
            _cnn = [(data[f'p{i}_weight'], data[f'p{i}_bias']) for i in range(6)]
    return _cnn


def _conv(x, w, b):
    # x: (C, H, W), w: (O, C, 3, 3), same padding.
    windows = np.lib.stride_tricks.sliding_window_view(np.pad(x, ((0, 0), (1, 1), (1, 1))), (3, 3), axis=(1, 2))
    return np.maximum(np.einsum('chwij,ocij->ohw', windows, w, optimize=True) + b[:, None, None], 0)


def _pool(x):
    c, h, w = x.shape
    return x.reshape(c, h // 2, 2, w // 2, 2).max(axis=(2, 4))


def cnn_logits(image):
    (w1, b1), (w2, b2), (w3, b3), (w4, b4), (w5, b5), (w6, b6) = cnn()
    x = image[None].astype(np.float32) / 255.0
    x = _pool(_conv(_conv(x, w1, b1), w2, b2))
    x = _pool(_conv(_conv(x, w3, b3), w4, b4))
    x = np.maximum(w5 @ x.reshape(-1) + b5, 0)
    return w6 @ x + b6


def model():
    global _model
    if _model is None:
        with np.load(MODEL_PATH, allow_pickle=False) as data:
            _model = {k: data[k] for k in data.files}
    return _model


def normalized(mask, size=28):
    """Crop to ink, keep aspect ratio (a ١ stays narrow), centre in a square."""
    ys, xs = np.nonzero(mask)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    side = int(max(h, w) * 1.2) + 2
    square = np.zeros((side, side), np.uint8)
    y, x = (side - h) // 2, (side - w) // 2
    square[y:y + h, x:x + w] = crop
    return cv2.resize(square, (size, size), interpolation=cv2.INTER_AREA)


def features(mask):
    image = normalized(mask)
    ys, xs = np.nonzero(mask)
    aspect = (ys.max() - ys.min() + 1) / (xs.max() - xs.min() + 1)
    small = cv2.resize(image, (14, 14), interpolation=cv2.INTER_AREA).ravel() / 255.0
    return np.concatenate([_HOG.compute(image).ravel(), small, [np.log(aspect)]]).astype(np.float32)


def probabilities(mask):
    if CNN_PATH.exists():
        logits = cnn_logits(normalized(mask))
        e = np.exp(logits - logits.max())
        return e / e.sum()
    m = model()
    x = (features(mask) - m['mean']) / m['scale']
    layers = sorted(k for k in m if k.startswith('w'))
    for i, key in enumerate(layers):
        x = x @ m[key] + m['b' + key[1:]]
        if i < len(layers) - 1:
            x = np.maximum(x, 0)
    x = np.exp(x - x.max())
    return x / x.sum()


def faint_ink(rgb):
    """Coloured ink that is only slightly darker than its surroundings (faded red or blue pen).

    Relative to each image's own background, not fixed colour thresholds: a pixel is ink when
    it is darker than the local background AND shifted towards red or towards blue. The
    green seal's edges shift towards green, so they are not taken for ink. Development card: pale
    red digits on a low-resolution photo was only 24–32 levels darker than the paper.
    """
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    h, w = lab.shape[:2]
    scale = min(1.0, 500 / max(h, w))
    small = cv2.resize(lab, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    k = min(51, max(15, int(min(small.shape[:2]) / 6) | 1))  # wider than a digit, so digits do not tint it
    background = np.dstack([cv2.medianBlur(np.ascontiguousarray(small[:, :, i]), k) for i in range(3)])
    background = cv2.resize(background, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.int16)
    lab = lab.astype(np.int16)
    darker = background[:, :, 0] - lab[:, :, 0]
    redder = lab[:, :, 1] - background[:, :, 1]
    bluer = background[:, :, 2] - lab[:, :, 2]
    return (darker > 12) & ((redder > 12) | (bluer > 12))


def local_mask(rgb, darkness=22):
    """Ink mask of one field strip, from the strip's own background and stroke width.

    The card-level mask keeps strokes at least as thick as the card's typical pen. A number
    written in a thinner or paler pen (grey pencil next to thick red digits on a development card)
    falls apart under it: a five-digit number was read as three digits. Returns (mask, stroke width).
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    background = cv2.medianBlur(gray, min(31, max(15, (min(gray.shape) // 3) | 1))).astype(np.int16)
    ink = (((background - gray.astype(np.int16)) > darkness) | faint_ink(rgb)).astype(np.uint8) * 255
    distance = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    width = float(np.median(distance[distance > 0]) * 2) if distance.any() else 3.0
    core = max(1.2, .42 * width)
    radius = max(1, int(round(core)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.bitwise_and(cv2.dilate(((distance >= core) * 255).astype(np.uint8), kernel), ink), width


def pen_mask(rgb, faint=False):
    """Pen ink: locally dark, or saturated blue / red; thin stamp lines and guide dots removed.

    faint=True also takes faded coloured ink (faint_ink). It is a second pass for numbers
    the normal mask finds nothing in: added to every card, the extra ink merged digits
    that were read correctly before («٦٧٣» → «63»).
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, sat, val = (hsv[:, :, i].astype(np.int16) for i in range(3))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    k = max(15, (min(gray.shape) // 4) | 1)
    background = cv2.medianBlur(gray, min(k, 31)).astype(np.int16)
    ink = ((background - gray.astype(np.int16)) > 40) | ((hue >= 95) & (hue <= 140) & (sat > 60) & (val < 225)) | \
          (((hue <= 10) | (hue >= 165)) & (sat > 80))
    if faint:
        ink = ink | faint_ink(rgb)
    ink = ink.astype(np.uint8) * 255
    distance = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    width = float(np.median(distance[distance > 0]) * 2) if distance.any() else 3.0
    core = max(1.6, .42 * width)
    radius = max(1, int(round(core)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    # Keep only strokes at least as thick as a pen line; thin stamp text and dotted lines drop out.
    return cv2.bitwise_and(cv2.dilate(((distance >= core) * 255).astype(np.uint8), kernel), ink), width


def pieces(mask, pen_width):
    """Connected ink pieces, with pieces stacked in the same column merged into one digit."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    min_side = 1.4 * pen_width
    items = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        if max(w, h) < min_side or area < 1.5 * pen_width ** 2:
            continue  # printed guide dot or speck
        items.append({'box': [x, y, x + w, y + h], 'area': area, 'labels': [i]})
    items.sort(key=lambda p: p['box'][0])
    # Attach a small detached fragment (a broken stroke) to the digit it sits inside.
    # Two full-size pieces are never merged: slanted digits overlap in x (٦ under ٧).
    merged = []
    for p in sorted(items, key=lambda p: -p['area']):
        host = None
        for q in merged:
            overlap = min(p['box'][2], q['box'][2]) - max(p['box'][0], q['box'][0])
            if p['area'] < .3 * q['area'] and overlap > .7 * (p['box'][2] - p['box'][0]) and \
                    p['box'][1] >= q['box'][1] - .3 * (q['box'][3] - q['box'][1]) and \
                    p['box'][3] <= q['box'][3] + .3 * (q['box'][3] - q['box'][1]):
                host = q
                break
        if host is None:
            merged.append(p)
            continue
        host['box'] = [min(p['box'][0], host['box'][0]), min(p['box'][1], host['box'][1]),
                       max(p['box'][2], host['box'][2]), max(p['box'][3], host['box'][3])]
        host['area'] += p['area']; host['labels'] += p['labels']
    merged.sort(key=lambda p: p['box'][0])
    for p in merged:
        p['mask'] = (np.isin(labels, p['labels']).astype(np.uint8) * 255)[p['box'][1]:p['box'][3], p['box'][0]:p['box'][2]]
    return merged


def split_touching(piece, digit_height):
    """Split a piece that is too wide for one digit at its thinnest column."""
    mask = piece['mask']
    h, w = mask.shape
    if w < 1.25 * digit_height:
        return [piece]
    profile = (mask > 0).sum(axis=0).astype(float)
    lo, hi = int(.3 * w), int(.7 * w)
    cut = lo + int(np.argmin(profile[lo:hi]))
    parts = []
    for x1, x2 in ((0, cut), (cut, w)):
        sub = mask[:, x1:x2]
        ys = np.nonzero(sub.any(axis=1))[0]
        if not len(ys):
            continue
        box = [piece['box'][0] + x1, piece['box'][1] + int(ys[0]), piece['box'][0] + x2, piece['box'][1] + int(ys[-1]) + 1]
        parts.append({'box': box, 'area': int((sub > 0).sum()), 'mask': sub[ys[0]:ys[-1] + 1], 'split': True})
    return parts if len(parts) == 2 else [piece]


def best_digit(mask):
    prob = probabilities(mask)
    i = int(np.argmax(prob))
    return CLASSES[i], float(prob[i])


def maybe_split(piece, digit_height):
    """Split touching digits only when the evidence is clear.

    Wide single digits exist (٦ with its flag, ٤ with its long tail), so a piece is
    split only when it is much wider than a digit, the whole piece does not read
    as one confident digit, and both halves do.
    """
    if piece['mask'].shape[1] < 1.5 * digit_height:
        return [piece]
    label, prob = best_digit(piece['mask'])
    if label != 'noise' and prob >= .85:
        return [piece]
    parts = split_touching(piece, digit_height)
    if len(parts) == 2 and all(best_digit(p['mask'])[0] != 'noise' and best_digit(p['mask'])[1] >= .7 for p in parts):
        return parts
    return [piece]


def pen_layer(rgb, mask, pen_lightness=None):
    """Separate handwriting from a same-hue stamp by ink darkness.

    Ballpoint pen ink is darker than stamp-pad ink even when both are blue (development card:
    «١٥» written across the office stamp's lettering). The ink pixels of `mask` are split
    into two colour groups; the group whose lightness is nearest the card's own pen ink
    (measured on its clean digits) is kept, or the darker one without a reference. Hue is
    not used: the same pen looks greener over the seal and bluer over white paper.
    Returns a mask, or None when the ink is one colour (nothing to separate).
    """
    ys, xs = np.nonzero(mask)
    if len(ys) < 60:
        return None
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[ys, xs].astype(np.float32)
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, .5)
    _, labels, centres = cv2.kmeans(lab, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    lightness = centres[:, 0]
    if abs(lightness[0] - lightness[1]) < 20:
        return None
    keep = int(np.argmin(np.abs(lightness - pen_lightness)) if pen_lightness is not None else np.argmin(lightness))
    out = np.zeros(mask.shape, np.uint8)
    chosen = labels.ravel() == keep
    out[ys[chosen], xs[chosen]] = 255
    return cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def guide_dots(found, pen_width):
    """Pieces that are dots of a printed dotted guide line (the line the number is written on).

    Guide dots are one size, on one line, at a regular spacing. On sharp, high-resolution
    photos they are as big as a handwritten ٠, so size alone cannot tell them apart; a
    handwritten zero never sits in an evenly spaced row of equal dots (card 8: its 17 guide
    dots were read as «00000000000000000»).
    """
    def dot_like(p):
        w, h = p['box'][2] - p['box'][0], p['box'][3] - p['box'][1]
        return .6 < w / max(1, h) < 1.7 and p['area'] / max(1, w * h) > .45 and max(w, h) <= 4.5 * pen_width

    def centre(p):
        return (p['box'][0] + p['box'][2]) / 2, (p['box'][1] + p['box'][3]) / 2

    dots = sorted((p for p in found if dot_like(p)), key=lambda p: p['box'][0])
    links = {id(p): set() for p in dots}
    for i, p in enumerate(dots):
        (px, py), size = centre(p), max(p['box'][2] - p['box'][0], p['box'][3] - p['box'][1])
        for q in dots[i + 1:]:
            (qx, qy) = centre(q)
            if qx - px > 4 * size:
                break
            if 1.4 * size <= qx - px and abs(qy - py) < .6 * size and max(p['area'], q['area']) < 1.7 * min(p['area'], q['area']):
                links[id(p)].add(id(q)); links[id(q)].add(id(p))
    by_id = {id(p): p for p in dots}
    seen, chains = set(), []
    for p in dots:
        if id(p) in seen or not links[id(p)]:
            continue
        stack, chain = [id(p)], []
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k); chain.append(by_id[k]); stack.extend(links[k])
        chains.append(chain)
    long_chains = [c for c in chains if len(c) >= 3]
    if not long_chains:
        return []
    # The printed spacing, measured on the long chains; short chains (dots between two
    # digits) count as guide dots only when they have exactly that spacing.
    gaps = []
    for c in long_chains:
        xs = sorted(centre(p)[0] for p in c)
        gaps += [b - a for a, b in zip(xs, xs[1:])]
    spacing = float(np.median(gaps))
    guide = [p for c in long_chains for p in c]
    for c in chains:
        if len(c) < 3:
            xs = sorted(centre(p)[0] for p in c)
            if all(abs((b - a) - spacing) < .25 * spacing for a, b in zip(xs, xs[1:])):
                guide += c
    # A single dot showing between two digits (card 8: between ١ and ٥ of «٢١٥») is a guide
    # dot when it sits on the dotted line, has the dots' size and falls on their printed pitch.
    if len(guide) >= 4:
        gx, gy = np.array([centre(p) for p in guide]).T
        slope, offset = np.polyfit(gx, gy, 1)
        size = float(np.median([max(p['box'][2] - p['box'][0], p['box'][3] - p['box'][1]) for p in guide]))
        area = float(np.median([p['area'] for p in guide]))
        taken = {id(p) for p in guide}
        for p in dots:
            if id(p) in taken or max(p['area'], area) > 1.7 * min(p['area'], area):
                continue
            x, y = centre(p)
            steps = np.min(np.abs(gx - x)) / spacing
            if abs(y - (slope * x + offset)) < .5 * size and steps <= 6 and abs(steps - round(steps)) < .25:
                guide.append(p)
    return guide


def _gap(p, q):
    """Smallest pixel distance between the ink of two pieces."""
    x1, y1 = min(p['box'][0], q['box'][0]), min(p['box'][1], q['box'][1])
    x2, y2 = max(p['box'][2], q['box'][2]), max(p['box'][3], q['box'][3])
    canvas = np.ones((y2 - y1, x2 - x1), np.uint8)
    b = p['box']
    canvas[b[1] - y1:b[3] - y1, b[0] - x1:b[2] - x1][p['mask'] > 0] = 0
    distance = cv2.distanceTransform(canvas, cv2.DIST_L2, 3)
    b = q['box']
    return float(distance[b[1] - y1:b[3] - y1, b[0] - x1:b[2] - x1][q['mask'] > 0].min())


def _joined(p, q):
    x1, y1 = min(p['box'][0], q['box'][0]), min(p['box'][1], q['box'][1])
    x2, y2 = max(p['box'][2], q['box'][2]), max(p['box'][3], q['box'][3])
    mask = np.zeros((y2 - y1, x2 - x1), np.uint8)
    for r in (p, q):
        b = r['box']
        mask[b[1] - y1:b[3] - y1, b[0] - x1:b[2] - x1] |= r['mask']
    return {'box': [x1, y1, x2, y2], 'area': p['area'] + q['area'], 'mask': mask}


def join_fragments(found, digit_height, pen_width):
    """Re-join a digit that the ink mask broke apart (a faint joint lost to the stroke filter).

    Development photo (card 2 again): «٦٧٣» came apart into ٦ | ٧-arm | ٧ | ٣-top | ٣-bottom and
    was read «69771». A piece shorter than 60% of the line's digits, that the model does
    not read confidently on its own, rejoins its nearest piece when their ink is within
    1.5 pen widths — and only if the joined shape reads confidently as one digit. A small
    but complete digit (a short ٥ reads as ٥) and solid dots (a possible ٠) never join.
    Gaps alone cannot decide: here ٧ and ٣ were as close as the ٧'s own fragment.
    """
    def confident(piece):
        label, prob = best_digit(piece['mask'])
        return label != 'noise' and prob >= .8

    pieces_ = list(found)
    changed = True
    while changed:
        changed = False
        for p in sorted(pieces_, key=lambda p: p['box'][3] - p['box'][1]):
            if p['box'][3] - p['box'][1] >= .6 * digit_height or is_zero_dot(p, digit_height, pen_width) or confident(p):
                continue
            others = [q for q in pieces_ if q is not p and not is_zero_dot(q, digit_height, pen_width)]
            if not others:
                continue
            gap, q = min(((_gap(p, q), q) for q in others), key=lambda t: t[0])
            joined = _joined(p, q)
            if gap < 1.5 * pen_width and confident(joined):
                pieces_ = [r for r in pieces_ if r is not p and r is not q] + [joined]
                changed = True
                break
    return sorted(pieces_, key=lambda p: p['box'][0])


def _ink_colour(rgb, piece):
    x1, y1, x2, y2 = piece['box']
    lab = cv2.cvtColor(rgb[y1:y2, x1:x2], cv2.COLOR_RGB2LAB).reshape(-1, 3)
    ink = piece['mask'].reshape(-1) > 0
    return np.median(lab[ink].astype(np.float32), axis=0) if ink.any() else None


def plausible_zeros(digits, rgb=None):
    """Drop dots that cannot be the digit ٠.

    - A mahalla, zuqaq, house or form number never starts with ٠: a leading dot is a printed
      guide dot, a stamp dot or noise (stress test: «0105», «00210500», «02833»).
    - A ٠ is written with the same pen as its number: when the colours are known, a dot whose
      ink differs clearly from the number's other digits (black print next to blue pen, a
      lighter stamp dot) is not a digit («67300», «4200»).
    """
    if rgb is not None:
        shapes = [_ink_colour(rgb, d['_piece']) for d in digits if d['digit'] != 0 and d.get('_piece')]
        shapes = [c for c in shapes if c is not None]
        if shapes:
            pen = np.median(shapes, axis=0)
            kept = []
            for d in digits:
                if d['digit'] == 0 and d.get('_piece'):
                    colour = _ink_colour(rgb, d['_piece'])
                    if colour is not None and np.linalg.norm(colour - pen) > 30:
                        continue
                kept.append(d)
            digits = kept
    while digits and digits[0]['digit'] == 0:
        digits = digits[1:]
    return digits


def is_zero_dot(piece, digit_height, pen_width):
    """Arabic zero (٠) is a small solid dot, clearly larger than a printed guide dot."""
    x1, y1, x2, y2 = piece['box']
    w, h = x2 - x1, y2 - y1
    fill = piece['area'] / max(1, w * h)
    return max(w, h) < .45 * digit_height and .55 < w / max(1, h) < 1.8 and fill > .5 and max(w, h) >= 1.6 * pen_width


def on_one_line(found, line_y=None):
    """Keep the pieces that sit on the number's writing line.

    Digits of one number share a height and a centre line; strokes hanging from
    the line above, stamp fragments and specks do not. When the printed marker's height
    `line_y` is known, the line is the one nearest to it; otherwise the line carrying most
    ink (development card 24: a stamp arc above «١١» carried more ink and «77» was read from it).
    """
    heights = [p['box'][3] - p['box'][1] for p in found]
    digit_height = float(np.median([x for x in heights if x >= .5 * max(heights)]))
    # ١ is naturally taller than its neighbours, so allow up to 2x the typical height.
    full = [p for p in found if .5 * digit_height <= p['box'][3] - p['box'][1] <= 2.0 * digit_height]
    if not full:
        return [], digit_height, None
    # Area-weighted median: real digits carry most of the ink; strokes hanging
    # from the line above are thin and must not pull the line upward.
    order = sorted(full, key=lambda p: (p['box'][1] + p['box'][3]) / 2)
    weights = np.cumsum([p['area'] for p in order])
    middle = order[int(np.searchsorted(weights, weights[-1] / 2))]
    if line_y is not None:
        middle = min(full, key=lambda p: abs((p['box'][1] + p['box'][3]) / 2 - line_y))
    centre = (middle['box'][1] + middle['box'][3]) / 2
    kept = [p for p in found if abs((p['box'][1] + p['box'][3]) / 2 - centre) < .6 * digit_height
            and p['box'][3] - p['box'][1] <= 2.0 * digit_height]
    return kept, digit_height, centre


def contiguous_run(found, digit_height, anchor='right'):
    """The run of pieces written together, starting from the label/marker side.

    Numbers are written as one group; a large gap means the next ink belongs to
    something else (the card border, a stamp, another field).
    """
    ordered = sorted(found, key=lambda p: -p['box'][2] if anchor == 'right' else p['box'][0])
    full = [p for p in ordered if p['box'][3] - p['box'][1] >= .5 * digit_height]
    if not full:
        return []
    run = [full[0]]
    for p in ordered:
        if p is full[0] or p in run:
            continue
        near = min(max(q['box'][0] - p['box'][2], p['box'][0] - q['box'][2], 0) for q in run)
        if near < 1.3 * digit_height:
            run.append(p)
        elif p in full:
            break
    return sorted(run, key=lambda p: p['box'][0])


def read_digits(rgb=None, mask=None, pen_width=None, anchor='right', line_y=None):
    """Read one handwritten number. Returns None when nothing is readable.

    Prefer passing `mask`/`pen_width` computed with pen_mask() on the whole card:
    on a small crop the dotted guide line dominates and the pen width is underestimated.
    `anchor` is the side the number starts from (its label or printed marker).
    """
    if not available():
        return None
    call = next(_calls)
    if mask is None:
        mask, pen_width = pen_mask(rgb)
    found = pieces(mask, pen_width)
    guide = {id(p) for p in guide_dots(found, pen_width)}
    found = [p for p in found if id(p) not in guide]
    if not found:
        return None
    found, digit_height, centre = on_one_line(found, line_y)
    if not found:
        return None
    found = join_fragments(found, digit_height, pen_width)
    found = contiguous_run([part for p in found for part in maybe_split(p, digit_height)], digit_height, anchor)
    digits = []
    for p in found:
        cy = (p['box'][1] + p['box'][3]) / 2
        if is_zero_dot(p, digit_height, pen_width):
            # A zero sits in the middle of the line, not on top of a letter or below it,
            # and within the height of the digit next to it (a stamp dot above ٥ is not ٠).
            full = [q for q in found if q is not p and q['box'][3] - q['box'][1] >= .35 * digit_height
                    and not is_zero_dot(q, digit_height, pen_width)]
            beside = min(full, key=lambda q: abs((q['box'][0] + q['box'][2]) / 2 - (p['box'][0] + p['box'][2]) / 2), default=None)
            inside = beside is None or beside['box'][1] <= cy <= beside['box'][3]
            if abs(cy - centre) < .35 * digit_height and inside:
                digits.append({'digit': 0, 'probability': .9, 'box': p['box'], 'alternatives': [], 'ink': p['area'], '_piece': p})
            continue
        if p['box'][3] - p['box'][1] < .35 * digit_height:
            continue  # stray mark, not a full digit
        prob = probabilities(p['mask'])
        order = np.argsort(prob)[::-1]
        best = CLASSES[order[0]]
        if collector is not None:
            collector.append({'mask': p['mask'].copy(), 'digit': best, 'probability': float(prob[order[0]]), 'call': call})
        if best == 'noise':
            continue
        digits.append({'digit': best, 'probability': float(prob[order[0]]), 'box': p['box'], 'ink': p['area'], '_piece': p,
                       'alternatives': [{'digit': CLASSES[i], 'probability': round(float(prob[i]), 3)}
                                        for i in order[1:3] if CLASSES[i] != 'noise']})
    digits = plausible_zeros(digits, rgb if rgb is not None and mask is not None and rgb.shape[:2] == mask.shape else None)
    for d in digits:
        d.pop('_piece', None)
    if not digits:
        return None
    value = ''.join(str(d['digit']) for d in digits)
    confidence = float(np.prod([d['probability'] for d in digits]) ** (1 / len(digits)))
    # Clutter: share of the pen ink around the number that is NOT part of its digits (a stamp,
    # other writing, or digits that were missed). Used to decide on a second reading.
    x1 = max(0, min(d['box'][0] for d in digits) - int(digit_height))
    x2 = max(d['box'][2] for d in digits) + int(digit_height)
    y1 = max(0, int(centre - digit_height)); y2 = int(centre + digit_height)
    around = int((mask[y1:y2, x1:x2] > 0).sum())
    used = sum(int((d.get('ink', 0))) for d in digits)
    clutter = round(1 - used / max(1, around), 3) if around else 0.0
    # Overlap: other ink inside the digits' own boxes. Only this means the digit shapes may be
    # corrupted, so only this lowers confidence (card 24: a stamp arc beside a clean «١١»
    # counted as clutter and cut two 100% digits to 60%).
    inside = np.zeros(mask.shape, bool)
    for d in digits:
        bx1, by1, bx2, by2 = d['box']
        inside[by1:by2, bx1:bx2] = True
    in_boxes = int(((mask > 0) & inside).sum())
    overlap = round(1 - used / max(1, in_boxes), 3) if in_boxes else 0.0
    if overlap > .35:
        confidence *= .6
    return {'value': value, 'confidence': round(confidence, 3), 'digits': digits, 'pen_width': round(pen_width, 2),
            'clutter': clutter, 'overlap': overlap, 'call': call}
