"""Start the local server, wait for readiness, then open the browser."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from .runtime import ROOT, INSTANCE, revision


def health(url):
    try:
        # Ignore system HTTP proxies for the loopback readiness check.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + '/api/health', timeout=1) as response:
            result = json.load(response)
        return result if result.get('app') == 'mustamsak' else None
    except (OSError, ValueError):
        return None


def occupied(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', port)) == 0


@contextmanager
def launch_lock(path, timeout):
    # Serializes double clicks without leaving a stale lock after a crash.
    import msvcrt
    with path.open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Another launch is still starting. Try again shortly.')
                time.sleep(.2)
        try:
            yield
        finally:
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def ensure_server(port=8765, timeout=90):
    url = f'http://127.0.0.1:{port}'
    logs = ROOT / 'output' / 'runtime'
    logs.mkdir(parents=True, exist_ok=True)
    record = logs / f'server-{port}.json'
    log_path = logs / f'server-{port}.log'
    expected = revision()
    current = lambda r: r.get('revision') == expected
    with launch_lock(logs / f'launch-{port}.lock', timeout):
        running = health(url)
        if running:
            if running.get('instance') != INSTANCE:
                raise RuntimeError(f'Port {port} belongs to another installation. Close it first.')
            if current(running):
                return url, 'reused'
            if running.get('busy'):
                raise RuntimeError('An older server is processing documents. Wait for it to finish before restarting.')
            # Only stop a server recorded by this launcher and authenticated by
            # its installation ID and live PID. Never stop an arbitrary listener.
            try:
                saved = json.loads(record.read_text(encoding='utf8'))
            except (OSError, ValueError):
                saved = {}
            if saved.get('instance') != INSTANCE or saved.get('pid') != running.get('pid'):
                raise RuntimeError('An older server is running outside this launcher. Close its server window, then try again.')
            subprocess.run(['taskkill', '/PID', str(running['pid']), '/F'], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 10
            while occupied(port) and time.monotonic() < deadline:
                time.sleep(.15)
        if occupied(port):
            raise RuntimeError(f'Port {port} is already in use and does not answer as this app. No process was stopped.')
        with log_path.open('ab', buffering=0) as log:
            log.write(f'\n--- Starting {time.strftime("%Y-%m-%d %H:%M:%S")} ---\n'.encode())
            env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1')
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                        '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT,
                                       env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            running = health(url)
            if running and running.get('instance') == INSTANCE and current(running):
                record.write_text(json.dumps({'instance': INSTANCE, 'pid': running['pid']}), encoding='utf8')
                return url, 'started'
            if process.poll() is not None:
                raise RuntimeError(f'Server exited ({process.returncode}). See: {log_path}')
            time.sleep(.25)
        raise RuntimeError(f'Server did not become ready within {timeout} seconds. See: {log_path}')


def stop_server(port=8765, force=False, timeout=15):
    """Stop this installation's server: politely through /api/shutdown, else (only a server this
    launcher recorded, with the same installation ID and PID) by ending its process tree."""
    import urllib.error
    import urllib.request
    url = f'http://127.0.0.1:{port}'
    running = health(url)
    if not running:
        return 'not-running'
    if running.get('instance') != INSTANCE:
        raise RuntimeError(f'Port {port} belongs to another installation. Nothing was stopped.')
    request = urllib.request.Request(url + '/api/shutdown', data=json.dumps({'force': force}).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except urllib.error.HTTPError as error:
        if error.code == 409 and not force:
            detail = json.loads(error.read().decode('utf-8') or '{}').get('detail', '')
            raise RuntimeError(f'The app is busy ({detail}). Wait, or run: "Stop KYC Agent.cmd" -Force')
    except OSError:
        pass
    deadline = time.monotonic() + timeout
    while occupied(port) and time.monotonic() < deadline:
        time.sleep(.2)
    if not occupied(port):
        return 'stopped'
    try:
        saved = json.loads((ROOT / 'output' / 'runtime' / f'server-{port}.json').read_text(encoding='utf8'))
    except (OSError, ValueError):
        saved = {}
    if saved.get('instance') != INSTANCE or saved.get('pid') != running.get('pid'):
        raise RuntimeError('The server did not stop and was not started by this launcher. Nothing was killed.')
    subprocess.run(['taskkill', '/PID', str(running['pid']), '/T', '/F'], check=False, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    return 'stopped'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true', help='stop the running app')
    parser.add_argument('--force', action='store_true', help='with --stop: stop even while busy')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, choices=range(1024, 65536), metavar='PORT', default=8765)
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    if args.stop:
        try:
            result = stop_server(args.port, args.force)
            print('Mustamsak is not running.' if result == 'not-running' else 'Mustamsak stopped.', flush=True)
            return 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f'Could not stop Mustamsak: {error}', file=sys.stderr)
            return 1
    print('Starting Mustamsak. Waiting for the local server...', flush=True)
    try:
        url, action = ensure_server(args.port, args.timeout)
        print(json.dumps({'ready': True, 'action': action, 'url': url}), flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Could not start Mustamsak: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
