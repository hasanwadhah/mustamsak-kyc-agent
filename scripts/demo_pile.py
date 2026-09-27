"""One photo holding a whole onboarding file: the documents of a fictional case lying on a desk.

For the "upload everything at once" demo: the agent must find each document in the photo, cut it
out, straighten it, identify it and sort the file. Built only from the fictional templates written by
`scripts/synthetic_kyc.py --split demo --clean-copies` (never real documents).

    python scripts/demo_pile.py            # eval/synthetic/demo/pile_case00N.jpg for every demo case
"""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'eval' / 'synthetic' / 'demo'
# Width of each document in the photo, as a share of the photo width (IDs are small cards).
WIDTH = {'id_front': .27, 'id_back': .27, 'license': .40, 'tax': .36}
# Where each document lies (centre, as shares of the photo), a little untidily.
PLACES = {'id_front': (.22, .27), 'id_back': (.22, .70), 'license': (.70, .32), 'tax': (.70, .76)}


def desk(h, w, rng):
    """A wooden desk: warm base colour, grain stripes and soft light falloff."""
    base = np.array(rng.choice([[62, 96, 139], [48, 70, 104], [120, 128, 136]]), np.float32)
    y = np.arange(h, dtype=np.float32)[:, None]
    grain = np.sin(y / rng.uniform(5, 9) + np.sin(np.arange(w, dtype=np.float32)[None] / 90) * 3) * 10
    image = base[None, None] + grain[..., None] + rng.normal(0, 4, (h, w, 3))
    yy, xx = np.mgrid[0:h, 0:w]
    light = 1.1 - .35 * (((xx - w * .45) / w) ** 2 + ((yy - h * .4) / h) ** 2)
    return np.clip(image * light[..., None], 0, 255)


def place(canvas, doc, centre, width, angle, rng):
    h, w = doc.shape[:2]
    scale = width / w
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    matrix[:, 2] += np.array(centre) - np.array([w / 2, h / 2])
    size = (canvas.shape[1], canvas.shape[0])
    mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), matrix, size)
    shadow = cv2.GaussianBlur(cv2.warpAffine(mask, np.float32([[1, 0, 6], [0, 1, 9]]), size), (0, 0), 7) / 255.0
    canvas *= 1 - .45 * shadow[..., None]
    warped = cv2.warpAffine(doc.astype(np.float32), matrix, size)
    alpha = cv2.GaussianBlur(mask, (3, 3), 0)[..., None] / 255.0
    canvas[:] = canvas * (1 - alpha) + warped * alpha


def pile(case, rng, width=3600, height=2550):  # a 9 MP phone photo
    canvas = desk(height, width, rng)
    order = list(WIDTH)
    rng.shuffle(order)  # dropped on the desk in any order
    for name in order:
        doc = cv2.imread(str(DEMO / f'case{case:03}_{name}_template.png'))
        if doc is None:
            raise FileNotFoundError(f'run synthetic_kyc.py --split demo --clean-copies first ({name})')
        cx, cy = PLACES[name]
        centre = (cx * width + rng.uniform(-40, 40), cy * height + rng.uniform(-30, 30))
        place(canvas, doc, centre, WIDTH[name] * width, rng.uniform(-9, 9), rng)
    photo = np.clip(canvas * rng.uniform(.85, 1.05) + rng.normal(0, 3, canvas.shape), 0, 255).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (0, 0), .8)
    return cv2.imdecode(cv2.imencode('.jpg', photo, [cv2.IMWRITE_JPEG_QUALITY, 88])[1], cv2.IMREAD_COLOR)


def main():
    labels = json.loads((DEMO / 'labels.json').read_text(encoding='utf-8'))
    cases = sorted({int(i['case'].split('-')[1]) for i in labels['items']})
    rng = np.random.default_rng(99)
    made = []
    for case in cases:
        name = f'pile_case{case:03}.jpg'
        cv2.imwrite(str(DEMO / name), pile(case, rng))
        made.append(name)
    labels['piles'] = [{'file': n, 'case': f'demo-{int(n[9:12]):03}', 'documents': list(WIDTH)} for n in made]
    (DEMO / 'labels.json').write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'piles': made}))


if __name__ == '__main__':
    main()
