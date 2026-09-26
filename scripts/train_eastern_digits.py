"""Train the handwritten Eastern Arabic digit classifier (١..٩ + "not a digit").

Training data:
  * MADBase (El-Sherif & Abdelazeem, 2007): 60,000 real handwritten Arabic-Indic digits
    by 700 writers, free for research with citation. Optional: downloaded once to
    research/downloads/madbase/{train,test}.npz (see scripts/fetch_madbase.py).
    Its separate 10,000-image test split is used only for reporting.
  * Synthetic pen strokes in Iraqi forms (below), and a synthetic "not a digit" class.
No identity document is ever used for training. Each digit is drawn as pen strokes in the
forms common in Iraqi handwriting (٢ like "c", ٤ like "ع", ٥ as a loop, ٦ like "7",
٧ as V, ٨ as Λ, ٩ with a top loop), with random slant, proportions, pen width,
wobble and blur. Zero (٠, a solid dot) is recognised by a size rule in
app/handwritten_digits.py, not by this model. Printed-font digits are mixed in.

  python scripts/train_eastern_digits.py            # writes models/eastern_digits.npz
  python scripts/train_eastern_digits.py --preview  # also writes a sample sheet
"""
import argparse
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.handwritten_digits import CLASSES, features, MODEL_PATH  # noqa: E402

# Control points in a unit box (x to the right, y down). Several styles per digit.
STROKES = {
    1: [[[(.55, .02), (.50, .50), (.45, .98)]],
        [[(.62, .02), (.52, .45), (.40, .98)]],
        [[(.40, .08), (.55, .02), (.52, .50), (.48, .98)]],
        [[(.35, .02), (.50, .50), (.65, .98)]]],                                   # slanting the other way
    2: [[[(.90, .10), (.55, .02), (.20, .30), (.25, .75), (.85, .95)]],          # "c" with a long lower tail
        [[(.85, .05), (.40, .10), (.25, .50), (.45, .85), (.90, .92)]],
        [[(.95, .02), (.80, .25), (.50, .18), (.42, .55), (.40, .98)]],          # printed-like: hook then stem
        [[(.80, .12), (.30, .05), (.15, .45), (.35, .80), (.95, .80)]]],
    3: [[[(.98, .05), (.88, .28), (.74, .05), (.62, .28), (.48, .05), (.45, .50), (.38, .98)]],
        [[(.95, .10), (.85, .30), (.72, .08), (.60, .30), (.50, .10), (.45, .30), (.40, .98)]],
        [[(.90, .02), (.80, .22), (.68, .02), (.58, .22), (.45, .02)], [(.45, .02), (.42, .55), (.35, .98)]]],
    4: [[[(.85, .05), (.40, .02), (.30, .25), (.65, .45), (.30, .55), (.25, .85), (.85, .98)]],   # "ع"
        [[(.80, .10), (.35, .10), (.35, .35), (.70, .48), (.35, .62), (.35, .90), (.90, .92)]],
        [[(.75, .02), (.30, .12), (.45, .40), (.25, .60), (.40, .95), (.85, .85)]],
        [[(.65, .05), (.30, .05), (.28, .28), (.50, .38), (.22, .55), (.25, .88), (.98, .95)]],   # small top curve, long sweep right
        [[(.55, .02), (.25, .12), (.35, .35), (.15, .55), (.30, .92), (.98, .98)]],
        [[(.60, .10), (.35, .02), (.30, .30), (.40, .40), (.20, .60), (.40, .85), (.95, .75)]]],
    5: [[[(.50, .05), (.15, .35), (.25, .90), (.75, .90), (.85, .35), (.50, .05)]],
        [[(.50, .15), (.25, .45), (.35, .85), (.65, .85), (.75, .45), (.50, .15), (.40, .40), (.55, .70), (.60, .40)]],  # thick pen fills the loop
        [[(.55, .10), (.10, .50), (.45, .95), (.90, .55), (.55, .10), (.45, .30)]],
        [[(.50, .02), (.20, .55), (.50, .98), (.80, .55), (.50, .02)]]],
    6: [[[(.10, .05), (.55, .12), (.85, .08), (.70, .55), (.55, .98)]],          # "7"-like
        [[(.05, .20), (.40, .05), (.80, .10), (.65, .60), (.60, .98)]],
        [[(.20, .02), (.25, .15), (.80, .12), (.62, .98)]],
        [[(.30, .12), (.45, .02), (.62, .08), (.58, .55), (.52, .98)]],            # small hook on a long stem
        [[(.35, .20), (.55, .05), (.70, .15), (.60, .60), (.45, .98)]],
        [[(.02, .10), (.30, .02), (.60, .45), (.95, .98)]],                         # flag top-left, stem slanting down-right
        [[(.05, .28), (.20, .02), (.55, .40), (.90, .98)]],
        [[(.02, .02), (.35, .05), (.55, .50), (.80, .98)]]],
    7: [[[(.05, .02), (.50, .98), (.95, .02)]],
        [[(.10, .05), (.45, .95), (.55, .95), (.90, .02)]],
        [[(.15, .02), (.50, .98), (.85, .10), (.95, .02)]],
        [[(.30, .35), (.50, .98), (.95, .02)]],                                     # short left arm
        [[(.05, .02), (.50, .98), (.70, .40)]]],
    8: [[[(.05, .98), (.50, .02), (.95, .98)]],
        [[(.10, .95), (.45, .05), (.55, .05), (.90, .98)]]],
    9: [[[(.55, .35), (.30, .50), (.10, .30), (.30, .05), (.60, .12), (.62, .40), (.58, .98)]],
        [[(.60, .30), (.35, .45), (.15, .25), (.40, .02), (.65, .20), (.55, .98)]],
        [[(.55, .40), (.20, .45), (.20, .10), (.55, .05), (.60, .45), (.70, .98)]],
        [[(.40, .25), (.22, .30), (.20, .10), (.40, .03), (.45, .25), (.70, .70), (.90, .98)]],   # small loop, long diagonal tail
        [[(.45, .28), (.25, .28), (.25, .08), (.45, .05), (.50, .30), (.60, .98)]]],
}
FONTS = [f for f in ['tahoma.ttf', 'arial.ttf', 'arabtype.ttf', 'majalla.ttf', 'DIWANLTR.TTF', 'simpo.ttf', 'segoeui.ttf',
                     'andlso.ttf', 'times.ttf'] if (Path('C:/Windows/Fonts') / f).exists()]
EASTERN = '٠١٢٣٤٥٦٧٨٩'


def spline(points, steps=24):
    """Catmull-Rom curve through the control points."""
    p = np.asarray(points, float)
    if len(p) < 3:
        return p
    p = np.vstack([p[0], p, p[-1]])
    out = []
    for i in range(1, len(p) - 2):
        a, b, c, d = p[i - 1], p[i], p[i + 1], p[i + 2]
        for t in np.linspace(0, 1, steps, endpoint=False):
            out.append(.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3))
    out.append(p[-2])
    return np.asarray(out)


def draw_strokes(strokes, rng, size=96):
    """Render strokes with random affine, wobble and pen width. Returns a binary ink mask."""
    width, height = rng.uniform(.55, 1.15), rng.uniform(.85, 1.15)
    angle, shear = np.radians(rng.uniform(-14, 14)), rng.uniform(-.3, .3)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    canvas = np.zeros((size, size), np.uint8)
    pen = int(round(rng.uniform(.05, .13) * size))
    for stroke in strokes:
        pts = np.asarray(stroke, float) + rng.normal(0, .035, (len(stroke), 2))
        curve = spline(pts)
        curve = (curve - .5) * [width, height]
        curve[:, 0] += shear * curve[:, 1]
        curve = curve @ rot.T
        curve = (curve * .7 + .5) * size
        curve += rng.normal(0, .004 * size, curve.shape)  # hand tremor
        cv2.polylines(canvas, [np.round(curve).astype(np.int32)], False, 255, max(1, pen), cv2.LINE_AA)
    return canvas


def font_digit(digit, rng, size=96):
    image = Image.new('L', (size, size), 0)
    face = ImageFont.truetype(str(Path('C:/Windows/Fonts') / FONTS[rng.integers(len(FONTS))]), int(size * rng.uniform(.55, .8)))
    ImageDraw.Draw(image).text((size / 2, size / 2), EASTERN[digit], font=face, fill=255, anchor='mm')
    image = np.array(image)
    k = int(rng.integers(1, 4))
    return cv2.dilate(image, np.ones((k, k), np.uint8))


def noise_sample(rng, size=96):
    """Things that are not digits: printed letters (م ز د ...), dashes and stamp arcs.

    Random pen scribbles are deliberately excluded: they look like unusual real
    digits and taught the model to reject genuine handwriting.
    """
    kind = rng.integers(3)
    canvas = np.zeros((size, size), np.uint8)
    if kind == 0:
        image = Image.new('L', (size, size), 0)
        face = ImageFont.truetype(str(Path('C:/Windows/Fonts') / FONTS[rng.integers(len(FONTS))]), int(size * rng.uniform(.5, .8)))
        ImageDraw.Draw(image).text((size / 2, size / 2), rng.choice(list('مزدرسصعهقفنبت')), font=face, fill=255, anchor='mm')
        return np.array(image)
    if kind == 1:  # horizontal dash / underline
        y = int(rng.uniform(.3, .7) * size)
        cv2.line(canvas, (int(.05 * size), y), (int(.95 * size), y + int(rng.uniform(-8, 8))), 255, int(rng.integers(3, 10)))
    else:  # stamp arc
        cv2.ellipse(canvas, (size // 2, size // 2), (int(size * .45), int(size * .3)), float(rng.uniform(0, 180)),
                    float(rng.uniform(0, 180)), float(rng.uniform(200, 360)), 255, int(rng.integers(2, 5)))
    return canvas


def elastic(mask, rng, strength=2.5):
    """Smooth random displacement, like natural variation between writers."""
    h, w = mask.shape
    dx = cv2.GaussianBlur(rng.uniform(-1, 1, (h, w)).astype(np.float32), (0, 0), 8) * strength * 8
    dy = cv2.GaussianBlur(rng.uniform(-1, 1, (h, w)).astype(np.float32), (0, 0), 8) * strength * 8
    x, y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(mask, x + dx, y + dy, cv2.INTER_LINEAR, borderValue=0)


def sample(label, rng):
    if label == 'noise':
        mask = noise_sample(rng)
    elif label == 5 and rng.random() < .3:
        # A thick pen often fills the loop of ٥ completely.
        mask = np.zeros((96, 96), np.uint8)
        cv2.ellipse(mask, (48, 50), (int(rng.uniform(14, 24)), int(rng.uniform(16, 26))), float(rng.uniform(-30, 30)), 0, 360, 255, -1)
        if rng.random() < .6:
            cv2.line(mask, (48, 30), (int(rng.uniform(40, 70)), int(rng.uniform(10, 25))), 255, int(rng.integers(5, 10)))
        mask = draw_strokes([], rng) | mask
    elif rng.random() < .15:
        mask = font_digit(label, rng)
    else:
        styles = STROKES[label]
        mask = draw_strokes(styles[rng.integers(len(styles))], rng)
    if label != 'noise' and rng.random() < .6:
        mask = elastic(mask, rng)
    if rng.random() < .4:
        mask = cv2.GaussianBlur(mask, (0, 0), rng.uniform(.5, 1.5))
    if rng.random() < .3:  # broken pen stroke
        y, x = rng.integers(0, 96, 2)
        cv2.circle(mask, (int(x), int(y)), int(rng.integers(2, 6)), 0, -1)
    return (mask > 90).astype(np.uint8) * 255


MADBASE = ROOT / 'research' / 'downloads' / 'madbase'


def madbase_mask(image, rng=None):
    """A MADBase 28x28 digit as a pen mask like ours, with writer-style jitter."""
    big = cv2.resize(image, (96, 96), interpolation=cv2.INTER_CUBIC)
    if rng is not None:
        angle, shear = rng.uniform(-12, 12), rng.uniform(-.25, .25)
        matrix = cv2.getRotationMatrix2D((48, 48), angle, rng.uniform(.8, 1.05))
        matrix[0, 1] += shear
        big = cv2.warpAffine(big, matrix, (96, 96))
        k = int(rng.integers(0, 3))
        if k:
            big = (cv2.dilate if rng.random() < .6 else cv2.erode)(big, np.ones((k + 1, k + 1), np.uint8))
    return (big > 100).astype(np.uint8) * 255


def madbase(split, per_class, seed, augment):
    """Real handwritten digits 1..9 from MADBase, if downloaded. Zero is handled by a size rule."""
    path = MADBASE / f'{split}.npz'
    if not path.exists():
        return [], []
    with np.load(path) as data:  # load once: each data['X'] access decompresses the whole array
        images, labels = data['X'], data['y']
    rng = np.random.default_rng(seed)
    X, y = [], []
    for digit in range(1, 10):
        index = np.flatnonzero(labels == digit)
        for i in rng.choice(index, min(per_class, len(index)), replace=False):
            mask = madbase_mask(images[i], rng if augment else None)
            if mask.any():
                X.append(features(mask)); y.append(CLASSES.index(digit))
    return X, y


def dataset(count, seed, real_per_class=0, split='train'):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for index, label in enumerate(CLASSES):
        for _ in range(count * (2 if label == 'noise' else 1)):
            mask = sample(label, rng)
            if not mask.any():
                continue
            X.append(features(mask))
            y.append(index)
    if real_per_class:
        rx, ry = madbase(split, real_per_class, seed + 1, augment=split == 'train')
        X += rx; y += ry
    return np.asarray(X, np.float32), np.asarray(y)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=2500, help='training samples per class')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--real', action='store_true', help='also use MADBase (slow with this MLP; prefer train_digit_cnn.py)')
    args = parser.parse_args()
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    if args.preview:
        rng = np.random.default_rng(1)
        rows = [np.hstack([cv2.resize(sample(label, rng), (48, 48)) for _ in range(14)]) for label in CLASSES]
        cv2.imwrite(str(ROOT / 'eval' / 'digit_samples.png'), 255 - np.vstack(rows))
    real = args.real and (MADBASE / 'train.npz').exists()
    X, y = dataset(args.count, seed=5, real_per_class=6000 if real else 0)
    Xv, yv = dataset(300, seed=99)  # synthetic validation, different seed
    scaler = StandardScaler().fit(X)
    model = MLPClassifier(hidden_layer_sizes=(256, 128), alpha=1e-3, max_iter=80, early_stopping=True, random_state=0)
    model.fit(scaler.transform(X), y)
    accuracy = float((model.predict(scaler.transform(Xv)) == yv).mean())
    real_accuracy = None
    if (MADBASE / 'test.npz').exists():
        tx, ty = madbase('test', 1000, 7, augment=False)
        real_accuracy = float((model.predict(scaler.transform(np.asarray(tx, np.float32))) == np.asarray(ty)).mean())
        print(f'MADBase held-out test accuracy (digits 1-9, {len(ty)} images): {real_accuracy:.4f}')
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    arrays = {'mean': scaler.mean_.astype(np.float32), 'scale': scaler.scale_.astype(np.float32),
              'classes': np.array([str(c) for c in CLASSES]), 'validation_accuracy': np.array(accuracy),
              'real_test_accuracy': np.array(-1.0 if real_accuracy is None else real_accuracy),
              'trained_on_real': np.array(real)}
    for i, (w, b) in enumerate(zip(model.coefs_, model.intercepts_)):
        arrays[f'w{i}'], arrays[f'b{i}'] = w.astype(np.float32), b.astype(np.float32)
    np.savez_compressed(MODEL_PATH, **arrays)
    print(f'synthetic validation accuracy {accuracy:.3f}; saved {MODEL_PATH}')


if __name__ == '__main__':
    main()
