"""Optional local vision-language reader (Ollama + Qwen2.5-VL) for doubtful handwriting.

A second opinion that "reads like a person": it is told what the field is (e.g. the
house number after the printed د, in Arabic-Indic digits, with a stamp over it) and may
answer "unreadable" instead of guessing. It is consulted only for fields that are
approximate, conflicting or read by a single reader, and its answer is added as a
suggestion only. It runs on this computer only (Ollama at 127.0.0.1); if Ollama is
not running or the reader is not enabled, nothing changes.

Setup (once): install Ollama (https://ollama.com), then `ollama pull <model>`.
OFF by default. Switched on/off from the reading-settings dialog (saved in
data/settings.json); MUSTAMSAK_LOCAL_VLM=1 is only the default when nothing is saved.
Model: MUSTAMSAK_VLM_MODEL.

Measured 2026-09-23 on 5 real housing cards with qwen2.5vl:7b: 0/15 handwritten address
numbers right and invented names (a different three-part name for the one written). General VLMs of this size do not read Iraqi handwritten
Arabic-Indic digits, so this reader only ever ADDS a suggestion; it never changes a value.
Re-measure any new model with the same cards before enabling it.
"""
import base64
import json
import os
import re

import cv2
import numpy as np

HOST = 'http://127.0.0.1:11434'
MODEL = os.environ.get('MUSTAMSAK_VLM_MODEL', 'qwen2.5vl:7b')
_available = None

ROLE_TEXT = {
    'mahalla_number': ('the mahalla (neighbourhood) number, written after the printed letter م', 'رقم المحلة'),
    'street': ('the street (zuqaq) number, written after the printed letter ز', 'رقم الزقاق'),
    'house_number': ('the house number, written after the printed letter د', 'رقم الدار'),
    'form_number': ('the form number (رقم الاستمارة)', 'رقم الاستمارة'),
}


def settings_file():
    from .storage import DATA
    return DATA / 'settings.json'


def _settings():
    try:
        return json.loads(settings_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def enabled():
    """The user's on/off choice (saved from the settings dialog); else MUSTAMSAK_LOCAL_VLM; else off."""
    saved = _settings().get('local_vlm')
    if isinstance(saved, bool):
        return saved
    return os.environ.get('MUSTAMSAK_LOCAL_VLM', '0') == '1'


def ollama_executable():
    from pathlib import Path
    return Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'


def _ollama_version():
    try:
        import httpx
        with httpx.Client(timeout=1.5, trust_env=False) as client:
            return client.get(HOST + '/api/version').json().get('version')
    except Exception:
        return None


def ensure_ollama(wait=15):
    """Start the local Ollama server if it is installed and not running. Returns True when reachable."""
    import subprocess
    import time
    if _ollama_version():
        return True
    exe = ollama_executable()
    if not exe.exists():
        return False
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.Popen([str(exe), 'serve'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if _ollama_version():
            return True
        time.sleep(.5)
    return False


def set_enabled(value):
    """Save the user's choice, start Ollama when switching on, and re-check availability."""
    global _available
    from .storage import atomic_write
    settings = _settings() | {'local_vlm': bool(value)}
    atomic_write(settings_file(), json.dumps(settings, ensure_ascii=False, indent=2))
    _available = None
    if value:
        ensure_ollama()
    return status()


def status():
    global _available
    _available = None  # fresh check for the settings dialog
    running = bool(_ollama_version())
    return {'enabled': enabled(), 'installed': ollama_executable().exists() or running, 'running': running,
            'ready': available(), 'model': MODEL}


_checked = 0.0


def available():
    """True when a local Ollama server with the model is reachable.

    A positive answer is kept; a negative one is re-checked after a minute, so the
    app notices Ollama being started or the model finishing its download.
    """
    global _available, _checked
    import time
    if _available is None or (_available is False and time.monotonic() - _checked > 60):
        _checked = time.monotonic()
        _available = False
        if enabled():
            names = _model_names()
            _available = MODEL in names or any(n.split(':')[0] == MODEL.split(':')[0] for n in names)
    return _available


def _model_names():
    """Models installed in the local Ollama (empty when it is not running)."""
    try:
        import httpx
        with httpx.Client(timeout=1.5, trust_env=False) as client:
            return {m.get('name', '') for m in client.get(HOST + '/api/tags').json().get('models', [])}
    except Exception:
        return set()


def _png(rgb, min_height=160):
    h, w = rgb.shape[:2]
    scale = max(1.0, min_height / max(1, h))
    if scale > 1:
        rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    ok, data = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return base64.b64encode(data.tobytes()).decode()


def _ask(prompt, rgb, schema, timeout=120):
    import httpx
    payload = {'model': MODEL, 'prompt': prompt, 'images': [_png(rgb)], 'stream': False, 'format': schema,
               'options': {'temperature': 0, 'num_predict': 120}, 'keep_alive': '10m'}
    with httpx.Client(timeout=timeout, trust_env=False) as client:  # local only; never a proxy
        response = client.post(HOST + '/api/generate', json=payload)
    response.raise_for_status()
    return json.loads(response.json().get('response') or '{}')


def crop_around(image, box, margin=.7):
    """The field with some context around it (marker letter, dotted line, stamp)."""
    b = np.asarray(box, float)
    h, w = image.shape[:2]
    x1, y1 = b.min(0)
    x2, y2 = b.max(0)
    mh = (y2 - y1) * margin
    return image[max(0, int(y1 - mh)):min(h, int(y2 + mh)), max(0, int(x1 - 1.2 * mh)):min(w, int(x2 + 1.2 * mh))]


def read_number(image, box, role):
    """Digits of one handwritten number, or None when the model cannot read it."""
    if not available() or role not in ROLE_TEXT:
        return None
    crop = crop_around(image, box)
    if crop.size == 0:
        return None
    what, arabic = ROLE_TEXT[role]
    prompt = (f'This image is a crop of an Iraqi housing card (بطاقة السكن). It shows {what} ({arabic}). '
              'The number is handwritten in Arabic-Indic digits ٠١٢٣٤٥٦٧٨٩ (٠ is written as a dot, ٢ often looks like "c", '
              '٤ like "ع"). A stamp, signature or printed letters may overlap it: ignore them and read only the '
              'handwritten number, left to right. Reply with the digits converted to 0-9. '
              'If any digit is not clearly visible, set readable to false. Never guess or complete a digit.')
    schema = {'type': 'object', 'properties': {'digits': {'type': 'string'}, 'readable': {'type': 'boolean'}},
              'required': ['digits', 'readable']}
    try:
        answer = _ask(prompt, crop, schema)
    except Exception:
        return None
    digits = re.sub(r'\D', '', str(answer.get('digits', '')).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')))
    if not answer.get('readable') or not 1 <= len(digits) <= 6:
        return None
    return digits


def read_text(image, box, what):
    """Handwritten Arabic text (a name or an office), as a suggestion only."""
    if not available():
        return None
    crop = crop_around(image, box, margin=.3)
    if crop.size == 0:
        return None
    prompt = (f'This crop of an Iraqi housing card shows {what}, handwritten in Arabic. Transcribe exactly the '
              'handwritten Arabic words you can see, ignoring stamps and printed labels. Do not add, complete or '
              'correct names. If it is not clearly readable, set readable to false.')
    schema = {'type': 'object', 'properties': {'text': {'type': 'string'}, 'readable': {'type': 'boolean'}},
              'required': ['text', 'readable']}
    try:
        answer = _ask(prompt, crop, schema)
    except Exception:
        return None
    text = ' '.join(re.sub(r'[^ء-ي\s]', ' ', str(answer.get('text', ''))).split())
    return text if answer.get('readable') and len(text) >= 3 else None


def review_housing(image, fields):
    """Ask the local model about doubtful housing fields and add its vote/suggestion."""
    if not available():
        return fields
    for role in ('mahalla_number', 'street', 'house_number', 'form_number'):
        f = fields.get(role)
        if not f or not f.get('box') or f.get('verified') or f.get('method') == 'manual':
            continue
        doubtful = f.get('status') in ('approximate', 'conflict', 'unreadable', 'missing') or f.get('single_reader')
        if not doubtful or f.get('agreement'):
            continue
        answer = read_number(image, f['box'], role)
        if not answer or answer == str(f.get('value') or ''):
            continue
        # Only ever a suggestion: this reader has not earned the right to change a value.
        candidates = f.setdefault('candidates', [])
        if not any(c.get('value') == answer for c in candidates):
            candidates.append({'value': answer, 'confidence': None, 'engine': 'local_vision_llm',
                               'note': 'قراءة القارئ الذكي المحلي؛ اقتراح يحتاج مقارنة بالصورة.'})
    for role, what in (('name', 'the name of the head of household (اسم رب الأسرة)'),
                       ('information_office', 'the information office name (مكتب المعلومات)')):
        f = fields.get(role)
        if not f or not f.get('box') or f.get('verified') or f.get('method') == 'manual' or f.get('status') == 'read':
            continue
        text = read_text(image, f['box'], what)
        if text and not any(c.get('value') == text for c in f.get('candidates', [])):
            f.setdefault('candidates', []).insert(0, {'value': text, 'confidence': None, 'engine': 'local_vision_llm',
                                                      'note': 'قراءة القارئ الذكي المحلي؛ اقتراح يحتاج مقارنة بالصورة.'})
    return fields
