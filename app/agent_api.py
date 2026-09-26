"""Routes for the KYC agent screen (static/agent.html): fictional demo files and the evaluation report.

Demo files come only from `eval/synthetic/demo` (scripts/synthetic_kyc.py --split demo and
scripts/demo_pile.py): fictional people, never scored, never real documents. They go through
exactly the same reading path as an upload (main.start_batch).
"""
import json
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'eval' / 'synthetic' / 'demo'
REPORTS = ROOT / 'eval' / 'reports'
FILE_NAME = re.compile(r'^(?:case\d{3}_(?:id_front|id_back|license|tax)|pile_case\d{3})\.jpg$')
ORDER = ('id_front', 'id_back', 'license', 'tax')
router = APIRouter()


def _labels():
    try:
        return json.loads((DEMO / 'labels.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'items': [], 'piles': []}


def demo_cases():
    """Each fictional case: its four photos, how badly each was photographed, and its planted problem."""
    labels = _labels()
    cases = {}
    for item in labels['items']:
        case = cases.setdefault(item['case'], {'id': item['case'], 'problem': item.get('case_problem'), 'files': [],
                                               'levels': {}, 'pile': None})
        case['files'].append(item['file'])
        case['levels'][item['document']] = item['level']
    for pile in labels.get('piles', []):
        if pile['case'] in cases and (DEMO / pile['file']).exists():
            cases[pile['case']]['pile'] = pile['file']
    for case in cases.values():
        case['files'].sort(key=lambda f: next((i for i, d in enumerate(ORDER) if f'_{d}.' in f), 9))
        levels = list(case['levels'].values())
        case['worst_level'] = 'worst' if 'worst' in levels else 'poor' if 'poor' in levels else 'clean'
    return sorted(cases.values(), key=lambda c: c['id'])


@router.get('/api/demo/cases')
def cases():
    return {'fictional': True, 'cases': demo_cases()}


@router.get('/api/demo/files/{name}')
def demo_file(name: str):
    if not FILE_NAME.match(name) or not (DEMO / name).is_file():
        raise HTTPException(404, 'Demo file not found.')
    return FileResponse(DEMO / name, media_type='image/jpeg')


class DemoStart(BaseModel):
    mode: Literal['separate', 'pile'] = 'separate'


@router.post('/api/demo/cases/{case_id}', status_code=202)
def start_demo(case_id: str, body: DemoStart):
    from . import main, storage
    case = next((c for c in demo_cases() if c['id'] == case_id), None)
    if case is None:
        raise HTTPException(404, 'Demo case not found.')
    names = [case['pile']] if body.mode == 'pile' and case['pile'] else case['files']
    items = [(n, (DEMO / n).read_bytes()) for n in names]
    with main.queue_lock:
        if len(main.pending) >= 3:
            raise HTTPException(429, 'Other files are being read; wait for one to finish.')
        token = storage.uid()
        main.pending.add(token)
    try:
        label = f'Demo {case_id}' + (' · one photo' if body.mode == 'pile' else '')
        return main.start_batch(items, token, label)
    except Exception:
        with main.queue_lock:
            main.pending.discard(token)
        raise


@router.get('/api/evaluation')
def evaluation():
    """The latest synthetic evaluation (scripts/evaluate_kyc.py): held-out = never tuned on."""
    out = {}
    for split in ('heldout', 'tune'):
        try:
            report = json.loads((REPORTS / f'kyc-{split}.json').read_text(encoding='utf-8'))
            report.get('kyc', {}).pop('details', None)
            out[split] = report
        except (OSError, ValueError):
            out[split] = None
    return out


@router.get('/workspace')
def workspace():
    return FileResponse(ROOT / 'static' / 'index.html')
