"""Mustamsak's own number reader: a whole handwritten number strip read at once (docs/HANDWRITING.md).

Trained from scratch in this project (scripts/train_number_reader.py) on synthetic strips built
from MADBase handwriting and drawn card backgrounds, stamps and guide lines; never on real
identity documents. A fully convolutional CRNN with CTC: it reads the strip without cutting it
into digits first, so split, touching and dot-sized digits (٠) are read in context.

Runs in numpy (no torch at run time). Output: digits left to right as written (Western digits),
with a probability per digit. It is one more independent reader: see housing_handwriting.
"""
from pathlib import Path

import cv2
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / 'models' / 'number_reader.npz'
HEIGHT = 40
MIN_WIDTH = 64
MAX_WIDTH = 480
# (kind, name): conv = 3x3 same + ReLU; pool = max (2,2) or (2,1); convh = (2,1) valid + ReLU;
# tconv = 1-D conv k=5 same + ReLU, residual; head = 1x1 to 11 classes (blank + 0..9).
LAYERS = [('conv', 'c1'), ('pool22', None), ('conv', 'c2'), ('pool22', None), ('conv', 'c3'), ('conv', 'c4'),
          ('pool21', None), ('conv', 'c5'), ('conv', 'c6'), ('pool21', None), ('convh', 'c7'),
          ('tconv', 't1'), ('tconv', 't2'), ('tconv', 't3'), ('head', 'head')]
_weights = None


def available():
    return MODEL_PATH.exists()


def weights():
    global _weights
    if _weights is None:
        with np.load(MODEL_PATH, allow_pickle=False) as data:
            _weights = {k: data[k] for k in data.files}
    return _weights


def reset():
    global _weights
    _weights = None


def to_input(rgb):
    """Height 40, aspect kept, narrow strips padded with their own border colour (same as training)."""
    h, w = rgb.shape[:2]
    width = int(np.clip(round(w * HEIGHT / h), 8, MAX_WIDTH))
    image = cv2.resize(rgb, (width, HEIGHT), interpolation=cv2.INTER_AREA)
    if width < MIN_WIDTH:
        border = np.concatenate([image[:, :2].reshape(-1, 3), image[:, -2:].reshape(-1, 3)])
        colour = np.median(border, axis=0).astype(np.uint8)
        left = (MIN_WIDTH - width) // 2
        padded = np.empty((HEIGHT, MIN_WIDTH, 3), np.uint8)
        padded[:] = colour
        padded[:, left:left + width] = image
        image = padded
    return image


def _conv(x, w, b):
    windows = np.lib.stride_tricks.sliding_window_view(np.pad(x, ((0, 0), (1, 1), (1, 1))), (3, 3), axis=(1, 2))
    return np.maximum(np.einsum('chwij,ocij->ohw', windows, w, optimize=True) + b[:, None, None], 0)


def _pool(x, ph, pw):
    c, h, w = x.shape
    x = x[:, :h - h % ph, :w - w % pw]
    return x.reshape(c, h // ph, ph, w // pw, pw).max(axis=(2, 4))


def logits(image):
    """image: model input (HEIGHT, W, 3) uint8 -> (T, 11) logits."""
    p = weights()
    x = image.transpose(2, 0, 1).astype(np.float32) / 255.0 - .5
    for kind, name in LAYERS:
        if kind == 'conv':
            x = _conv(x, p[name + '.w'], p[name + '.b'])
        elif kind == 'pool22':
            x = _pool(x, 2, 2)
        elif kind == 'pool21':
            x = _pool(x, 2, 1)
        elif kind == 'convh':  # (O, C, 2, 1) valid over the remaining height of 2
            w = p[name + '.w']
            x = np.maximum(np.einsum('chw,och->ow', x[:, :w.shape[2]], w[:, :, :, 0], optimize=True)
                           + p[name + '.b'][:, None], 0)
        elif kind == 'tconv':  # (O, C, 5) same, residual
            w = p[name + '.w']
            windows = np.lib.stride_tricks.sliding_window_view(np.pad(x, ((0, 0), (2, 2))), 5, axis=1)
            x = x + np.maximum(np.einsum('ctk,ock->ot', windows, w, optimize=True) + p[name + '.b'][:, None], 0)
        else:
            x = p[name + '.w'][:, :, 0] @ x + p[name + '.b'][:, None]
    return x.T


def decode(log_probs):
    """Greedy CTC: digits (as ints) with the probability of the frame that emitted each one."""
    best = log_probs.argmax(axis=1)
    probs = np.exp(log_probs.max(axis=1))
    digits, previous = [], 0
    for t, k in enumerate(best):
        if k != 0 and k != previous:
            digits.append([int(k) - 1, float(probs[t])])
        elif k != 0 and k == previous:
            digits[-1][1] = max(digits[-1][1], float(probs[t]))
        previous = k
    return digits


def read(rgb):
    """Reads one number strip (RGB). Returns {'value', 'confidence', 'digits': [{'digit','probability'}]}
    or None when the model is missing or reads nothing."""
    if not available() or rgb is None or rgb.size == 0 or min(rgb.shape[:2]) < 6:
        return None
    z = logits(to_input(rgb))
    z = z - z.max(axis=1, keepdims=True)
    log_probs = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    digits = decode(log_probs)
    if not digits:
        return None
    confidence = float(np.prod([p for _, p in digits]) ** (1 / len(digits)))
    return {'value': ''.join(str(d) for d, _ in digits), 'confidence': round(confidence, 3),
            'digits': [{'digit': d, 'probability': round(p, 3)} for d, p in digits]}


def kept_aside(name):
    """One in five corrected strips (fixed by file name) is never trained on: an honest check on your cards."""
    import zlib
    return zlib.crc32(name.split('__', 1)[-1].encode('utf-8')) % 5 == 0
