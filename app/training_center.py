"""The AI training dashboard (static/training-ui.js): see, track and guide the readers.

- Overview: each model (digit CNN, own number reader), its metrics, version and backup.
- Data: the samples learned from the reviewer's corrections, browsable; a wrong label can be
  fixed or a bad sample deleted (the most direct way to guide training).
- Evaluate: each reader on the reviewer's own samples; kept-aside samples (never trained on)
  give the honest figure, the rest show what it has learned.
- Training: start (which models, how long), live progress parsed from the training log, stop.
- History and rollback: every run with its outcome; the previous model can be restored (and
  restored back: rollback swaps the two files).
Everything stays on this computer.
"""
import json
import re
import time
from pathlib import Path

import cv2
import numpy as np

from . import learning, storage

DIGIT_LABELS = [str(d) for d in range(1, 10)] + ['noise']
DIGIT_ID = re.compile(r'^(?:[1-9]|noise)/[\w.\-]{1,120}\.png$')
STRIP_ID = re.compile(r'^\d{1,7}__[\w.\-]{1,120}\.png$')
FIELD_NAMES = {'mahalla_number': 'محلة', 'street': 'زقاق', 'house_number': 'دار', 'form_number': 'استمارة'}


def eval_file():
    return storage.DATA / 'training-eval.json'


def _mtime(path):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(path.stat().st_mtime)) if path.exists() else None


def models():
    from . import handwritten_digits as hd, number_reader as nr
    digit_prev = hd.CNN_PATH.with_name('eastern_digits_cnn.previous.npz')
    number_prev = nr.MODEL_PATH.with_name('number_reader.previous.npz')
    digits = learning._meta(hd.CNN_PATH)
    numbers = learning.model_report()
    return [
        {'id': 'digits', 'name': 'قارئ الأرقام رقمًا رقمًا', 'kind': 'CNN', 'exists': hd.CNN_PATH.exists(),
         'updated': _mtime(hd.CNN_PATH), 'previous': _mtime(digit_prev),
         'metrics': {'خط يد كتّاب لم يرهم (MADBase)': digits.get('madbase_test_accuracy'),
                     'تحت الأختام': digits.get('madbase_test_accuracy_under_overlap'),
                     'أرقام مولّدة': digits.get('synthetic_accuracy'),
                     'أرقامك المحجوزة': digits.get('own_samples_check_accuracy')}},
        {'id': 'numbers', 'name': 'قارئ الأرقام الخاص (الرقم كاملًا)', 'kind': 'CNN + CTC', 'exists': nr.MODEL_PATH.exists(),
         'updated': _mtime(nr.MODEL_PATH), 'previous': _mtime(number_prev),
         'metrics': {'أرقام كاملة لكتّاب لم يرهم': numbers.get('held_out_whole_number_accuracy'),
                     'شرائح بطاقات حقيقية': numbers.get('real_whole_number_accuracy'),
                     'شرائحك المحجوزة': numbers.get('own_check_accuracy')},
         'steps': numbers.get('steps')},
    ]


def _digit_files():
    out = []
    root = learning.samples_dir()
    for label in DIGIT_LABELS:
        files = sorted((root / label).glob('*.png')) if (root / label).exists() else []
        # Same rule as scripts/train_digit_cnn.py: every 5th file of a label is kept aside.
        out += [(f'{label}/{p.name}', label, i % 5 == 4, p) for i, p in enumerate(files)]
    return out


def _strip_files():
    from .number_reader import kept_aside
    folder = learning.strips_dir()
    files = sorted(folder.glob('*.png'), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
    return [(p.name, p.name.split('__')[0], kept_aside(p.name), p) for p in files if STRIP_ID.match(p.name)]


def _field_of(name):
    for key, label in FIELD_NAMES.items():
        if f'__{key}-' in name or f'-{key}-' in name:
            return label
    return ''


def data_summary():
    digits = _digit_files()
    strips = _strip_files()
    try:
        names = json.loads(learning.names_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        names = {}
    return {'digits': {label: sum(1 for _, l, _, _ in digits if l == label) for label in DIGIT_LABELS},
            'digits_kept_aside': sum(1 for d in digits if d[2]),
            'strips': len(strips), 'strips_kept_aside': sum(1 for s in strips if s[2]),
            'strips_by_field': {v: sum(1 for s in strips if _field_of(s[0]) == v) for v in FIELD_NAMES.values()},
            'name_words': len(names), 'top_names': sorted(names, key=names.get, reverse=True)[:12],
            'min_samples': learning.MIN_SAMPLES, 'min_strips': learning.MIN_STRIPS}


def list_samples(kind, label=None, offset=0, limit=60):
    rows = _digit_files() if kind == 'digits' else _strip_files()
    if label:
        rows = [r for r in rows if r[1] == label]
    items = [{'id': sid, 'label': lab, 'kept_aside': kept, 'field': _field_of(sid),
              'from_correction': 'corr-' in sid or '__' in sid, 'added': _mtime(path)}
             for sid, lab, kept, path in rows[offset:offset + limit]]
    return {'kind': kind, 'total': len(rows), 'offset': offset, 'items': items}


def sample_path(kind, sid):
    """The file for a sample id, only inside its own folder (ids are validated, never trusted)."""
    pattern, root = (DIGIT_ID, learning.samples_dir()) if kind == 'digits' else (STRIP_ID, learning.strips_dir())
    if kind not in ('digits', 'strips') or not pattern.match(sid or ''):
        raise ValueError('معرّف عينة غير صالح.')
    path = (root / sid).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(sid)
    return path


def relabel(kind, sid, label):
    """Fix a wrong label: a digit sample moves to its right folder, a strip is renamed to its right value."""
    path = sample_path(kind, sid)
    if kind == 'digits':
        if label not in DIGIT_LABELS:
            raise ValueError('التصنيف يجب أن يكون رقمًا من 1 إلى 9 أو «ليس رقمًا».')
        folder = learning.samples_dir() / label
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        n = 1
        while target.exists():
            target = folder / f'{path.stem}-{n}.png'
            n += 1
        path.rename(target)
        return f'{label}/{target.name}'
    if not re.fullmatch(r'\d{1,7}', label or ''):
        raise ValueError('القيمة يجب أن تكون أرقامًا فقط (حتى 7).')
    target = path.with_name(f'{label}__{path.name.split("__", 1)[1]}')
    if target.exists() and target != path:
        raise ValueError('توجد عينة بالاسم نفسه.')
    path.rename(target)
    return target.name


def delete(kind, sid):
    sample_path(kind, sid).unlink()


def _digit_mask(path):
    from .handwritten_digits import pen_mask
    rgb = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if np.isin(gray, (0, 255)).mean() > .98:  # an exported ink image (as scripts/train_digit_cnn.ink_of)
        return np.where(gray < 128, 255, 0).astype(np.uint8) if gray.mean() > 127 else np.where(gray > 127, 255, 0).astype(np.uint8)
    return pen_mask(rgb)[0]


def evaluate():
    """Both readers on the reviewer's own samples. Kept-aside samples are the honest test."""
    from . import handwritten_digits as hd, number_reader as nr
    started = time.time()
    out = {'when': time.strftime('%Y-%m-%d %H:%M'), 'digits': None, 'numbers': None}
    digit_rows = _digit_files()
    if digit_rows and hd.available():
        results, confusion = [], {}
        for sid, label, kept, path in digit_rows:
            mask = _digit_mask(path)
            if not mask.any():
                continue
            predicted = str(hd.CLASSES[int(np.argmax(hd.probabilities(mask)))])
            results.append((kept, predicted == label))
            if predicted != label:
                pair = f'{label}→{predicted}'
                confusion[pair] = confusion.get(pair, 0) + 1
        out['digits'] = _summary(results) | {'confusions': sorted(confusion.items(), key=lambda kv: -kv[1])[:8]}
    strip_rows = _strip_files()
    if strip_rows and nr.available():
        results, mistakes, confusion = [], [], {}
        for sid, label, kept, path in strip_rows:
            rgb = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            r = nr.read(rgb)
            value = r['value'] if r else ''
            results.append((kept, value == label))
            if value != label:
                mistakes.append({'id': sid, 'label': label, 'read': value, 'kept_aside': kept})
                if len(value) == len(label):
                    for a, b in zip(label, value):
                        if a != b:
                            confusion[f'{a}→{b}'] = confusion.get(f'{a}→{b}', 0) + 1
        out['numbers'] = _summary(results) | {'mistakes': mistakes[:40],
                                              'confusions': sorted(confusion.items(), key=lambda kv: -kv[1])[:8]}
    out['seconds'] = round(time.time() - started, 1)
    try:
        past = json.loads(eval_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        past = []
    storage.atomic_write(eval_file(), json.dumps((past + [out])[-60:], ensure_ascii=False, indent=1))
    return out


def _summary(results):
    kept = [ok for k, ok in results if k]
    seen = [ok for k, ok in results if not k]
    rate = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
    return {'total': len(results), 'accuracy': rate([ok for _, ok in results]),
            'kept_aside': len(kept), 'kept_aside_accuracy': rate(kept), 'trained_on': len(seen), 'trained_on_accuracy': rate(seen)}


def evaluations():
    try:
        return json.loads(eval_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def progress():
    """Live view of the current (or last) run, parsed from its part of the training log."""
    state = learning._training_state()
    log = learning.log_file()
    text = ''
    if log.exists() and state.get('log_offset') is not None:
        with log.open('rb') as f:
            f.seek(int(state['log_offset']))
            text = f.read().decode('utf-8', 'replace')
    phase, total = None, None
    numbers = {'steps': [], 'loss': [], 'held_out': []}
    digits = {'epochs': []}
    for line in text.splitlines():
        if line.startswith('=== phase'):
            phase = line.split()[-1]
        elif m := re.match(r'plan steps (\d+)', line):
            total = int(m.group(1))
        elif m := re.match(r'step (\d+) loss ([\d.]+)', line):
            numbers['steps'].append(int(m.group(1)))
            numbers['loss'].append(float(m.group(2)))
        elif m := re.search(r'held-out writers: ([\d.]+)%.*?(?:step (\d+))?\)?$', line):
            numbers['held_out'].append([int(m.group(2)) if m.group(2) else (numbers['steps'][-1] if numbers['steps'] else 0),
                                        float(m.group(1)) / 100])
        elif m := re.match(r'epoch (\d+): synthetic ([\d.]+)', line):
            digits['epochs'].append([int(m.group(1)), float(m.group(2))])
    lines = [l for l in text.splitlines() if l.strip()]
    return {'state': state, 'phase': phase, 'total_steps': total, 'numbers': numbers, 'digits': digits,
            'tail': lines[-25:]}


def rollback(model):
    """Swap the model with its saved previous version (so a rollback can itself be undone)."""
    from . import handwritten_digits as hd, number_reader as nr
    if learning._training and learning._training.is_alive():
        raise RuntimeError('لا يمكن الرجوع أثناء التدريب.')
    if model == 'digits':
        current, previous = hd.CNN_PATH, hd.CNN_PATH.with_name('eastern_digits_cnn.previous.npz')
    elif model == 'numbers':
        current, previous = nr.MODEL_PATH, nr.MODEL_PATH.with_name('number_reader.previous.npz')
    else:
        raise ValueError('نموذج غير معروف.')
    if not previous.exists():
        raise RuntimeError('لا توجد نسخة سابقة لهذا النموذج.')
    swap = current.with_suffix('.swap')
    current.replace(swap)
    previous.replace(current)
    swap.replace(previous)
    hd._cnn = None
    nr.reset()
    learning._add_history({'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'finished': time.strftime('%Y-%m-%d %H:%M:%S'),
                           'state': 'rollback', 'models': [model], 'message': 'رجوع إلى النسخة السابقة (يمكن التراجع عنه).'})
    return models()


def advice():
    """Plain suggestions for guiding the training, from the data and the last evaluation."""
    data = data_summary()
    tips = []
    weak = [d for d in DIGIT_LABELS[:-1] if data['digits'][d] < 5]
    if weak:
        tips.append(f'عينات قليلة للأرقام: {"، ".join(weak)}. صحّح أو اعتمد بطاقات فيها هذه الأرقام.')
    if data['strips'] < data['min_strips']:
        tips.append(f'شرائح الأرقام الكاملة: {data["strips"]} من {data["min_strips"]} اللازمة لتحسين قارئ الأرقام الخاص بخطوط مكاتبكم.')
    if sum(data['digits'].values()) < data['min_samples']:
        tips.append(f'عينات الأرقام المفردة: {sum(data["digits"].values())} من {data["min_samples"]} اللازمة لتدريب قارئ الأرقام رقمًا رقمًا.')
    past = evaluations()
    if past:
        last = past[-1]
        for key, name in (('numbers', 'قارئ الأرقام الخاص'), ('digits', 'قارئ الأرقام رقمًا رقمًا')):
            s = last.get(key) or {}
            if s.get('confusions'):
                pair, count = s['confusions'][0]
                wanted, read = (pair.split('→') + [''])[:2]
                tips.append(f'أكثر خطأ لـ{name}: الرقم {wanted} قُرئ {read or "لا شيء"} ({count} مرة). راجع هذه العينات في «البيانات»: تصنيف خاطئ يعلّم النموذج الخطأ.')
    runs = learning.history()
    last_run = next((r for r in reversed(runs) if r.get('state') != 'rollback'), None)
    if last_run and (data['strips'] - (last_run.get('strips') or 0) >= 10 or sum(data['digits'].values()) - (last_run.get('samples') or 0) >= 20):
        tips.append('أُضيفت عينات كثيرة منذ آخر تدريب؛ حان وقت تدريب جديد.')
    if not tips:
        tips.append('لا توجد ملاحظات. استمر في مراجعة البطاقات وتصحيحها؛ كل تصحيح يُحفظ للتدريب.')
    return tips


def overview():
    return {'models': models(), 'data': data_summary(), 'training': learning._training_state(),
            'history': learning.history()[-30:], 'evaluations': evaluations()[-30:], 'advice': advice(),
            'learning_enabled': learning.enabled()}
