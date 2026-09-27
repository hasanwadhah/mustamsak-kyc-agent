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


def git_version():
    """Which GitHub commit this folder runs, compared with the last fetch of GitHub (start.ps1 fetches).

    Returns None when git or the repository is missing (e.g. a downloaded ZIP). Never touches the network.
    """
    import subprocess

    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        head = git('log', '-1', '--format=%h|%cs')
        if not head:
            return None
        commit, date = head.split('|')
        counts = git('rev-list', '--left-right', '--count', 'HEAD...origin/main')
        ahead, behind = (int(n) for n in counts.split()) if counts else (0, 0)
        return {'commit': commit, 'date': date, 'behind': behind, 'ahead': ahead,
                'changed': bool(git('status', '--porcelain', '--untracked-files=no'))}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


STARTED_REVISION = revision()
STARTED_EDIT = last_edit()
