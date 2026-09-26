"""Measure extraction accuracy, confidence calibration and KYC routing on synthetic splits.

  python scripts/evaluate_kyc.py --split tune --fit      # extract, fit calibration on tune only
  python scripts/evaluate_kyc.py --split heldout         # report on documents never tuned on
  add --reuse to re-score cached extractions without running OCR again

Generate the splits first with scripts/synthetic_kyc.py. Extraction runs the real
local pipeline (segmentation, OCR, field reading) with network access unused and
all app data written to a throwaway directory, never the user's data folder.
"""
import argparse
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ['MUSTAMSAK_DATA'] = tempfile.mkdtemp(prefix='mustamsak-eval-')
sys.path.insert(0, str(ROOT))
from app import kyc, pipeline, storage, vision  # noqa: E402

SYNTHETIC = ROOT / 'eval' / 'synthetic'
RESULTS = ROOT / 'eval' / 'results'
REPORTS = ROOT / 'eval' / 'reports'
REFERENCE_DAY = date(2026, 9, 23)
TEXT_KEYS = {'name', 'first_name', 'father_name', 'grandfather_name', 'surname', 'mother_name', 'business_name', 'activity',
             'birth_place', 'issuing_authority', 'address', 'sex'}


# ------------------------------------------------------------------ extraction
def extract(split, reuse):
    cache = RESULTS / f'{split}.json'
    if reuse and cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))
    labels = json.loads((SYNTHETIC / split / 'labels.json').read_text(encoding='utf-8'))
    out = []
    for n, item in enumerate(labels['items'], 1):
        started = time.monotonic()
        data = (SYNTHETIC / split / item['file']).read_bytes()
        image, page = next(pipeline.pages_from_bytes(data, item['file']))
        source = {'id': storage.uid(), 'name': item['file'], 'page': page, 'width': image.shape[1], 'height': image.shape[0]}
        docs = []
        for i, region in enumerate(vision.detect_regions(image)):
            try:
                docs.append(pipeline.make_document(image, source, region, i))
            except ValueError:
                continue
        chosen = max(docs, key=lambda d: ((d['kind'], d['side']) == (item['kind'], item['side']), d['kind'] == item['kind'],
                                          d['width'] * d['height']), default=None)
        if chosen:
            chosen = {k: v for k, v in chosen.items() if k not in ('ocr',)}
        out.append(dict(item, doc=chosen, regions=len(docs), seconds=round(time.monotonic() - started, 2)))
        print(f'[{split}] {n}/{len(labels["items"])} {item["file"]} -> {chosen and chosen["kind"]}:{chosen and chosen["side"]} '
              f'({out[-1]["seconds"]}s)', flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    return out


# ------------------------------------------------------------------ scoring
def same(key, truth, value):
    if key.endswith('_date'):
        return kyc.parse_date(value) is not None and kyc.parse_date(value) == kyc.parse_date(truth)
    if key in TEXT_KEYS:
        return kyc.name_tokens(value) == kyc.name_tokens(truth)
    clean = lambda v: re.sub(r'[\s/-]', '', str(v).translate(kyc.DIGITS)).upper()
    return clean(value) == clean(truth)


def records(items):
    """One row per ground-truth field, scored through the production KYC path.

    Confidence comes from kyc.assess_documents on the whole case (so cross-document
    corroboration is included), before calibration.
    """
    saved = kyc.calibration
    kyc.calibration = lambda: None
    try:
        by_case = defaultdict(list)
        for item in items:
            by_case[item['case']].append(item)
        rows = []
        for members in by_case.values():
            docs = [m['doc'] for m in members if m['doc']]
            verdict = kyc.assess_documents(docs, 'merchant', .9, REFERENCE_DAY) if docs else {'documents': []}
            assessed = {(e['id'], f['key']): f for e in verdict['documents'] for f in e['fields']}
            for item in members:
                doc = item['doc']
                critical = kyc.CRITICAL.get((item['kind'], item['side']), [])
                for key, truth in item['fields'].items():
                    f = assessed.get((doc['id'], key)) if doc else None
                    value = str((f or {}).get('value') or '').strip()
                    rows.append({'file': item['file'], 'level': item['level'], 'kind': item['kind'], 'side': item['side'],
                                 'key': key, 'critical': key in critical, 'truth': truth, 'value': value, 'blank': not value,
                                 'correct': bool(value) and same(key, truth, value),
                                 'raw': (f or {}).get('raw_confidence', 0.0), 'basis': (f or {}).get('basis', 'missing')})
        return rows
    finally:
        kyc.calibration = saved


def isotonic(pairs, min_block=10):
    """Monotone calibration curve from (score, correct) pairs.

    1. Pool tied scores (many fields share a capped score such as 0.80).
    2. Pool-adjacent-violators so accuracy never decreases with score.
    3. Merge blocks smaller than `min_block` into a neighbour (tiny blocks are noise).
    4. Beta(1,1) smoothing, then a running maximum to keep the curve monotone.
    Each block becomes one point at its sample-weighted mean score.
    """
    ties = {}
    for x, y in pairs:
        s, n, sx = ties.get(x, (0, 0, 0.0))
        ties[x] = (s + y, n + 1, sx + x)
    blocks = []  # [correct, count, sum_of_scores]
    for x in sorted(ties):
        blocks.append(list(ties[x]))
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n, sx = blocks.pop()
            blocks[-1][0] += s; blocks[-1][1] += n; blocks[-1][2] += sx
    while len(blocks) > 1 and min(b[1] for b in blocks) < min_block:
        i = min(range(len(blocks)), key=lambda k: blocks[k][1])
        j = i - 1 if i == len(blocks) - 1 or (i > 0 and blocks[i - 1][1] < blocks[i + 1][1]) else i + 1
        a, b = sorted((i, j))
        blocks[a] = [blocks[a][k] + blocks[b][k] for k in range(3)]
        del blocks[b]
    points, floor = [], 0.0
    for s, n, sx in blocks:
        floor = max(floor, (s + 1) / (n + 2))
        points.append([round(sx / n, 4), round(floor, 4)])
    return [[0.0, points[0][1]]] + points + [[1.0, points[-1][1]]]


def ece(rows, key='conf', bins=10):
    scored = [r for r in rows if not r['blank']]
    if not scored:
        return None, []
    table, total = [], 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        inside = [r for r in scored if lo <= r[key] < hi or (b == bins - 1 and r[key] == 1)]
        if not inside:
            continue
        conf = sum(r[key] for r in inside) / len(inside)
        acc = sum(r['correct'] for r in inside) / len(inside)
        total += len(inside) / len(scored) * abs(acc - conf)
        table.append({'bin': f'{lo:.1f}-{hi:.1f}', 'n': len(inside), 'mean_confidence': round(conf, 3), 'accuracy': round(acc, 3)})
    return round(total, 4), table


def rate(part, whole):
    return round(part / whole, 4) if whole else None


def summarize_fields(rows, threshold):
    def block(subset):
        n = len(subset)
        read = [r for r in subset if not r['blank']]
        accepted = [r for r in subset if not r['blank'] and r['conf'] >= threshold]
        return {'fields': n, 'read_rate': rate(len(read), n), 'accuracy_when_read': rate(sum(r['correct'] for r in read), len(read)),
                'misread_rate': rate(sum(not r['correct'] for r in read), n), 'auto_accepted_rate': rate(len(accepted), n),
                'accuracy_of_auto_accepted': rate(sum(r['correct'] for r in accepted), len(accepted)),
                'routed_to_human_rate': rate(n - len(accepted), n)}
    by = lambda attr: {k: block([r for r in rows if r[attr] == k]) for k in sorted({r[attr] for r in rows})}
    return {'overall': block(rows), 'critical': block([r for r in rows if r['critical']]), 'by_level': by('level'),
            'by_kind': by('kind'), 'by_key': by('key')}


def capture_metrics(items):
    def flagged(item, code=None):
        issues = (item['doc'] or {}).get('capture') or []
        return any(i['severity'] == 'retake' and (code is None or i['code'] == code) for i in issues)
    out = {}
    for level in ('clean', 'poor', 'worst'):
        subset = [i for i in items if i['level'] == level]
        out[f'retake_rate_{level}'] = rate(sum(flagged(i) for i in subset), len(subset))
    cut = [i for i in items if any(d.startswith('cut_off') for d in i['degradations'])]
    out['cut_off_recall'] = rate(sum(flagged(i, 'cut_off') for i in cut), len(cut))
    out['cut_off_images'] = len(cut)
    uncut = [i for i in items if not any(d.startswith('cut_off') for d in i['degradations'])]
    out['cut_off_false_alarm_rate'] = rate(sum(flagged(i, 'cut_off') for i in uncut), len(uncut))
    glare = [i for i in items if 'glare' in i['degradations']]
    out['glare_detected_rate'] = rate(sum(any(x['code'] == 'glare' for x in (i['doc'] or {}).get('capture') or []) for i in glare), len(glare))
    out['classification_accuracy'] = rate(sum(bool(i['doc']) and i['doc']['kind'] == i['kind'] and i['doc']['side'] == i['side']
                                              for i in items), len(items))
    return out


def case_metrics(items, rows, threshold):
    cases = defaultdict(list)
    for item in items:
        cases[item['case']].append(item)
    correct = {(r['file'], r['key']): r['correct'] for r in rows}
    results = []
    for case, members in sorted(cases.items()):
        docs = [dict(m['doc'], id=m['doc'].get('id') or m['file']) for m in members if m['doc']]
        verdict = kyc.assess_documents(docs, 'merchant', threshold, REFERENCE_DAY)
        problem = members[0]['case_problem']
        codes = {r['code'] for r in verdict['reasons'] if r['severity'] == 'block'}
        detected = {None: None, 'name_mismatch': 'cross_name_match' in codes, 'expired_license': 'expired' in codes,
                    'serial_mismatch': 'cross_document_number_match' in codes}[problem]
        wrong_critical = [f'{m["document"]}:{k}' for m in members for k in kyc.CRITICAL.get((m['kind'], m['side']), [])
                          if (m['file'], k) in correct and not correct[(m['file'], k)]]
        results.append({'case': case, 'problem': problem, 'levels': [m['level'] for m in members], 'decision': verdict['decision'],
                        'blocking_reasons': len(codes), 'problem_named': detected,
                        'wrong_critical_fields': wrong_critical, 'summary_en': verdict['summary_en']})
    flawed = [c for c in results if c['problem']]
    clean_cases = [c for c in results if not c['problem']]
    passed = [c for c in results if c['decision'] == 'pass']
    # A consistent case can only rightly pass if every critical field was read correctly.
    passable = [c for c in clean_cases if not c['wrong_critical_fields']]
    return {'cases': len(results), 'flawed_cases': len(flawed),
            'false_pass_on_flawed_cases': sum(c['decision'] == 'pass' for c in flawed),
            'flaw_named_in_summary_rate': rate(sum(bool(c['problem_named']) for c in flawed), len(flawed)),
            'auto_pass_rate_consistent_cases': rate(sum(c['decision'] == 'pass' for c in clean_cases), len(clean_cases)),
            'consistent_cases_fully_read': len(passable),
            'auto_pass_rate_fully_read_cases': rate(sum(c['decision'] == 'pass' for c in passable), len(passable)),
            'passed_with_wrong_critical_field': sum(bool(c['wrong_critical_fields']) for c in passed),
            'details': results}


def evaluate(split, items, table, threshold):
    kyc.calibration = lambda: table  # Evaluate with exactly this table.
    rows = records(items)
    for r in rows:
        r['conf'] = kyc.calibrated(r['raw'], r['basis'], table)
    raw_ece, _ = ece(rows, 'raw')
    cal_ece, reliability = ece(rows, 'conf')
    return {'split': split, 'threshold': threshold, 'images': len(items), 'calibrated': bool(table),
            'fields': summarize_fields(rows, threshold),
            'calibration': {'ece_raw': raw_ece, 'ece_calibrated': cal_ece, 'reliability': reliability},
            'capture': capture_metrics(items), 'kyc': case_metrics(items, rows, threshold),
            'seconds_per_image': round(sum(i['seconds'] for i in items) / max(1, len(items)), 2)}, rows


# ------------------------------------------------------------------ report
def pct(v):
    return '—' if v is None else f'{v * 100:.1f}%'


def markdown(report):
    f, c, k, cal = report['fields'], report['capture'], report['kyc'], report['calibration']
    lines = [f'# KYC evaluation — {report["split"]} split', '',
             f'Generated {report["created"]}. {report["images"]} images, threshold {report["threshold"]:.2f}, '
             f'calibration {"applied" if report["calibrated"] else "not applied"}. Synthetic, fictional documents only.', '',
             '## Fields', '', '| scope | fields | read | accuracy when read | misread | auto-accepted | accuracy of auto-accepted | routed to human |',
             '|---|---|---|---|---|---|---|---|']
    def row(name, b):
        lines.append(f'| {name} | {b["fields"]} | {pct(b["read_rate"])} | {pct(b["accuracy_when_read"])} | {pct(b["misread_rate"])} | '
                     f'{pct(b["auto_accepted_rate"])} | {pct(b["accuracy_of_auto_accepted"])} | {pct(b["routed_to_human_rate"])} |')
    row('all', f['overall']); row('critical', f['critical'])
    for name, b in f['by_level'].items():
        row(f'level: {name}', b)
    for name, b in f['by_kind'].items():
        row(f'kind: {name}', b)
    lines += ['', '### By field', '', '| field | fields | read | accuracy when read | auto-accepted | accuracy of auto-accepted |', '|---|---|---|---|---|---|']
    for name, b in f['by_key'].items():
        lines.append(f'| {name} | {b["fields"]} | {pct(b["read_rate"])} | {pct(b["accuracy_when_read"])} | {pct(b["auto_accepted_rate"])} | '
                     f'{pct(b["accuracy_of_auto_accepted"])} |')
    lines += ['', '## Calibration', '', f'Expected calibration error: raw {cal["ece_raw"]}, calibrated {cal["ece_calibrated"]} '
              '(lower is better; 0 means stated confidence equals observed accuracy).', '',
              '| confidence bin | fields | mean confidence | observed accuracy |', '|---|---|---|---|']
    for b in cal['reliability']:
        lines.append(f'| {b["bin"]} | {b["n"]} | {pct(b["mean_confidence"])} | {pct(b["accuracy"])} |')
    lines += ['', '## Capture guidance', '', '| measure | value |', '|---|---|']
    for key, value in c.items():
        lines.append(f'| {key} | {pct(value) if isinstance(value, float) else value} |')
    lines += ['', '## KYC decisions', '', f'- Cases: {k["cases"]} ({k["flawed_cases"]} with a planted inconsistency)',
              f'- False passes on flawed cases: **{k["false_pass_on_flawed_cases"]}**',
              f'- Planted flaw named in the reviewer summary: {pct(k["flaw_named_in_summary_rate"])}',
              f'- Automatic pass rate on consistent cases: {pct(k["auto_pass_rate_consistent_cases"])}',
              f'- Consistent cases where every critical field was read correctly: {k["consistent_cases_fully_read"]} '
              f'(automatic pass rate among them: {pct(k["auto_pass_rate_fully_read_cases"])})',
              f'- Passed cases containing a wrong critical field: **{k["passed_with_wrong_critical_field"]}**', '',
              '| case | planted problem | photo levels | decision | problem named | wrong critical fields |', '|---|---|---|---|---|---|']
    for d in k['details']:
        lines.append(f'| {d["case"]} | {d["problem"] or "—"} | {", ".join(d["levels"])} | {d["decision"]} | '
                     f'{"—" if d["problem_named"] is None else "yes" if d["problem_named"] else "no"} | {len(d["wrong_critical_fields"])} |')
    example = next((d for d in k['details'] if d['decision'] == 'review'), None)
    if example:
        lines += ['', '### Example reviewer summary', '', '```', example['summary_en'], '```']
    lines += ['', f'Average processing time: {report["seconds_per_image"]} s per image (CPU).', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['tune', 'heldout'], required=True)
    parser.add_argument('--fit', action='store_true', help='fit and save calibration (tune split only)')
    parser.add_argument('--reuse', action='store_true', help='reuse cached extractions')
    parser.add_argument('--threshold', type=float, default=None)
    args = parser.parse_args()
    if args.fit and args.split != 'tune':
        parser.error('Calibration may only be fitted on the tune split.')
    threshold = args.threshold or kyc.policy()['threshold']
    items = extract(args.split, args.reuse)
    table = kyc.load_json(kyc.CALIBRATION_PATH)
    if args.fit:
        rows = records(items)
        pairs = [(r['raw'], int(r['correct'])) for r in rows if not r['blank'] and r['basis'] != 'human']
        if len(pairs) < 30:
            raise SystemExit('Not enough read fields to fit a calibration (need 30).')
        table = {'points': isotonic(pairs), 'fitted_on': 'tune', 'samples': len(pairs), 'created': date.today().isoformat(),
                 'method': 'isotonic regression (pool adjacent violators), additive smoothing 0.5'}
        kyc.CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        kyc.CALIBRATION_PATH.write_text(json.dumps(table, indent=2), encoding='utf-8')
        print(f'Calibration saved: {kyc.CALIBRATION_PATH} ({len(pairs)} samples)')
    report, _ = evaluate(args.split, items, table, threshold)
    report['created'] = date.today().isoformat()
    if not args.fit:
        report['uncalibrated_comparison'], _ = evaluate(args.split, items, None, threshold)
        report['uncalibrated_comparison'].pop('kyc', None)
    if args.split == 'heldout' and table:
        table['heldout'] = {'ece': report['calibration']['ece_calibrated'], 'date': report['created']}
        kyc.CALIBRATION_PATH.write_text(json.dumps(table, indent=2), encoding='utf-8')
    REPORTS.mkdir(parents=True, exist_ok=True)
    base = REPORTS / f'kyc-{args.split}'
    base.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    base.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))


if __name__ == '__main__':
    main()
