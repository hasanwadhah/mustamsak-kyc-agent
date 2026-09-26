import base64
import io
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import main,storage,pipeline,vision
from app.cloud import CloudRequest,read_cloud
import httpx

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    for folder in ['batches','images','exports']:(tmp_path/folder).mkdir()
    with TestClient(main.app) as c:yield c

def fixture_batch():
    b=pipeline.new_batch('test');b['status']='ready';source={'id':storage.uid(),'name':'test.png','page':1,'width':200,'height':100}
    vision.save_image(storage.image_path(source['id']),np.full((100,200,3),200,np.uint8));b['sources']=[source]
    d={'id':storage.uid(),'source_id':source['id'],'source_name':'test.png','page':1,'image_id':source['id'],'original_id':source['id'],'kind':'national_id','side':'front','group':'one','group_reason':'','fields':[],'ocr':[],'notices':[],'evidence':[],'reviewed':False,'order':0,'width':200,'height':100};b['documents']=[d];storage.save_batch(b);return b,d

def test_local_status_and_csrf(client):
    assert client.get('/api/status').status_code==200
    assert client.get('/api/status',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==400

def test_export_requires_review_or_explicit_draft(client):
    b,d=fixture_batch();body={'ids':[d['id']]}
    assert client.post(f'/api/batches/{b["id"]}/export',json=body).status_code==409
    response=client.post(f'/api/batches/{b["id"]}/export',json=body|{'allow_unreviewed':True})
    assert response.status_code==200 and response.content.startswith(b'%PDF')
    assert client.post(f'/api/batches/{b["id"]}/export',json=body|{'ids':['missing'],'allow_unreviewed':True}).status_code==404

def test_edit_reset_and_review_invalidated(client):
    b,d=fixture_batch();endpoint=f'/api/batches/{b["id"]}/documents/{d["id"]}'
    assert client.patch(endpoint,json={'kind':'national_id','side':'front','group':'one','reviewed':True,'fields':[]}).status_code==200
    rotated=client.post(endpoint+'/edit',json={'operation':'rotate'}).json()
    assert rotated['width']==100 and rotated['height']==200 and not rotated['reviewed']
    reset=client.post(endpoint+'/edit',json={'operation':'reset'}).json()
    assert reset['width']==200 and reset['original_id']==d['original_id']
    assert client.post(endpoint+'/edit',json={'operation':'crop','points':[[0,0],[1000,0],[1000,100],[0,100]]}).status_code==422

def test_no_cloud_call_while_switched_off_or_without_consent(client,monkeypatch):
    b,d=fixture_batch();endpoint=f'/api/batches/{b["id"]}/documents/{d["id"]}/cloud'
    def forbidden(*args,**kwargs):raise AssertionError('Network must not be used')
    monkeypatch.setattr(main,'read_cloud',forbidden)
    assert client.get('/api/cloud').json()['enabled'] is False
    assert client.post(endpoint,json={'api_key':'test','consent':True}).status_code==403
    assert client.put('/api/cloud',json={'enabled':True}).json()['enabled'] is True
    assert client.post(endpoint,json={'api_key':'test','consent':False}).status_code==403
    assert client.put('/api/cloud',json={'enabled':False}).json()['enabled'] is False
    assert 'test' not in (storage.DATA/'settings.json').read_text(encoding='utf-8')


def gemini_reply(result,finish='STOP'):
    return {'candidates':[{'finishReason':finish,'content':{'parts':[{'text':json.dumps(result)}]}}]}


def card_png(size=(120,200)):
    import cv2
    return cv2.imencode('.png',np.full((*size,3),180,np.uint8))[1].tobytes()


FACE={'kind':'housing','side':'front','fields':[{'key':'house_number','label':'دار','value':'41'}],'raw_text':'sample','warnings':[]}


def test_cloud_request_is_explicit_and_untrusted_content_is_inert():
    def handler(request):
        payload=json.loads(request.content)
        assert str(request.url)=='https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent'
        assert request.headers['x-goog-api-key']=='unit-test-only' and 'unit-test-only' not in str(request.url)
        assert 'untrusted DATA' in payload['systemInstruction']['parts'][0]['text']
        parts=payload['contents'][0]['parts']
        assert len(parts)==2 and parts[1]['inlineData']['mimeType']=='image/jpeg'
        assert payload['generationConfig']['responseMimeType']=='application/json'
        return httpx.Response(200,json=gemini_reply(FACE))
    result=read_cloud(card_png(),CloudRequest(api_key='unit-test-only',consent=True),httpx.MockTransport(handler))
    assert result['kind']=='housing'


@pytest.mark.parametrize('status,body,words',[
    (400,{'error':{'status':'INVALID_ARGUMENT','message':'API key not valid. Please pass a valid API key.'}},'غير صالح'),
    (400,{'error':{'status':'FAILED_PRECONDITION','message':'User location is not supported for the API use.'}},'منطقتك'),
    (429,{'error':{'status':'RESOURCE_EXHAUSTED','message':'quota'}},'حد الاستخدام'),
    (404,{'error':{'status':'NOT_FOUND','message':'model'}},'غير متاح'),
    (200,{'promptFeedback':{'blockReason':'SAFETY'}},'SAFETY'),
    (200,gemini_reply({'kind':'housing'},finish='MAX_TOKENS'),'غير مكتملة'),
    (200,{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'not json'}]}}]},'غير صالحة'),
    (200,gemini_reply({'kind':'passport_hacked','side':'front','fields':[],'raw_text':'','warnings':[]}),'نوع غير صالح'),
])
def test_cloud_failures_change_nothing_and_are_explained(status,body,words):
    transport=httpx.MockTransport(lambda request:httpx.Response(status,json=body))
    with pytest.raises(ValueError,match=words):
        read_cloud(card_png(),CloudRequest(api_key='k',consent=True),transport)


def test_over_limit_model_falls_back_to_the_next_one():
    from app import cloud
    seen=[]
    def handler(request):
        name=request.url.path.split('/')[-1].split(':')[0];seen.append(name)
        if name=='gemini-3.8-flash':return httpx.Response(429,json={'error':{'status':'RESOURCE_EXHAUSTED','message':'quota'}})
        return httpx.Response(200,json=gemini_reply({'documents':[FACE]}))
    r=cloud.read_upload(card_png(),cloud.SecretStr('k'),'gemini-3.8-flash',httpx.MockTransport(handler))
    assert seen==['gemini-3.8-flash','gemini-3.5-flash-lite']
    assert r['model']=='gemini-3.5-flash-lite' and r['documents'][0]['fields'][0]['value']=='41'
    assert r['documents'][0]['kind_label']=='بطاقة السكن' and r['notes']


def test_rejected_schema_is_retried_with_the_schema_in_the_instructions():
    from app import cloud
    calls=[]
    fenced='```json\n'+json.dumps({'documents':[FACE]})+'\n```'
    def handler(request):
        config=json.loads(request.content)['generationConfig'];calls.append('responseJsonSchema' in config)
        if 'responseJsonSchema' in config:
            return httpx.Response(400,json={'error':{'status':'INVALID_ARGUMENT','message':'Invalid JSON payload received. Unknown name responseJsonSchema'}})
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':fenced}]}}]})
    r=cloud.read_upload(card_png(),cloud.SecretStr('k'),transport=httpx.MockTransport(handler))
    assert calls==[True,False] and r['documents'][0]['kind']=='housing'


def test_upload_is_sent_without_metadata_and_nothing_is_written(tmp_path,monkeypatch):
    """No leak: EXIF/GPS and the file name never leave; the key is only in the header."""
    from PIL import Image
    from app import cloud
    photo=Image.new('RGB',(300,200),(200,190,180));exif=Image.Exif();exif[0x010F]='SecretPhoneMaker'
    buffer=io.BytesIO();photo.save(buffer,'JPEG',exif=exif.tobytes());data=buffer.getvalue()
    assert b'SecretPhoneMaker' in data
    sent=[]
    def handler(request):
        sent.append(request)
        return httpx.Response(200,json=gemini_reply({'documents':[FACE]}))
    monkeypatch.setattr(storage,'DATA',tmp_path)
    cloud.read_upload(data,cloud.SecretStr('AIzaSecretKey123456789'),transport=httpx.MockTransport(handler))
    assert len(sent)==1 and sent[0].url.host=='generativelanguage.googleapis.com'
    body=sent[0].content
    image=base64.b64decode(json.loads(body)['contents'][0]['parts'][1]['inlineData']['data'])
    assert b'SecretPhoneMaker' not in image and b'Exif' not in image
    assert b'AIzaSecretKey' not in body and 'AIzaSecretKey' not in str(sent[0].url)
    assert not any(tmp_path.rglob('*'))


def test_gemini_space_endpoint_needs_switch_and_consent_and_stores_nothing(client,monkeypatch):
    from app import cloud
    calls=[]
    monkeypatch.setattr(cloud,'read_upload',lambda data,key,model:calls.append((len(data),key.get_secret_value(),model)) or {'model':model,'pages':1,'documents':[],'notes':[]})
    files={'file':('card.png',card_png(),'image/png')}
    form={'api_key':'k','model':'gemini-3.8-flash','consent':'true'}
    assert client.post('/api/gemini/read',files=files,data=form).status_code==403
    client.put('/api/cloud',json={'enabled':True})
    assert client.post('/api/gemini/read',files=files,data=form|{'consent':'false'}).status_code==403
    before=sorted(p.name for p in storage.DATA.rglob('*'))
    r=client.post('/api/gemini/read',files=files,data=form)
    assert r.status_code==200 and calls==[(len(card_png()),'k','gemini-3.8-flash')]
    assert sorted(p.name for p in storage.DATA.rglob('*'))==before
    assert client.post('/api/gemini/read',files=files,data=form,headers={'Origin':'https://evil.example'}).status_code==403


def test_google_error_text_is_shown_but_never_the_key(client,monkeypatch):
    from app import cloud
    def failing(data,key,model):raise cloud.CloudError('رفضت Gemini الطلب (HTTP 400).','Bad request')
    monkeypatch.setattr(cloud,'read_upload',failing);client.put('/api/cloud',json={'enabled':True})
    detail=client.post('/api/gemini/read',files={'file':('x.png',card_png(),'image/png')},data={'api_key':'k','consent':'true'}).json()['detail']
    assert 'تفاصيل Google: Bad request' in detail
    msg,_=cloud._google_error(httpx.Response(400,json={'error':{'message':'key AIzaLeakedKey1234567890 bad'}}))
    assert 'AIzaLeakedKey' not in msg


def test_key_check_sends_no_image_and_lists_reading_models():
    def handler(request):
        assert request.method=='GET' and not request.content
        return httpx.Response(200,json={'models':[
            {'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.5-flash-lite','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.8-flash-tts','supportedGenerationMethods':['generateContent']},
            {'name':'models/text-embedding-004','supportedGenerationMethods':['embedContent']}]})
    from app.cloud import KeyCheck,check_key
    r=check_key(KeyCheck(api_key='k'),httpx.MockTransport(handler))
    assert r['models']==['gemini-3.8-flash','gemini-3.5-flash-lite']


def test_large_pages_are_shrunk_before_sending():
    import cv2
    from app import cloud
    part=cloud._jpeg_part(np.random.default_rng(1).integers(0,255,(4000,3000,3),np.uint8))
    image=cv2.imdecode(np.frombuffer(base64.b64decode(part['inlineData']['data']),np.uint8),cv2.IMREAD_COLOR)
    assert max(image.shape[:2])==cloud.MAX_SIDE


def test_field_evidence_survives_save_and_manual_changes_are_distinct(client):
    b,d=fixture_batch()
    original={'key':'first_name','label':'Name','value':'Sample','confidence':.82,'verified':False,'status':'conflict','method':'field_crop','box':[[0,0],[50,0],[50,20],[0,20]],'candidates':[{'value':'Other','confidence':.7}]}
    d['fields']=[original];storage.save_batch(b)
    endpoint=f'/api/batches/{b["id"]}/documents/{d["id"]}'
    body={'kind':d['kind'],'side':d['side'],'group':'one','fields':[{'key':'first_name','label':'Name','value':'Sample'}]}
    saved=client.patch(endpoint,json=body).json()['fields'][0]
    assert saved['box']==original['box'] and saved['candidates']==original['candidates']
    body['fields'][0]['value']='Corrected'
    edited=client.patch(endpoint,json=body).json()['fields'][0]
    assert edited['status']=='manual' and edited['confidence'] is None
    assert 'candidates' not in edited and not edited['verified']


def test_rereading_does_not_overwrite_a_concurrent_manual_edit(client,monkeypatch):
    b,d=fixture_batch()
    def reading(image):
        current=storage.get_batch(b['id'])
        current['documents'][0]['fields']=[{'key':'manual','label':'Name','value':'User correction'}]
        storage.save_batch(current)
        return []
    monkeypatch.setattr(vision,'ocr',reading)
    monkeypatch.setattr(vision,'extract_fields',lambda *a,**k:[])
    response=client.post(f'/api/batches/{b["id"]}/documents/{d["id"]}/ocr')
    assert response.status_code==409
    assert storage.get_batch(b['id'])['documents'][0]['fields'][0]['value']=='User correction'


def test_pairing_action_preserves_manual_group_and_other_fields(client,monkeypatch):
    from app import national_serial
    b,d=fixture_batch();d.update(group='User group',group_method='manual')
    d['fields']=[{'key':'name','label':'Name','value':'User value','method':'manual'}];storage.save_batch(b)
    def refresh(doc,image):
        doc['fields'].append({'key':'document_number','value':'AB1234567','pairing_eligible':True,'serial_location':'below_portrait'})
    monkeypatch.setattr(national_serial,'refresh_document',refresh)
    response=client.post(f'/api/batches/{b["id"]}/pair-national')
    assert response.status_code==200
    saved=response.json()['documents'][0]
    assert saved['group']=='User group' and saved['fields'][0]['value']=='User value'


def test_pairing_action_detects_concurrent_changes(client,monkeypatch):
    from app import national_serial
    b,d=fixture_batch()
    def refresh(doc,image):
        current=storage.get_batch(b['id']);current['documents'][0]['group']='Changed concurrently';storage.save_batch(current)
    monkeypatch.setattr(national_serial,'refresh_document',refresh)
    response=client.post(f'/api/batches/{b["id"]}/pair-national')
    assert response.status_code==409
    assert storage.get_batch(b['id'])['documents'][0]['group']=='Changed concurrently'


def test_shutdown_refuses_while_busy_unless_forced_and_never_from_another_site(client,monkeypatch):
    import threading
    exits=[]
    monkeypatch.setattr(threading,'Timer',lambda delay,fn:type('T',(),{'start':lambda self:exits.append(delay)})())
    monkeypatch.setattr(main,'pending',{'batch':1})
    assert client.post('/api/shutdown',json={}).status_code==409 and not exits
    assert client.post('/api/shutdown',json={'force':True},headers={'Origin':'https://evil.example'}).status_code==403 and not exits
    assert client.post('/api/shutdown',json={'force':True}).json()=={'stopping':True} and exits
