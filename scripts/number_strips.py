"""Synthetic strips of handwritten Arabic-Indic numbers, like the number slots on Iraqi housing cards.

Training data for the number reader (scripts/train_number_reader.py, docs/HANDWRITING.md). No identity
document is used: digits come from MADBase (real handwriting from many writers; the `test` split
only ever feeds the held-out check) plus synthetic Iraqi-style strokes and font digits. Everything
else is drawn: card-like backgrounds, the dotted guide line, pen colours, stamps over the digits,
clipped text from the rows above and below, marker letters at the edges, blur, low resolution,
JPEG and faint ink. These imitate the handwritten number slots of Iraqi cards (see docs/HANDWRITING.md).

    python scripts/number_strips.py --preview out.png     # a sheet of examples
"""
import argparse
import importlib.util
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HEIGHT = 40  # model input height (app/number_reader.py uses the same)
FONT_DIR = Path('C:/Windows/Fonts')

_spec = importlib.util.spec_from_file_location('strokes', ROOT / 'scripts' / 'train_eastern_digits.py')
strokes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(strokes)

# Height of each digit relative to a full digit, as written on the cards: ٠ is a dot, ٥ a small loop.
RELATIVE_HEIGHT = {0: (.2, .34), 5: (.42, .7), 1: (.85, 1.1)}
LENGTHS = ([1, 2, 3, 4, 5, 6], [.13, .3, .25, .1, .19, .03])
BACKGROUNDS = [(250, 250, 250), (236, 232, 245), (222, 238, 196), (205, 228, 160), (246, 240, 222),
               (228, 230, 232), (238, 244, 226), (214, 222, 236)]
PENS = [((20, 40, 150), .35), ((40, 60, 200), .15), ((200, 30, 40), .15), ((25, 25, 30), .15), ((90, 90, 95), .1),
        ((60, 60, 140), .1)]
STAMPS = [(60, 70, 190), (110, 60, 160), (190, 50, 70), (40, 110, 170)]
LETTERS = 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي'


class Glyphs:
    """Pen masks of single digits from MADBase (per split), synthetic strokes and fonts."""

    def __init__(self, split='train'):
        path = ROOT / 'research' / 'downloads' / 'madbase' / f'{split}.npz'
        with np.load(path) as data:
            self.images, self.labels = data['X'], data['y']
        self.by_digit = [np.flatnonzero(self.labels == d) for d in range(10)]
        self.split = split

    def mask(self, digit, rng):
        source = rng.random()
        if source < .72 or digit == 0:
            image = self.images[rng.choice(self.by_digit[digit])]
            mask = strokes.madbase_mask(image, rng)
        elif source < .9 or digit == 0:
            mask = strokes.sample(digit, rng)
        else:
            mask = strokes.font_digit(digit, rng)
        ys, xs = np.nonzero(mask > 0)
        if not len(ys):
            return None
        return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _label(rng):
    n = int(rng.choice(LENGTHS[0], p=LENGTHS[1]))
    digits = [int(rng.integers(1, 10))] + [int(d) for d in rng.integers(0, 10, n - 1)]
    if n > 1 and rng.random() < .25:  # zeros are common inside Iraqi numbers (e.g. 407, 10380, 30126)
        digits[int(rng.integers(1, n))] = 0
    return digits


def _ink_line(digits, glyphs, rng, size):
    """The number as an ink mask (float 0..1) and its baseline, digits left to right."""
    parts, x = [], 0
    stroke = rng.uniform(.06, .14)
    for d in digits:
        g = glyphs.mask(d, rng)
        if g is None:
            continue
        lo, hi = RELATIVE_HEIGHT.get(d, (.75, 1.0))
        h = max(4 if d == 0 else 2, int(size * rng.uniform(lo, hi)))
        w = max(2, int(g.shape[1] * h / g.shape[0] * rng.uniform(.8, 1.2)))
        if d == 0:
            w = max(2, int(h * rng.uniform(.8, 1.5)))
        g = cv2.resize(g, (w, h), interpolation=cv2.INTER_AREA)
        pen = max(1, int(size * stroke * rng.uniform(.8, 1.2)))
        if d != 0 and rng.random() < .5:  # re-stroke at this size: consistent pen width within a number
            g = cv2.dilate((g > 60).astype(np.uint8) * 255, np.ones((pen // 3 + 1, pen // 3 + 1), np.uint8))
        if d == 0:  # ٠ is a dot or a tiny diamond
            h0, w0 = g.shape
            g = np.zeros((h0, w0), np.uint8)
            cv2.ellipse(g, (w0 // 2, h0 // 2), (max(1, w0 // 2), max(1, h0 // 2)), float(rng.uniform(-40, 40)), 0, 360, 255, -1)
        if d in (0, 5):
            lift = size * rng.uniform(.15, .45)  # small digits float at mid height
        else:
            lift = size * rng.normal(0, .06)
        gap = size * rng.normal(.18, .14)
        if rng.random() < .15:
            gap = -size * rng.uniform(0, .15)  # touching / overlapping neighbours
        if parts:
            x += max(-.5 * w, gap)
        parts.append((g, int(x), lift))
        x += w
    if not parts:
        return None, 0
    shift = -min(px for _, px, _ in parts)
    parts = [(g, px + shift, lift) for g, px, lift in parts]
    width = int(max(px + g.shape[1] for g, px, _ in parts)) + 2
    slope = rng.normal(0, .04)
    # y of each glyph's bottom, relative to the baseline at x = 0 (downwards positive)
    placed = [(g, px, int(round(-lift + slope * px))) for g, px, lift in parts]
    top = -min(y - g.shape[0] for g, _, y in placed) + 2
    bottom = max(y for _, _, y in placed) + 2
    canvas = np.zeros((top + max(0, bottom), width), np.float32)
    for g, px, y in placed:
        y2 = top + y
        y1 = y2 - g.shape[0]
        canvas[y1:y2, px:px + g.shape[1]] = np.maximum(canvas[y1:y2, px:px + g.shape[1]], g / 255.0)
    return canvas, top


def _background(h, w, rng):
    a, b = (np.array(BACKGROUNDS[i], np.float32) for i in rng.integers(len(BACKGROUNDS), size=2))
    t = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
    if rng.random() < .5:
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None] * np.ones((1, w, 1), np.float32)
    image = a * (1 - t) + b * t
    image = np.broadcast_to(image, (h, w, 3)).copy()
    if rng.random() < .6:  # the card's printed green pattern: big soft blobs
        blob = np.zeros((h, w), np.float32)
        for _ in range(int(rng.integers(1, 4))):
            cv2.ellipse(blob, (int(rng.uniform(0, w)), int(rng.uniform(-h, 2 * h))),
                        (int(rng.uniform(.3, 1.2) * w), int(rng.uniform(.5, 2) * h)), 0, 0, 360, 1, -1)
        blob = cv2.GaussianBlur(blob, (0, 0), max(1, h / 6))[:, :, None]
        tint = np.array(BACKGROUNDS[int(rng.integers(len(BACKGROUNDS)))], np.float32)
        image = image * (1 - .6 * blob) + tint * .6 * blob
    image += rng.normal(0, rng.uniform(1, 6), image.shape)
    return image


def _paint(image, mask, colour, strength=1.0):
    alpha = np.clip(mask, 0, 1)[:, :, None] * strength
    image[:] = image * (1 - alpha) + np.array(colour, np.float32) * alpha


def _text_mask(h, w, rng, size, text=None):
    """Printed or handwritten-looking Arabic text (for rows above/below, stamps, markers)."""
    face = ImageFont.truetype(str(FONT_DIR / strokes.FONTS[rng.integers(len(strokes.FONTS))]), max(6, int(size)))
    text = text or ''.join(rng.choice(list(LETTERS + '   '), int(rng.integers(3, 12))))
    image = Image.new('L', (w, h), 0)
    ImageDraw.Draw(image).text((rng.uniform(-.2, .6) * w, rng.uniform(0, 1) * h), text, font=face, fill=255, anchor='lm')
    return np.array(image, np.float32) / 255


def strip(digits, glyphs, rng):
    """One synthetic number strip (RGB uint8) for the digit list, height HEIGHT."""
    size = rng.uniform(24, 60)  # a full digit's height, in pixels, at photo resolution
    ink, top = _ink_line(digits, glyphs, rng, size)
    if ink is None:
        return None
    ih, iw = ink.shape
    h = int(ih + size * rng.uniform(.5, 1.6))
    y0 = int(rng.uniform(.1, .7) * (h - ih))
    left, right = size * rng.uniform(.2, 1.5), size * rng.uniform(.2, 1.5)
    if rng.random() < .35:  # house numbers sit in a wide slot, form numbers far to one side
        if rng.random() < .6:
            left += size * rng.uniform(1, 6)
        right += size * rng.uniform(0, 3)
    w = int(iw + left + right)
    x0 = int(left)
    image = _background(h, w, rng)
    baseline = y0 + top
    if rng.random() < .85:  # dotted guide line under the digits, across the slot
        gy = int(baseline + size * rng.uniform(-.15, .12))
        step = max(3, int(size * rng.uniform(.08, .16)))
        dot = max(1, int(size * rng.uniform(.02, .05)))
        guide = np.zeros((h, w), np.float32)
        start = int(rng.uniform(0, .4) * w) if rng.random() < .5 else 0
        for gx in range(start, w, step):
            cv2.circle(guide, (gx, gy), dot, 1, -1)
        _paint(image, guide, (rng.uniform(20, 90),) * 3, rng.uniform(.5, .95))
    if rng.random() < .6:  # the next rows' text clipped by the strip edges
        for edge in ('top', 'bottom'):
            if rng.random() < .6:
                band = np.zeros((h, w), np.float32)
                piece = _text_mask(int(size), w, rng, size * rng.uniform(.6, 1.1))
                if edge == 'top':
                    k = int(size * rng.uniform(.15, .5)); band[:k] = piece[-k:]
                else:
                    k = int(size * rng.uniform(.15, .5)); band[-k:] = piece[:k]
                colour = PENS[int(rng.integers(len(PENS)))][0] if rng.random() < .6 else (30, 30, 30)
                _paint(image, band, colour, rng.uniform(.6, 1))
    if rng.random() < .3:  # a printed marker letter (م ز د) cut at a side
        m = _text_mask(h, int(size * 1.2), rng, size * rng.uniform(.6, 1), rng.choice(list('مزد')))
        band = np.zeros((h, w), np.float32)
        k = int(size * rng.uniform(.2, .6))
        if rng.random() < .5:
            band[:, -k:] = m[:, :k]
        else:
            band[:, :k] = m[:, -k:]
        _paint(image, band, (30, 30, 30), .9)
    pen, _ = PENS[int(rng.choice(len(PENS), p=[p for _, p in PENS]))]
    pen = np.clip(np.array(pen) + rng.normal(0, 15, 3), 0, 255)
    full = np.zeros((h, w), np.float32)
    full[y0:y0 + ih, x0:x0 + iw] = ink[:h - y0, :w - x0]
    full = cv2.GaussianBlur(full, (0, 0), rng.uniform(.3, 1.0))
    strength = rng.uniform(.85, 1) if rng.random() < .8 else rng.uniform(.35, .7)  # faint pencil / pale ink
    stamp_first = rng.random() < .5
    if stamp_first:
        _stamp(image, h, w, size, rng)
    _paint(image, full, pen, strength)
    if not stamp_first:
        _stamp(image, h, w, size, rng)
    if rng.random() < .15:  # signature scribble
        pts = rng.uniform([0, 0], [w, h], (int(rng.integers(3, 7)), 2))
        curve = strokes.spline(pts)
        sig = np.zeros((h, w), np.float32)
        cv2.polylines(sig, [np.round(curve).astype(np.int32)], False, 1, max(1, int(size * .06)), cv2.LINE_AA)
        _paint(image, sig, PENS[int(rng.integers(len(PENS)))][0], rng.uniform(.5, 1))
    return degrade(np.clip(image, 0, 255).astype(np.uint8), rng)


def _stamp(image, h, w, size, rng):
    if rng.random() > .35:
        return
    mask = np.zeros((h, w), np.float32)
    colour = STAMPS[int(rng.integers(len(STAMPS)))]
    r = int(size * rng.uniform(1.5, 4))
    centre = (int(rng.uniform(-.2, 1.2) * w), int(rng.uniform(-.5, 1.5) * h))
    thick = max(1, int(size * rng.uniform(.03, .08)))
    for k in range(int(rng.integers(1, 3))):
        cv2.circle(mask, centre, int(r * (1 - .18 * k)), 1, thick, cv2.LINE_AA)
    if rng.random() < .7:
        mask = np.maximum(mask, _text_mask(h, w, rng, size * rng.uniform(.3, .6)))
    _paint(image, mask, colour, rng.uniform(.4, .9))


def degrade(image, rng):
    """Photo problems: lighting, blur, low resolution, JPEG, tilt."""
    image = image.astype(np.float32)
    image = image * rng.uniform(.7, 1.15) + rng.uniform(-25, 25)
    if rng.random() < .3:
        gamma = rng.uniform(.6, 1.6)
        image = 255 * (np.clip(image, 0, 255) / 255) ** gamma
    image = np.clip(image, 0, 255).astype(np.uint8)
    h, w = image.shape[:2]
    if rng.random() < .4:
        angle = rng.uniform(-4, 4)
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
        image = cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if rng.random() < .5:
        image = cv2.GaussianBlur(image, (0, 0), rng.uniform(.3, 2.2))
    if rng.random() < .45:  # low-resolution photo: down then up
        f = rng.uniform(.3, .8)
        small = cv2.resize(image, (max(4, int(w * f)), max(4, int(h * f))), interpolation=cv2.INTER_AREA)
        image = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    if rng.random() < .6:
        ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(25, 95))])
        image = cv2.imdecode(jpeg, cv2.IMREAD_UNCHANGED)
    return image


def to_input(rgb):
    """A strip as the model sees it (shared with the app, so training and use match)."""
    from app.number_reader import to_input as app_input
    return app_input(rgb)


def sample(glyphs, rng):
    while True:
        digits = _label(rng)
        image = strip(digits, glyphs, rng)
        if image is not None:
            return to_input(image), digits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', required=True)
    parser.add_argument('--split', default='train')
    parser.add_argument('--count', type=int, default=40)
    args = parser.parse_args()
    rng = np.random.default_rng(7)
    glyphs = Glyphs(args.split)
    rows = []
    for _ in range(args.count):
        image, digits = sample(glyphs, rng)
        big = cv2.resize(image, (image.shape[1] * 2, image.shape[0] * 2), interpolation=cv2.INTER_NEAREST)[:, :560]
        pad = np.full((big.shape[0] + 4, 600, 3), 255, np.uint8)
        pad[2:2 + big.shape[0], 2:2 + big.shape[1]] = big
        cv2.putText(pad, ''.join(map(str, digits)), (568 - 12 * len(digits), 50), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 255), 1)
        rows.append(pad)
    half = (len(rows) + 1) // 2
    left, right = rows[:half], rows[half:] + [np.full_like(rows[0], 255)] * (half - len(rows[half:]))
    sheet = np.hstack([np.vstack(left), np.vstack(right)])
    cv2.imwrite(args.preview, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))


if __name__ == '__main__':
    main()
