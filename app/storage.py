import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('MUSTAMSAK_DATA',ROOT/'data'))
LOCK=threading.RLock()
for name in ['images','batches','exports']:(DATA/name).mkdir(parents=True,exist_ok=True)

def uid():return uuid.uuid4().hex

def valid_id(value):
    if not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('معرّف غير صالح.')
    return value

def image_path(value):return DATA/'images'/f'{valid_id(value)}.png'

def atomic_write(path,text,attempts=40):
    """Write via a temp file, retrying the swap.

    On Windows a rename onto a file fails with PermissionError while any other
    handle (a reader thread, OneDrive, antivirus) has the target open.
    """
    temp=path.with_suffix('.tmp')
    temp.write_text(text,encoding='utf-8')
    for attempt in range(attempts):
        try:
            temp.replace(path);return
        except PermissionError:
            if attempt==attempts-1:raise
            time.sleep(min(.25,.01*(attempt+1)))

def save_batch(batch):
    with LOCK:
        atomic_write(DATA/'batches'/f'{valid_id(batch["id"])}.json',json.dumps(batch,ensure_ascii=False,indent=2))

def get_batch(value):
    with LOCK:return json.loads((DATA/'batches'/f'{valid_id(value)}.json').read_text(encoding='utf-8'))

def list_batches():
    result=[]
    # Read under the lock so this never holds a file open while a writer swaps it.
    with LOCK:
        for path in (DATA/'batches').glob('*.json'):
            try:
                b=json.loads(path.read_text(encoding='utf-8'))
                result.append({k:b[k] for k in ['id','name','created','status','progress','message'] }|{'count':len(b['documents'])})
            except (OSError,ValueError,KeyError):continue
    return sorted(result,key=lambda b:b['created'],reverse=True)
