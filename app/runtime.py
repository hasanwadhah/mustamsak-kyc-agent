"""Identify this installation and the source revision served by a process."""
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()[:20]


def revision():
    digest = hashlib.sha256()
    for path in sorted([*ROOT.glob('app/*.py'), *ROOT.glob('static/*')]):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def last_edit():
    """Time of the newest program file (code, pages, digit model) as 'YYYY-MM-DD HH:MM'."""
    import time
    files = [*ROOT.glob('app/*.py'), *ROOT.glob('static/*'), ROOT / 'models' / 'eastern_digits_cnn.npz']
    newest = max((p.stat().st_mtime for p in files if p.is_file()), default=0)
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(newest))


STARTED_REVISION = revision()
STARTED_EDIT = last_edit()
