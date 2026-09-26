"""Learn from the reviewer: corrected or confirmed handwritten numbers become digit training samples.

Housing cards change (new offices, new clerks, new pens and stamps), so the digit reader must
keep learning from the cards it actually meets. When a reviewer types or confirms a mahalla,
zuqaq, house or form number, that number is read again and each digit's ink is saved under
the digit the reviewer gave — only when the reading has exactly the same digits in the same
places (zeros included), so a mislabelled sample is never produced. Samples stay in
data/digit-samples on this computer.

Retraining (POST /api/learning/train) runs scripts/train_digit_cnn.py in the background at
low priority. The new model is installed only if it keeps its accuracy on the standard
held-out handwriting (MADBase test, clean and under stamps) and reads the reviewer's
kept-aside digits well; the previous model is kept for rollback. See docs/HANDWRITING.md.
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from . import storage

DIGIT_KEYS = ('mahalla_number', 'street', 'house_number', 'form_number')
ROOT = Path(__file__).resolve().parents[1]
MIN_SAMPLES = 20
MIN_STRIPS = 10
_lock = threading.Lock()
_training = None


def samples_dir():
    return storage.DATA / 'digit-samples'


def status_file():
    return storage.DATA / 'learning.json'


def enabled():
    """On unless the reviewer switched it off (saved with the other reading settings)."""
    from .vision_llm import _settings
    return _settings().get('learn_from_corrections', True) is not False


def set_enabled(value):
    from .vision_llm import _settings, settings_file
    settings = _settings() | {'learn_from_corrections': bool(value)}
    storage.atomic_write(settings_file(), json.dumps(settings, ensure_ascii=False, indent=2))
    return status()


def sample_counts():
    root = samples_dir()
    counts = {}
    for label in [str(d) for d in range(1, 10)] + ['noise']:
        folder = root / label
        counts[label] = len(list(folder.glob('*.png'))) if folder.exists() else 0
    return counts


def _training_state():
    try:
        state = json.loads(status_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'state': 'idle'}
    if state.get('state') == 'running' and not (_training and _training.is_alive()):
        state.update(state='interrupted', message='توقف التدريب قبل اكتماله (أُغلق البرنامج). ابدأه مرة أخرى.')
    return state


def status():
    counts = sample_counts()
    return {'enabled': enabled(), 'samples': counts, 'total': sum(counts.values()),
            'number_strips': strip_count(), 'min_samples': MIN_SAMPLES, 'training': _training_state()}


def digits_of(value):
    from .focused_fields import normalize
    text = normalize(str(value or '')).strip()
    return text if re.fullmatch(r'\d{1,7}', text) else None


def labelled_pieces(reading, pieces, value):
    """[(mask, digit)] when the reading has exactly the reviewer's digits in the same places, else [].

    `pieces` are the collected pieces of this reading (hd.collector entries with its call id);
    zeros are dots found by a rule, so they are never samples but must line up.
    """
    if not reading or reading.get('occluded') or not value or len(reading['value']) != len(value):
        return []  # a digit fused with a stamp is not a clean example of that digit
    if any((a == '0') != (b == '0') for a, b in zip(reading['value'], value)):
        return []
    shapes = [p for p in pieces if p['digit'] != 'noise']
    wanted = [c for c in value if c != '0']
    if len(shapes) != len(wanted):
        return []
    return [(p['mask'], digit) for p, digit in zip(shapes, wanted)]


def capture(image, lines, values, tag):
    """Save digit samples for {key: reviewed value}. Returns {key: saved piece count}."""
    from . import handwritten_digits as hd
    from .focused_fields import housing_regions
    from .housing_handwriting import digit_model_readings
    values = {k: digits_of(v) for k, v in values.items() if k in DIGIT_KEYS}
    values = {k: v for k, v in values.items() if v}
    if not values or not hd.available():
        return {}
    with _lock:
        collected = hd.collector = []
        try:
            readings = digit_model_readings(image, housing_regions(image, lines, 'front'), lines)
        finally:
            hd.collector = None
    layout = readings.pop('_layout', None) or {}
    save_strips(readings.pop('_strips', None) or {}, readings, readings.pop('_sequence', None) or {}, values, tag)
    saved = {}
    for key, value in values.items():
        reading = readings.get(key) or (layout.get(key) or {}).get('model')
        if not reading:
            saved[key] = 0
            continue
        pairs = labelled_pieces(reading, [p for p in collected if p.get('call') == reading.get('call')], value)
        for i, (mask, digit) in enumerate(pairs):
            folder = samples_dir() / digit
            folder.mkdir(parents=True, exist_ok=True)
            ink = cv2.copyMakeBorder(mask, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=0)
            # One file per document/field/position: re-saving a correction replaces it.
            cv2.imencode('.png', 255 - ink)[1].tofile(str(folder / f'corr-{tag}-{key}-{i}.png'))
        saved[key] = len(pairs)
    return saved


def strips_dir():
    return storage.DATA / 'number-strips'


def strip_count():
    folder = strips_dir()
    return len(list(folder.glob('*.png'))) if folder.exists() else 0


def save_strips(strips, readings, sequences, values, tag):
    """Save each reviewed number's whole strip, named by the reviewer's value, for the number reader.

    The whole number is the label, so no digit-by-digit alignment is needed (hard cases with
    split, merged or stamped digits are kept too). A strip is saved only when one of the readers
    saw at least half of the reviewer's digits in it: a sign the strip really holds that number
    (a misplaced strip would teach the wrong thing).
    """
    from difflib import SequenceMatcher
    folder = strips_dir()
    for key, value in values.items():
        strip = strips.get(key)
        if strip is None or strip.size == 0:
            continue
        seen = [str((readings.get(key) or {}).get('value') or ''), str((sequences.get(key) or {}).get('value') or '')]
        if max(SequenceMatcher(None, s, value).ratio() for s in seen) < .5:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        # One file per document/field: re-saving a correction replaces it.
        for old in folder.glob(f'*__{key}-{tag}.png'):
            old.unlink()
        cv2.imencode('.png', cv2.cvtColor(strip, cv2.COLOR_RGB2BGR))[1].tofile(str(folder / f'{value}__{key}-{tag}.png'))


def capture_later(bid, did, values):
    """Capture in the background after a reviewer saves a housing card (never blocks the save)."""
    if not enabled() or not values:
        return None

    def run():
        from . import vision
        try:
            b = storage.get_batch(bid)
            d = next(x for x in b['documents'] if x['id'] == did)
            image = vision.read_image(storage.image_path(d['image_id']))
            lines = d.get('ocr', []) if d.get('field_image_id') == d['image_id'] else vision.ocr(image)
            capture(image, lines, values, f'{bid[:8]}-{did[:8]}')
        except Exception:
            import logging
            logging.getLogger('mustamsak').exception('learning capture failed')
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def reviewed_values(doc, previous, verified):
    """Digit fields the reviewer typed (manual) or confirmed (verified) on a housing card front."""
    if doc.get('kind') != 'housing' or doc.get('side') != 'front':
        return {}
    values = {}
    for f in doc.get('fields', []):
        key = f.get('key')
        if key not in DIGIT_KEYS or not digits_of(f.get('value')):
            continue
        typed = f.get('method') == 'manual' and (previous.get(key) or {}).get('value') != f.get('value')
        if typed or verified:
            values[key] = f['value']
    return values


NAME_KEYS = ('name', 'first_name', 'father_name', 'grandfather_name', 'surname', 'mother_name', 'maternal_grandfather')


def names_file():
    return storage.DATA / 'name-words.json'


def known_name_words():
    """Name words the reviewer typed or confirmed on this computer (used by name suggestions)."""
    try:
        return set(json.loads(names_file().read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return set()


def learn_names(doc, previous, verified):
    """Add the words of typed or confirmed names to the local name vocabulary. Returns new words."""
    if not enabled():
        return []
    from .focused_fields import normalize
    words = []
    for f in doc.get('fields', []):
        key, value = f.get('key'), str(f.get('value') or '')
        typed = f.get('method') == 'manual' and (previous.get(key) or {}).get('value') != value
        if key in NAME_KEYS and (typed or verified):
            words += [w for w in re.sub(r'[^ء-ي ]', ' ', value).split() if len(normalize(w)) >= 3 and w not in ('عبد',)]
    if not words:
        return []
    with _lock:
        try:
            counts = json.loads(names_file().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            counts = {}
        new = [w for w in dict.fromkeys(words) if w not in counts]
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        storage.atomic_write(names_file(), json.dumps(counts, ensure_ascii=False, indent=1))
    return new


def _meta(path):
    try:
        with np.load(path, allow_pickle=False) as data:
            return json.loads(str(data['meta']))
    except (OSError, KeyError, ValueError):
        return {}


def gate(current, candidate):
    """(accept, reason): the new model must not get worse on the standard held-out tests."""
    checks = [('madbase_test_accuracy', .005, 'خط اليد العام'), ('madbase_test_accuracy_under_overlap', .01, 'الأرقام تحت الأختام'),
              ('synthetic_accuracy', .01, 'الأرقام المولّدة')]
    for key, tolerance, label in checks:
        old, new = current.get(key), candidate.get(key)
        if old is not None and (new is None or new < old - tolerance):
            return False, f'انخفضت دقة {label} من {old:.3f} إلى {new if new is not None else 0:.3f}'
    own = candidate.get('own_samples_check_accuracy')
    if own is not None and candidate.get('own_samples_check_size', 0) >= 5 and own < .8:
        return False, f'دقة الأرقام المحجوزة من تصحيحاتك {own:.2f} أقل من 0.80'
    return True, 'لم تنخفض الدقة في أي اختبار'


def _write_state(state):
    storage.atomic_write(status_file(), json.dumps(state, ensure_ascii=False, indent=2))


def history_file():
    return storage.DATA / 'training-history.json'


def history():
    try:
        return json.loads(history_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def _add_history(entry):
    runs = (history() + [entry])[-100:]
    storage.atomic_write(history_file(), json.dumps(runs, ensure_ascii=False, indent=1))


def log_file():
    return ROOT / 'output' / 'runtime' / 'training.log'


_process = None
_stop = threading.Event()
NUMBER_CHECKPOINT = 'research/number_reader.pt'


def stop_training():
    """Stop a running training; nothing is installed from a stopped run."""
    if not (_training and _training.is_alive()):
        raise RuntimeError('لا يوجد تدريب يعمل الآن.')
    _stop.set()
    if _process and _process.poll() is None:
        _process.terminate()
    return _training_state()


def start_training(runner=None, models=None, steps=1500, share=.3):
    """Start retraining in the background. Returns the new state, or raises RuntimeError.

    models=None (the one-click retrain): the digit CNN, which needs MIN_SAMPLES corrected digits,
    plus the number reader once there are MIN_STRIPS corrected strips. Explicit models (dashboard):
    'digits' (the digit-by-digit CNN, needs MIN_SAMPLES corrected digits) and/or
    'numbers' (Mustamsak's own whole-number reader, fine-tuned from its checkpoint for `steps`
    steps with `share` of each batch taken from the corrected strips). Each model is installed
    only if it passes its own no-regression gate; the previous one is kept for rollback.
    """
    global _training, _process
    from . import handwritten_digits as hd, number_reader
    if _training and _training.is_alive():
        raise RuntimeError('التدريب يعمل بالفعل.')
    total = sum(sample_counts().values())
    checkpoint = ROOT / NUMBER_CHECKPOINT
    if models is None:
        if total < MIN_SAMPLES:
            raise RuntimeError(f'عدد العينات {total} أقل من {MIN_SAMPLES}؛ صحّح أو اعتمد أرقامًا أكثر أولًا.')
        models = ['digits'] + (['numbers'] if strip_count() >= MIN_STRIPS else [])
    models = [m for m in ('digits', 'numbers') if m in models]
    if 'digits' in models and total < MIN_SAMPLES:
        if models == ['digits'] or runner:
            raise RuntimeError(f'عدد العينات {total} أقل من {MIN_SAMPLES}؛ صحّح أو اعتمد أرقامًا أكثر أولًا.')
        models.remove('digits')
    if 'numbers' in models and not checkpoint.exists() and not runner:
        models.remove('numbers')
    if not models:
        raise RuntimeError('لا يوجد نموذج جاهز للتدريب (تحتاج عينات كافية أو نقطة حفظ قارئ الأرقام الخاص).')
    steps, share = int(min(20000, max(200, steps))), float(min(.8, max(0, share)))
    candidate = ROOT / 'models' / 'eastern_digits_cnn.candidate.npz'
    log = log_file()
    log.parent.mkdir(parents=True, exist_ok=True)
    _stop.clear()
    state = {'state': 'running', 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'samples': total,
             'strips': strip_count(), 'models': models, 'steps': steps, 'share': share,
             'log_offset': log.stat().st_size if log.exists() else 0,
             'message': 'يجري التدريب في الخلفية بأولوية منخفضة.'}
    _write_state(state)
    number_before = number_reader.MODEL_PATH.stat().st_mtime if number_reader.MODEL_PATH.exists() else None

    def call(args, out):
        global _process
        flags = (getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        _process = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=out, stderr=out,
                                    stdin=subprocess.DEVNULL, creationflags=flags)
        return _process.wait()

    def default_runner():
        code = 0
        with log.open('ab') as out:
            if 'digits' in models and not _stop.is_set():
                out.write(b'\n=== phase digits\n'); out.flush()
                code = call([str(ROOT / 'scripts' / 'train_digit_cnn.py'), '--extra', str(samples_dir()),
                             '--extra-repeat', '80', '--out', str(candidate)], out)
            if 'numbers' in models and not _stop.is_set():
                out.write(b'\n=== phase numbers\n'); out.flush()
                args = [str(ROOT / 'scripts' / 'train_number_reader.py'), '--resume', str(checkpoint), '--steps', str(steps),
                        '--lr', '5e-4', '--workers', '4', '--threads', '4', '--share', str(share)]
                if strip_count():
                    args += ['--extra-strips', str(strips_dir())]
                number_code = call(args, out)
                code = code or number_code
        return code

    def run():
        done = dict(state, finished=None)
        results = {}
        try:
            code = (runner or default_runner)()
            number_reader.reset()  # a fine-tuned number reader, if its trainer installed one
            if _stop.is_set():
                done.update(state='stopped', message='أُوقف التدريب بطلبك؛ لم يُثبّت أي نموذج.')
                candidate.unlink(missing_ok=True)
            else:
                if 'numbers' in models:
                    after = number_reader.MODEL_PATH.stat().st_mtime if number_reader.MODEL_PATH.exists() else None
                    installed = after is not None and after != number_before
                    results['numbers'] = {'state': 'installed' if installed else 'kept', 'metrics': model_report()}
                if 'digits' in models:
                    if code != 0 or not candidate.exists():
                        results['digits'] = {'state': 'failed'}
                        done.update(state='failed', message=f'فشل التدريب (رمز {code}). راجع output/runtime/training.log')
                    else:
                        new, old = _meta(candidate), _meta(hd.CNN_PATH)
                        accept, reason = gate(old, new)
                        done['metrics'] = {'new': new, 'old': old}
                        if accept:
                            if hd.CNN_PATH.exists():
                                shutil.copy2(hd.CNN_PATH, hd.CNN_PATH.with_name('eastern_digits_cnn.previous.npz'))
                            shutil.move(str(candidate), hd.CNN_PATH)
                            hd._cnn = None  # the running app reads with the new model from now on
                            done.update(state='installed', message='ثُبّت النموذج الجديد: ' + reason + '. النموذج السابق محفوظ للرجوع إليه.')
                        else:
                            candidate.unlink(missing_ok=True)
                            done.update(state='rejected', message='لم يُثبّت النموذج الجديد: ' + reason + '. بقي النموذج الحالي.')
                        results['digits'] = {'state': 'installed' if accept else 'rejected', 'reason': reason, 'metrics': new}
                elif code != 0:
                    done.update(state='failed', message=f'فشل التدريب (رمز {code}). راجع output/runtime/training.log')
                else:
                    kept = results['numbers']['state'] == 'kept'
                    done.update(state='rejected' if kept else 'installed',
                                message='بقي قارئ الأرقام الخاص كما هو (لم يتحسن).' if kept else 'ثُبّت قارئ الأرقام الخاص الجديد؛ السابق محفوظ للرجوع إليه.')
        except Exception as e:
            done.update(state='failed', message='فشل التدريب: ' + str(e)[:200])
        done['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
        done['results'] = results
        _write_state(done)
        _add_history({k: done.get(k) for k in ('started', 'finished', 'state', 'message', 'models', 'steps', 'share',
                                               'samples', 'strips', 'results')})

    _training = threading.Thread(target=run, daemon=True)
    _training.start()
    return state


def model_report():
    """Metrics saved inside the installed number reader (scripts/train_number_reader.py)."""
    from . import number_reader
    try:
        with np.load(number_reader.MODEL_PATH, allow_pickle=False) as data:
            return json.loads(str(data['report'])) if 'report' in data.files else {}
    except (OSError, ValueError):
        return {}
