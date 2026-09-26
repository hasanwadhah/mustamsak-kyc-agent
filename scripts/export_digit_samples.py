"""Save every handwritten digit the digit reader sees on housing cards, for manual labelling.

Each digit is written as a small black-on-white ink image into
data/digit-samples/_inbox/<what the model read>/ . You check them by eye, move each
file to the folder of the correct digit (data/digit-samples/1 … 9, or noise for
anything that is not a digit), and then retrain with
`scripts/train_digit_cnn.py --extra`. See docs/HANDWRITING.md.

Only digit ink is saved (no names, no whole card), and it stays in data/ on this
computer (data/ is never committed or uploaded).

  python scripts/export_digit_samples.py card1.jpg card2.jpg
  python scripts/export_digit_samples.py --list              (saved batches, newest first)
  python scripts/export_digit_samples.py --batch <batch id>   (or --batch last)
"""
import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import handwritten_digits as hd, storage, vision  # noqa: E402
from app.focused_fields import housing_regions  # noqa: E402
from app.housing_handwriting import digit_model_readings  # noqa: E402

SAMPLES = storage.DATA / 'digit-samples'


def cards(args):
    """(name, image, ocr lines) for each front side of a housing card."""
    for path in args.images:
        image = vision.read_image(Path(path))
        yield Path(path).stem, image, vision.ocr(image)
    if args.batch:
        if args.batch == 'last':
            args.batch = storage.list_batches()[0]['id']
        batch = storage.get_batch(args.batch)
        for d in batch['documents']:
            if d['kind'] == 'housing' and d.get('side') == 'front':
                image = vision.read_image(storage.image_path(d['image_id']))
                lines = d.get('ocr', []) if d.get('field_image_id') == d['image_id'] else vision.ocr(image)
                yield f"{args.batch[:8]}-{d['image_id'][:8]}", image, lines


def export(name, image, lines, out):
    hd.collector = []
    try:
        digit_model_readings(image, housing_regions(image, lines, 'front'), lines)
        found = hd.collector
    finally:
        hd.collector = None
    for i, piece in enumerate(found):
        folder = out / str(piece['digit'])
        folder.mkdir(parents=True, exist_ok=True)
        ink = cv2.copyMakeBorder(piece['mask'], 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=0)
        # imencode + tofile: cv2.imwrite cannot write to non-ASCII (e.g. Arabic) folder names on Windows.
        cv2.imencode('.png', 255 - ink)[1].tofile(str(folder / f"{name}-{i:02}-p{round(100 * piece['probability'])}.png"))
    return len(found)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # Arabic batch names on a Windows console
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('images', nargs='*', help='photos or scans of the FRONT of housing cards')
    parser.add_argument('--batch', help='a saved batch id (or "last"): export its housing card fronts')
    parser.add_argument('--list', action='store_true', help='show saved batches and their ids')
    parser.add_argument('--out', default=str(SAMPLES / '_inbox'))
    args = parser.parse_args()
    if args.list:
        for b in storage.list_batches():
            print(f"{b['id']}  {b['created'][:16]}  {b['count']:3} images  {b['name']}")
        return
    if not args.images and not args.batch:
        parser.error('give card images or --batch')
    if not hd.available():
        sys.exit('The digit model is missing: run setup.ps1 or scripts/train_digit_cnn.py first.')
    out = Path(args.out)
    total = 0
    for name, image, lines in cards(args):
        count = export(name, image, lines, out)
        total += count
        print(f'{name}: {count} digit pieces')
    print(f'{total} pieces saved under {out}. Move each file to data/digit-samples/<correct digit or noise>/.')


if __name__ == '__main__':
    main()
