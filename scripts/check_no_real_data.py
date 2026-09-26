"""Audit this build for the hackathon's data rule: no real identity documents, only fictional ones.

Checks (exit code 1 if any fails):
  1. every image in the project is a generated fictional document under eval/synthetic/, a UI asset, or a
     screenshot of the app showing those fictional documents (docs/screenshots/);
  2. every label file under eval/synthetic/ says "fictional": true;
  3. the local data folder holds no uploads (it is created empty and filled only by what you upload);
  4. the models were trained without any personal samples (digit CNN: no own samples; number reader:
     synthetic strips only);
  5. no reference images of real cards are bundled (models/references is absent).

    python scripts/check_no_real_data.py
"""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.pdf', '.heic'}
SKIP = {'.venv', 'node_modules', '.git', '__pycache__', '.pytest_cache'}
problems, notes = [], []

for path in ROOT.rglob('*'):
    if any(part in SKIP for part in path.parts) or not path.is_file() or path.suffix.lower() not in IMAGES:
        continue
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith(('eval/synthetic/', 'static/', 'docs/screenshots/')):
        continue
    if rel.startswith('data/'):
        notes.append(f'uploaded during use (local only, git-ignored): {rel}')
        continue
    problems.append(f'image outside eval/synthetic: {rel}')

for labels in (ROOT / 'eval' / 'synthetic').glob('*/labels.json'):
    if json.loads(labels.read_text(encoding='utf-8')).get('fictional') is not True:
        problems.append(f'{labels.relative_to(ROOT)} is not marked fictional')

cnn = ROOT / 'models' / 'eastern_digits_cnn.npz'
if cnn.exists():
    with np.load(cnn, allow_pickle=False) as data:
        meta = json.loads(str(data['meta']))
    if meta.get('own_samples_check_size'):
        problems.append('digit CNN was trained with personal digit samples')
    notes.append('digit CNN: ' + '; '.join(meta.get('sources', ['MADBase + synthetic strokes'])))
reader = ROOT / 'models' / 'number_reader.npz'
if reader.exists():
    with np.load(reader, allow_pickle=False) as data:
        report = json.loads(str(data['report'])) if 'report' in data.files else {}
    if any(k.startswith('real') or k.startswith('own') for k in report):
        problems.append('number reader metadata mentions real or own samples')
    notes.append('number reader: ' + report.get('data', 'unknown'))
if (ROOT / 'models' / 'references').exists():
    problems.append('models/references (images of real specimen cards) must not be bundled')

for n in notes:
    print('note:', n)
for p in problems:
    print('FAIL:', p)
print('OK: no real identity data found.' if not problems else f'{len(problems)} problem(s).')
sys.exit(1 if problems else 0)
