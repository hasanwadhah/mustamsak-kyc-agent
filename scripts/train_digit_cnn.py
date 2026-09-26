"""Train the handwritten Eastern Arabic digit reader as a small CNN.

Data (no identity document is ever used):
  * MADBase real handwriting (research/downloads/madbase, see scripts/fetch_madbase.py),
    digits 1..9 with writer-style jitter. Its separate test split is used for reporting only.
  * Synthetic Iraqi-style pen strokes and a synthetic "not a digit" class
    (scripts/train_eastern_digits.py).
  * Optional (--extra): your own hand-checked digit images in data/digit-samples/<1..9|noise>/
    (scripts/export_digit_samples.py). One in five is kept aside and only used as a check.
Zero (٠, a solid dot) is recognised by a size rule in app/handwritten_digits.py.

Writes models/eastern_digits_cnn.npz (weights + metrics); the app runs the network in
numpy, so torch is needed only for training. About 15 minutes on CPU.

  python scripts/train_digit_cnn.py [--epochs 6] [--extra]
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.handwritten_digits import CLASSES, CNN_PATH, normalized  # noqa: E402

spec = importlib.util.spec_from_file_location('strokes', ROOT / 'scripts' / 'train_eastern_digits.py')
strokes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strokes)


def overlay(mask, rng):
    """Draw a stamp or signature over a digit, often touching it (as on development cards).

    The label stays the digit: the model must learn to read the digit through it.
    """
    from PIL import Image, ImageDraw, ImageFont
    out = mask.copy()
    size = out.shape[0]
    for _ in range(int(rng.integers(1, 3))):
        kind = rng.integers(3)
        width = int(rng.integers(2, 6))
        if kind == 0:  # stamp ring / arc passing through
            centre = (int(rng.uniform(-.3, 1.3) * size), int(rng.uniform(-.3, 1.3) * size))
            axes = (int(rng.uniform(.5, 1.2) * size), int(rng.uniform(.5, 1.2) * size))
            cv2.ellipse(out, centre, axes, float(rng.uniform(0, 180)), 0, 360, 255, width)
        elif kind == 1:  # stamp lettering next to / over the digit
            image = Image.new('L', (size, size), 0)
            font = ImageFont.truetype(str(Path('C:/Windows/Fonts') / strokes.FONTS[rng.integers(len(strokes.FONTS))]),
                                      int(size * rng.uniform(.18, .32)))
            text = ''.join(rng.choice(list('المركزيمعلوماتالغزاليةدائرة'), int(rng.integers(2, 5))))
            ImageDraw.Draw(image).text((rng.uniform(-.1, .7) * size, rng.uniform(-.1, .8) * size), text, font=font, fill=255)
            out |= cv2.dilate(np.array(image), np.ones((2, 2), np.uint8))
        else:  # signature scribble
            points = rng.uniform(-.1, 1.1, (int(rng.integers(3, 7)), 2)) * size
            curve = strokes.spline(points) if len(points) >= 3 else points
            cv2.polylines(out, [np.round(curve).astype(np.int32)], False, 255, width)
    return out


OWN_SAMPLES = ROOT / 'data' / 'digit-samples'


def ink_of(path):
    """A labelled image as a pen mask: exported ink images as they are, photo crops through pen_mask."""
    from app.handwritten_digits import pen_mask
    rgb = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if np.isin(gray, (0, 255)).mean() > .98:  # already an ink image (black on white, or white on black)
        return np.where(gray < 128, 255, 0).astype(np.uint8) if gray.mean() > 127 else np.where(gray > 127, 255, 0).astype(np.uint8)
    return pen_mask(rgb)[0]


def own_samples(folder):
    """[(mask, class index, kept_aside)] from folder/<1..9|noise>/*.png|jpg; every 5th file is kept aside."""
    out = []
    for label in CLASSES:
        files = sorted(p for p in (Path(folder) / str(label)).glob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.bmp'))
        for i, path in enumerate(files):
            mask = ink_of(path)
            if mask.any():
                out.append((mask, CLASSES.index(label), i % 5 == 4))
    return out


def jitter(mask, rng):
    """The same digit written slightly differently: rotation, slant, size and pen width."""
    h, w = mask.shape
    side = max(h, w) + 16  # square, as overlay() expects
    top, left = (side - h) // 2, (side - w) // 2
    pad = cv2.copyMakeBorder(mask, top, side - h - top, left, side - w - left, cv2.BORDER_CONSTANT, value=0)
    h, w = pad.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-10, 10), rng.uniform(.85, 1.1))
    matrix[0, 1] += rng.uniform(-.2, .2)
    out = cv2.warpAffine(pad, matrix, (w, h))
    k = int(rng.integers(0, 3))
    if k:
        out = (cv2.dilate if rng.random() < .5 else cv2.erode)(out, np.ones((k, k), np.uint8))
    return (out > 100).astype(np.uint8) * 255


def images(split, synthetic_per_class, real_per_class, seed, augment, overlap=0.0):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for index, label in enumerate(CLASSES):
        for _ in range(synthetic_per_class * (2 if label == 'noise' else 1)):
            mask = strokes.sample(label, rng)
            if overlap and label != 'noise' and rng.random() < overlap:
                mask = overlay(mask, rng)
            if mask.any():
                X.append(normalized(mask)); y.append(index)
    path = strokes.MADBASE / f'{split}.npz'
    if real_per_class and path.exists():
        with np.load(path) as data:  # load once: each data['X'] access decompresses the whole array
            images_, labels = data['X'], data['y']
        for digit in range(1, 10):
            index = np.flatnonzero(labels == digit)
            for i in rng.choice(index, min(real_per_class, len(index)), replace=False):
                mask = strokes.madbase_mask(images_[i], rng if augment else None)
                if overlap and rng.random() < overlap:
                    mask = overlay(mask, rng)
                if mask.any():
                    X.append(normalized(mask)); y.append(CLASSES.index(digit))
    return pack(X, y)


def pack(X, y):
    return np.asarray(X, np.float32).reshape(-1, 1, 28, 28) / 255.0, np.asarray(y, np.int64)


def own_images(samples, repeat, seed, overlap):
    """Training copies of your own digits (jittered, some under a stamp) and the kept-aside check set."""
    rng = np.random.default_rng(seed)
    X, y, Xc, yc = [], [], [], []
    for mask, label, aside in samples:
        if aside:
            Xc.append(normalized(mask)); yc.append(label)
            continue
        for _ in range(repeat):
            m = jitter(mask, rng)
            if overlap and CLASSES[label] != 'noise' and rng.random() < overlap:
                m = overlay(m, rng)
            if m.any():
                X.append(normalized(m)); y.append(label)
    return pack(X, y), pack(Xc, yc)


def build():
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(), nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.Conv2d(64, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Flatten(), nn.Dropout(.3), nn.Linear(64 * 7 * 7, 128), nn.ReLU(), nn.Dropout(.3), nn.Linear(128, len(CLASSES)))


def accuracy(model, X, y):
    import torch
    model.eval()
    with torch.no_grad():
        predictions = torch.cat([model(torch.from_numpy(X[i:i + 2048])).argmax(1) for i in range(0, len(X), 2048)])
    return float((predictions.numpy() == y).mean())


def main():
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=6)
    parser.add_argument('--synthetic', type=int, default=2500)
    parser.add_argument('--real', type=int, default=6000)
    parser.add_argument('--overlap', type=float, default=.4, help='share of training digits drawn under a stamp/signature')
    parser.add_argument('--extra', nargs='?', const=str(OWN_SAMPLES), default=None,
                        help='also learn from your hand-checked digits (default folder: data/digit-samples)')
    parser.add_argument('--extra-repeat', type=int, default=30, help='jittered copies of each of your digits')
    parser.add_argument('--out', default=str(CNN_PATH),
                        help='where to write the model (default: the one the app uses; the old one is kept as *.previous.npz)')
    args = parser.parse_args()
    torch.manual_seed(0)
    torch.set_num_threads(8)
    started = time.time()
    X, y = images('train', args.synthetic, args.real, seed=5, augment=True, overlap=args.overlap)
    Xs, ys = images('train', 300, 0, seed=99, augment=False)          # synthetic check, new seed
    Xr, yr = images('test', 0, 1000, seed=7, augment=False)            # MADBase held-out test split
    Xo, yo = images('test', 0, 1000, seed=8, augment=False, overlap=1.0)  # same, every digit under a stamp/signature
    Xc = yc = np.zeros(0)
    if args.extra:
        samples = own_samples(args.extra)
        (Xe, ye), (Xc, yc) = own_images(samples, args.extra_repeat, seed=11, overlap=args.overlap)
        print(f'your digits: {len(samples)} images, {len(yc)} kept aside as a check', flush=True)
        if len(ye):
            X, y = np.concatenate([X, Xe]), np.concatenate([y, ye])
    print(f'data: train {len(y)}, synthetic check {len(ys)}, real test {len(yr)} ({time.time() - started:.0f}s)', flush=True)
    model = build()
    optimiser = torch.optim.Adam(model.parameters(), 1e-3)
    loss_fn = torch.nn.CrossEntropyLoss()
    Xt, yt = torch.from_numpy(X), torch.from_numpy(y)
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(yt))
        for i in range(0, len(order), 128):
            batch = order[i:i + 128]
            optimiser.zero_grad()
            loss = loss_fn(model(Xt[batch]), yt[batch])
            loss.backward()
            optimiser.step()
        if epoch == args.epochs - 2:
            for group in optimiser.param_groups:
                group['lr'] = 3e-4
        print(f'epoch {epoch + 1}: synthetic {accuracy(model, Xs, ys):.4f}'
              + (f', MADBase test {accuracy(model, Xr, yr):.4f}, under stamp/signature {accuracy(model, Xo, yo):.4f}' if len(yr) else '')
              + (f', your kept-aside digits {accuracy(model, Xc, yc):.4f}' if len(yc) else '')
              + f' ({time.time() - started:.0f}s)', flush=True)
    model.eval()
    meta = {'classes': [str(c) for c in CLASSES], 'synthetic_accuracy': accuracy(model, Xs, ys),
            'madbase_test_accuracy': accuracy(model, Xr, yr) if len(yr) else None, 'trained_on_real': bool(len(yr)),
            'madbase_test_accuracy_under_overlap': accuracy(model, Xo, yo) if len(yo) else None, 'overlap_training_share': args.overlap,
            'own_samples_check_accuracy': accuracy(model, Xc, yc) if len(yc) else None, 'own_samples_check_size': int(len(yc)),
            'sources': ['MADBase (El-Sherif & Abdelazeem, 2007), research use with citation', 'synthetic Iraqi-style strokes']
            + (['hand-checked local digit samples (data/digit-samples)'] if args.extra else [])}
    # Plain arrays, run by numpy in app/handwritten_digits.py (no onnx/torch at runtime).
    layers = [m for m in model if hasattr(m, 'weight')]
    arrays = {f'p{i}_{kind}': getattr(m, kind).detach().numpy().astype(np.float32)
              for i, m in enumerate(layers) for kind in ('weight', 'bias')}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():  # keep the model being replaced, to roll back if the new one reads worse
        import shutil
        shutil.copy2(out, out.with_name(out.stem + '.previous.npz'))
    np.savez_compressed(out, **arrays, meta=np.array(json.dumps(meta)))
    print(f'saved {out}', flush=True)
    print(json.dumps(meta), flush=True)


if __name__ == '__main__':
    main()
