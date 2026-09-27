from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
import threading
import json
import cv2
import numpy as np
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import FileResponse,Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import storage,vision,pipeline,export,arabic_ocr
from .print_layout import PrintOptions, grid_spec, manual_sheets
from . import runtime
from .focused_fields import VERSION as EXTRACTION_VERSION

ROOT=Path(__file__).resolve().parents[1]
pool=ThreadPoolExecutor(max_workers=1)
queue_lock=threading.Lock();pending=set()
active_operations=0

@asynccontextmanager
async def lifespan(app):
    for entry in storage.list_batches():
        if entry['status'] in ['queued','processing']:
            b=storage.get_batch(entry['id']);b['status']='interrupted';b['message']='توقفت الجلسة السابقة؛ النتائج المكتملة محفوظة. أعد رفع الصفحات المتبقية.';storage.save_batch(b)
    yield

app=FastAPI(title='Mustamsak | مستمسك',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_only(request:Request,call_next):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        return JSONResponse({'detail':'طلب من مصدر غير مسموح.'},403)
    if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'طلب من موقع خارجي غير مسموح.'},403)
    global active_operations
    writing=request.method in ('POST','PUT','PATCH','DELETE')
    if writing:active_operations+=1
    try:response=await call_next(request)
    finally:
        if writing:active_operations-=1
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; frame-ancestors 'self'"
    return response

def batch_or_404(bid):
    try:return storage.get_batch(bid)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'المجموعة غير موجودة.')

def editable(b):
    if b['status'] in ['queued','processing']:raise HTTPException(409,'انتظر اكتمال المعالجة قبل التعديل.')

def doc_or_404(b,did):
    d=next((d for d in b['documents'] if d['id']==did),None)
    if d is None:raise HTTPException(404,'المستمسك غير موجود.')
    return d

@app.get('/')
def index():return FileResponse(ROOT/'static'/'agent.html')  # the KYC agent screen; the full workspace is /workspace

@app.get('/api/health')
def health():
    import os
    from .runtime import INSTANCE, STARTED_REVISION, STARTED_EDIT, revision
    from .vision_llm import enabled
    from .focused_fields import VERSION
    return {'app':'mustamsak','instance':INSTANCE,'revision':STARTED_REVISION,
            'pid':os.getpid(),'busy':bool(pending) or active_operations>0,'local_vlm':enabled(),
            # Shown in the sidebar, so the reviewer can see which update is running.
            'reading_version':VERSION,'updated':STARTED_EDIT,'current':revision()==STARTED_REVISION}


class Shutdown(BaseModel):
    force:bool=False

@app.post('/api/shutdown')
def shutdown(body:Shutdown):
    """Stop the app (sidebar button or "Stop KYC Agent.cmd"). The server runs in the background without a
    window, so closing the browser never stops it. Refused while documents are being processed or
    a training runs, unless forced; a forced stop also stops the training (nothing is installed)."""
    import os
    from . import learning
    training=bool(learning._training and learning._training.is_alive())
    processing=bool(pending) or active_operations>1  # this request itself counts as one
    if (processing or training) and not body.force:
        raise HTTPException(409,'يعمل البرنامج الآن على '+('تدريب نموذج' if training else 'معالجة مستمسكات')+'. انتظر حتى ينتهي، أو أوقفه على أي حال.')
    if training:
        try:learning.stop_training()
        except RuntimeError:pass
    # Exit after this response has been sent. Every save in the app is atomic (write then rename).
    threading.Timer(.6,lambda:os._exit(0)).start()
    return {'stopping':True}

@app.get('/api/status')
def status():
    return {'ocr_ready':arabic_ocr.available() or vision.ocr_available(),'engine':'PP-OCRv5 Arabic + English · قراءة الحقول محليًا' if arabic_ocr.available() else 'EasyOCR Arabic + English · CPU','types':vision.TYPES,'local_only':True,'extraction_version':EXTRACTION_VERSION,'references':len(list((ROOT/'models'/'references').glob('*.npz'))),'local_vlm':local_vlm()}

def local_vlm():
    from . import vision_llm
    return vision_llm.available()

@app.get('/api/batches')
def batches():return storage.list_batches()

@app.get('/api/batches/{bid}')
def batch(bid:str):return batch_or_404(bid)

def deletion_plan(b, after=None):
    from .deletion import cleanup_plan
    try:return cleanup_plan(b, after)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(409,'تعذر التحقق من الصور المشتركة بين الدفعات. لم يتم الحذف؛ أعد المحاولة بعد التحقق من ملفات الحفظ.')


def deletion_result(paths):
    from .deletion import cleanup_images
    return 'حُذفت السجلات، لكن تعذر حذف بعض الصور من القرص.' if cleanup_images(paths) else None


@app.delete('/api/batches/{bid}')
def delete_batch(bid:str):
    with storage.LOCK:
        b=batch_or_404(bid);editable(b)
        path=storage.DATA/'batches'/f'{storage.valid_id(bid)}.json'
        if path.resolve().parent!=(storage.DATA/'batches').resolve():
            raise HTTPException(409,'مسار الدفعة غير صالح للحذف.')
        paths=deletion_plan(b)
        path.unlink()
        return {'deleted_id':bid,'cleanup_warning':deletion_result(paths)}


class DeleteDocuments(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=800)


@app.delete('/api/batches/{bid}/documents')
def delete_documents(bid:str,body:DeleteDocuments):
    from .deletion import without_documents
    with storage.LOCK:
        before=batch_or_404(bid);editable(before)
        ids=set(body.ids)
        for did in ids:doc_or_404(before,did)
        after=without_documents(before,ids)
        paths=deletion_plan(before,after)
        storage.save_batch(after)
        return {'batch':after,'deleted_count':len(ids),'cleanup_warning':deletion_result(paths)}


@app.post('/api/batches',status_code=202)
async def upload(files:list[UploadFile]=File(...)):
    if not 1<=len(files)<=20:raise HTTPException(400,'ارفع من 1 إلى 20 ملفًا في الدفعة.')
    with queue_lock:
        if len(pending)>=3:raise HTTPException(429,'هناك دفعات قيد المعالجة؛ انتظر اكتمال إحداها.')
        token=storage.uid();pending.add(token)
    try:
        items=[];total=0
        for f in files:
            content=bytearray()
            while chunk:=await f.read(1024*1024):
                total+=len(chunk);content.extend(chunk)
                if len(content)>40*1024*1024 or total>100*1024*1024:raise HTTPException(413,'الحد 40 MB للملف و100 MB للدفعة.')
            if not content:raise HTTPException(400,'أحد الملفات فارغ.')
            name=Path((f.filename or 'document').replace('\\','/')).name[:160]
            items.append((name,bytes(content)))
            await f.close()
        return start_batch(items,token)
    except Exception:
        with queue_lock:pending.discard(token)
        raise

def start_batch(items,token,name=None):
    """Queue [(file name, bytes)] for reading; returns a snapshot of the new batch. `token` is the
    caller's place in `pending` (released when the batch is done)."""
    b=pipeline.new_batch(name or (items[0][0] if len(items)==1 else f'دفعة من {len(items)} ملفات'))
    storage.save_batch(b)
    def work():
        try:pipeline.process_batch(b,items)
        except Exception:
            # Futures swallow exceptions; keep a trace in the server log.
            import traceback;traceback.print_exc()
        finally:
            with queue_lock:pending.discard(token)
    snapshot=json.loads(json.dumps(b))
    pool.submit(work)
    return snapshot

@app.get('/api/images/{iid}')
def image(iid:str):
    try:path=storage.image_path(iid)
    except ValueError:raise HTTPException(404)
    if not path.exists():raise HTTPException(404)
    return FileResponse(path,media_type='image/png')

class DocumentUpdate(BaseModel):
    kind:str
    side:Literal['front','back','page','unknown']
    group:str=Field(min_length=1,max_length=100)
    reviewed:bool=False
    fields:list[dict]=Field(default_factory=list,max_length=50)
    @field_validator('kind')
    @classmethod
    def kind_valid(cls,v):
        if v not in vision.TYPES:raise ValueError('نوع غير صالح')
        return v

@app.patch('/api/batches/{bid}/documents/{did}')
def update_document(bid:str,did:str,body:DocumentUpdate):
    with storage.LOCK:
        b=batch_or_404(bid);editable(b);d=doc_or_404(b,did)
        previous={f['key']:f for f in d['fields']}
        previous_kind=d['kind'];previous_side=d['side']
        if body.group!=d.get('group'):
            d['group_method']='manual';d.pop('pairing',None);d['group_reason']='مجموعة اختارها المستخدم.'
        d.update(body.model_dump(exclude={'fields'}))
        updated=[]
        for f in body.fields:
            clean={'key':str(f.get('key','manual'))[:100],'label':str(f.get('label','حقل'))[:100],'value':str(f.get('value',''))[:2000]}
            old=previous.get(clean['key'],{})
            unchanged=old.get('value')==clean['value'] and old.get('label')==clean['label']
            meta=dict(old) if unchanged else {'confidence':None,'status':'manual','method':'manual','box':old.get('box')}
            updated.append(dict(meta,**clean,verified=body.reviewed))
        number_before=previous.get('document_number',{}).get('value','')
        number_after=next((f.get('value','') for f in updated if f.get('key')=='document_number'),'')
        if number_before!=number_after or previous_kind!=d['kind'] or previous_side!=d['side']:
            from .grouping import invalidate_pairing
            invalidate_pairing(b['documents'],d['id'])
        d['fields']=updated
        storage.save_batch(b)
    # Corrected/confirmed handwritten numbers teach the digit reader (background, local only).
    from . import learning
    learning.capture_later(bid,did,learning.reviewed_values(d,previous,body.reviewed))
    learning.learn_names(d,previous,body.reviewed)
    return d

class Edit(BaseModel):
    operation:Literal['rotate','enhance','grayscale','reset','crop']
    points:list[list[float]]|None=None

def validated_points(points,image):
    p=np.array(points,dtype=float)
    h,w=image.shape[:2]
    if p.shape!=(4,2) or not np.isfinite(p).all() or (p<0).any() or (p[:,0]>w-1).any() or (p[:,1]>h-1).any():raise HTTPException(422,'زوايا القص خارج حدود الصورة.')
    return p

@app.post('/api/batches/{bid}/documents/{did}/edit')
def edit_image(bid:str,did:str,body:Edit):
    with storage.LOCK:
        b=batch_or_404(bid);editable(b);d=doc_or_404(b,did)
        image=vision.read_image(storage.image_path(d['original_id'] if body.operation=='reset' else d['image_id']))
        if body.operation=='rotate':image=cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE)
        elif body.operation=='enhance':
            lab=cv2.cvtColor(image,cv2.COLOR_RGB2LAB);lab[:,:,0]=cv2.createCLAHE(clipLimit=1.5,tileGridSize=(8,8)).apply(lab[:,:,0]);image=cv2.cvtColor(lab,cv2.COLOR_LAB2RGB)
        elif body.operation=='grayscale':image=cv2.cvtColor(cv2.cvtColor(image,cv2.COLOR_RGB2GRAY),cv2.COLOR_GRAY2RGB)
        elif body.operation=='crop':
            if body.points is None:raise HTTPException(422,'حدد زوايا القص.')
            points=validated_points(body.points,image)
            try:image=vision.warp(image,points)
            except ValueError as e:raise HTTPException(422,str(e))
        d.setdefault('image_history',[]).append(d['image_id'])
        d['image_id']=storage.uid();vision.save_image(storage.image_path(d['image_id']),image)
        d['width']=image.shape[1];d['height']=image.shape[0];d['reviewed']=False
        from . import capture
        # Source-frame checks (cut-off edges) no longer apply to an edited crop.
        d['capture']=capture.assess(image)
        d['notices']=[i['message'] for i in d['capture'] if i['severity'] in ('retake','warn')]+['تغيّرت الصورة؛ راجع البيانات أو أعد القراءة.']
        storage.save_batch(b);return d

@app.post('/api/batches/{bid}/documents/{did}/ocr')
def reread(bid:str,did:str):
    b=batch_or_404(bid);editable(b);d=doc_or_404(b,did);image_id=d['image_id']
    before=json.dumps([d['kind'],d['side'],d['fields']],sort_keys=True,ensure_ascii=False)
    try:
        image=vision.read_image(storage.image_path(image_id))
        lines=vision.ocr(image)
        fields=vision.extract_fields(lines,d['kind'],image,d['side'])
    except Exception as e:raise HTTPException(503,str(e)[:300])
    with storage.LOCK:
        b=batch_or_404(bid);d=doc_or_404(b,did)
        if d['image_id']!=image_id or json.dumps([d['kind'],d['side'],d['fields']],sort_keys=True,ensure_ascii=False)!=before:raise HTTPException(409,'تغيّرت الصورة أو البيانات أثناء القراءة؛ أعد المحاولة لحماية تعديلاتك.')
        if next((f.get('value') for f in d['fields'] if f.get('key')=='document_number'),None)!=next((f.get('value') for f in fields if f.get('key')=='document_number'),None):
            from .grouping import invalidate_pairing
            invalidate_pairing(b['documents'],d['id'])
        d['ocr']=lines;d['fields']=fields;d['field_image_id']=image_id;d['extraction_version']=EXTRACTION_VERSION;d['reviewed']=False
        if d['kind']=='national_id':
            from .grouping import regroup_national
            regroup_national(b['documents'])
        from .paired_fields import reconcile
        reconcile(b['documents'])
        storage.save_batch(b);return d

@app.post('/api/batches/{bid}/refine-fields')
def refine_fields(bid:str):
    from . import focused_fields
    with storage.LOCK:
        b=batch_or_404(bid);editable(b)
        before=json.dumps(b,sort_keys=True,ensure_ascii=False)
    if not arabic_ocr.available():raise HTTPException(503,'محرك القراءة المحلي غير جاهز.')
    changed=0;skipped=0
    try:
        for d in b['documents']:
            if d['kind'] not in ['national_id','housing']:continue
            if d.get('reviewed'):skipped+=1;continue
            image=vision.read_image(storage.image_path(d['image_id']))
            lines=d.get('ocr',[]) if d.get('field_image_id')==d['image_id'] else vision.ocr(image)
            updates=focused_fields.extract(image,lines,d['kind'],d['side'])
            merged=focused_fields.merge_refined(d['fields'],updates,d['image_id'])
            if d['kind']=='national_id' and d['side']=='back':
                merged=[f for f in merged if f.get('key')!='sex' or f.get('verified') or f.get('method')=='manual' or f.get('status')=='manual']
            if merged!=d['fields']:
                changed+=1;d['fields']=merged;d['focused_extraction_version']=focused_fields.VERSION
    except Exception as e:raise HTTPException(503,'تعذر إكمال القراءة المحلية: '+str(e)[:200])
    with storage.LOCK:
        current=batch_or_404(bid);editable(current)
        if json.dumps(current,sort_keys=True,ensure_ascii=False)!=before:
            raise HTTPException(409,'تغيّرت الدفعة أثناء التحسين؛ أعد المحاولة لحماية تعديلاتك.')
        storage.save_batch(b)
    return {'batch':b,'updated_documents':changed,'skipped_reviewed':skipped}


@app.post('/api/batches/{bid}/pair-national')
def pair_national(bid:str):
    from . import national_serial,grouping
    b=batch_or_404(bid);editable(b)
    before=json.dumps(b,sort_keys=True,ensure_ascii=False)
    for d in b['documents']:
        if d['kind']=='national_id' and d['side'] in ['front','back'] and not d.get('reviewed'):
            image=vision.read_image(storage.image_path(d['image_id']))
            national_serial.refresh_document(d,image)
    grouping.regroup_national(b['documents'])
    from .paired_fields import reconcile
    reconcile(b['documents'])
    with storage.LOCK:
        current=batch_or_404(bid);editable(current)
        if json.dumps(current,sort_keys=True,ensure_ascii=False)!=before:
            raise HTTPException(409,'تغيّرت الدفعة أثناء مطابقة الأوجه؛ أعد المحاولة لحماية تعديلاتك.')
        storage.save_batch(b)
    return b

class Region(BaseModel):
    source_id:str
    points:list[list[float]]

@app.post('/api/batches/{bid}/regions')
def add_region(bid:str,body:Region):
    b=batch_or_404(bid);editable(b)
    source=next((s for s in b['sources'] if s['id']==body.source_id),None)
    if not source:raise HTTPException(404,'الصورة الأصلية غير موجودة.')
    image=vision.read_image(storage.image_path(source['id']));validated_points(body.points,image)
    try:d=pipeline.make_document(image,source,{'points':body.points,'method':'manual','score':1},len(b['documents']))
    except ValueError as e:raise HTTPException(422,str(e))
    with storage.LOCK:
        b=batch_or_404(bid);d['group']=f'مجموعة يدوية {len(b["documents"])+1}';b['documents'].append(d);storage.save_batch(b)
    return d

@app.get('/api/print-layouts')
def print_layouts():
    return {key: grid_spec(key) for key in ('grid4', 'grid6')}

class ExportRequest(PrintOptions):
    ids:list[str]=Field(min_length=1,max_length=800)
    format:Literal['pdf','zip','json','csv']='pdf'
    allow_unreviewed:bool=False

@app.post('/api/batches/{bid}/export')
def export_documents(bid:str,body:ExportRequest):
    b=batch_or_404(bid);editable(b)
    ids=list(dict.fromkeys(body.ids));documents=[doc_or_404(b,did) for did in ids]
    try:sheets=manual_sheets(body.pages,body.layout,{d['id']:d for d in documents})
    except ValueError as error:raise HTTPException(422,str(error))
    if not body.allow_unreviewed and any(not d['reviewed'] for d in documents):raise HTTPException(409,'بعض المستمسكات لم تُراجع. راجعها أو اختر تصدير المسودة صراحةً.')
    if body.format=='pdf':data=export.export_pdf(documents,body.layout,body.size,sheets);mime='application/pdf'
    elif body.format=='zip':data=export.export_zip(documents,body.layout,body.size,sheets);mime='application/zip'
    elif body.format=='csv':data=export.export_csv(documents);mime='text/csv; charset=utf-8'
    else:data=export.export_json(documents);mime='application/json'
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="mustamsak.{body.format}"'})

import httpx
from . import cloud
from .cloud import CloudRequest,KeyCheck,read_cloud

class CloudSwitch(BaseModel):
    enabled:bool

@app.get('/api/cloud')
def cloud_status():return cloud.status()

@app.put('/api/cloud')
def cloud_switch(body:CloudSwitch):
    """Switch the optional Gemini cloud reader on/off (saved). Off: no image can be sent."""
    return cloud.set_enabled(body.enabled)

def cloud_failure(e):
    """Arabic message plus Google's own short reason, so a failed reading can be diagnosed."""
    detail=getattr(e,'detail','')
    return HTTPException(400,f'{e} — تفاصيل Google: {detail}' if detail else str(e))

@app.post('/api/cloud/check')
def cloud_check(body:KeyCheck):
    """Checks the key by listing models; no document is sent."""
    try:return cloud.check_key(body)
    except ValueError as e:raise cloud_failure(e)
    except httpx.HTTPError:raise HTTPException(502,'تعذر الاتصال بخدمة Gemini. تحقق من الإنترنت.')

@app.post('/api/gemini/read')
async def gemini_read(file:UploadFile=File(...),api_key:str=Form(...),model:str=Form(cloud.DEFAULT_MODEL),consent:bool=Form(False)):
    """The Gemini space: reads an uploaded file in memory and returns Gemini's reading.
    Nothing is stored: not the file, not the key, not the answer."""
    if not cloud.enabled():raise HTTPException(403,'القراءة السحابية مطفأة. شغّلها أولًا.')
    if not consent:raise HTTPException(403,'تحتاج موافقة صريحة على إرسال الملف إلى Google Gemini.')
    data=await file.read(cloud.MAX_UPLOAD_BYTES+1)
    from pydantic import SecretStr
    from starlette.concurrency import run_in_threadpool
    try:return await run_in_threadpool(cloud.read_upload,data,SecretStr(api_key),model)
    except ValueError as e:raise cloud_failure(e)
    except httpx.HTTPError:raise HTTPException(502,'تعذر الاتصال بخدمة Gemini. تحقق من الإنترنت.')
    finally:del data

@app.post('/api/batches/{bid}/documents/{did}/cloud')
def cloud_review(bid:str,did:str,body:CloudRequest):
    b=batch_or_404(bid);editable(b);d=doc_or_404(b,did)
    if not cloud.enabled():raise HTTPException(403,'القراءة السحابية مطفأة. شغّلها من إعدادات القراءة أولًا.')
    if not body.consent:raise HTTPException(403,'تحتاج هذه القراءة موافقة صريحة على إرسال الصورة إلى Google Gemini.')
    try:return read_cloud(storage.image_path(d['image_id']).read_bytes(),body)
    except ValueError as e:raise cloud_failure(e)
    except httpx.HTTPError:raise HTTPException(502,'تعذر الاتصال بخدمة Gemini. تحقق من الإنترنت؛ لم تتغير بيانات المستمسك.')
    except Exception:raise HTTPException(502,'تعذرت القراءة السحابية؛ لم تتغير بيانات المستمسك.')

class LocalAI(BaseModel):
    enabled:bool

@app.get('/api/local-ai')
def local_ai_status():
    from . import vision_llm
    return vision_llm.status()

class Learning(BaseModel):
    enabled:bool
@app.get('/api/learning')
def learning_status():
    from . import learning
    return learning.status()
@app.put('/api/learning')
def learning_switch(body:Learning):
    from . import learning
    return learning.set_enabled(body.enabled)
@app.post('/api/learning/train',status_code=202)
def learning_train():
    from . import learning
    try:learning.start_training()
    except RuntimeError as e:raise HTTPException(409,str(e))
    return learning.status()

@app.put('/api/local-ai')
def local_ai_switch(body:LocalAI):
    """Switch the optional local AI reader (Ollama) on/off; saved, applies immediately."""
    from . import vision_llm
    return vision_llm.set_enabled(body.enabled)

@app.get('/api/kyc/policy')
def kyc_policy():
    from . import kyc
    table=kyc.calibration()
    return kyc.policy()|{'calibration':{'fitted':bool(table),**({k:table.get(k) for k in ('fitted_on','samples','created','heldout')} if table else {})},
                         'profiles':kyc.PROFILES,'critical':{f'{k}:{s}':v for (k,s),v in kyc.CRITICAL.items()}}

@app.get('/api/batches/{bid}/kyc')
def batch_kyc(bid:str,profile:Literal['auto','individual','merchant']='auto',threshold:float|None=None):
    from . import kyc
    if threshold is not None and not .5<=threshold<=.999:raise HTTPException(422,'الحد يجب أن يكون بين 0.5 و0.999.')
    return kyc.assess_batch(batch_or_404(bid),profile,threshold)

@app.post('/api/capture-check')
async def capture_check(file:UploadFile=File(...)):
    """Capture-time guidance without OCR or storage: 'the corner is cut off, retake'."""
    from starlette.concurrency import run_in_threadpool
    from . import capture
    data=await file.read(25*1024*1024+1)
    if len(data)>25*1024*1024:raise HTTPException(413,'الحد 25 MB للصورة.')
    if not data:raise HTTPException(400,'الملف فارغ.')
    try:image,_=next(pipeline.pages_from_bytes(data,file.filename or 'capture'))
    except (ValueError,StopIteration) as e:raise HTTPException(422,str(e) or 'تعذر قراءة الصورة.')
    return await run_in_threadpool(capture.check_upload,image)

from .people_api import router as people_router
app.include_router(people_router)
from .training_api import router as training_router
app.include_router(training_router)
from .agent_api import router as agent_router
app.include_router(agent_router)

app.mount('/static' ,StaticFiles(directory=ROOT/'static'),name='static')
