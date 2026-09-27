from copy import deepcopy
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import arabic_ocr,focused_fields as f,understanding as u,main,storage,pipeline,vision
from app.mrz import check_digit

def line(text,x1=40,y1=400,x2=860,y2=435):
    return {'text':text,'confidence':.96,'box':u.quad([x1,y1,x2,y2])}

@pytest.mark.parametrize('raw,expected',[
    ('٢٠٢٤ / ٠٢ / ٢٩','2024/02/29'),('۲۹-۰۲-۲۰۲۴','2024/02/29'),
    ('تاريخ الإصدار: 2016 / 09 / 28','2016/09/28'),
    ('\u200f2028 /\u200e09/25','2028/09/25'),('2024 02 29','2024/02/29'),
])
def test_calendar_and_digit_formats(raw,expected):
    assert f.date_readings(raw)[0]['value']==expected
    assert u.valid_value('issue_date',raw)==expected

@pytest.mark.parametrize('raw',['2023/02/29','2024/13/01','24/02/29','٣٠١٠٩٦','199809302302'])
def test_invalid_dates_and_missing_centuries_are_not_completed(raw):
    assert not f.date_readings(raw,allow_compact=True)

def test_repaired_and_compact_dates_remain_approximate():
    assert f.date_readings('2O24/O2/29')[0]['approximate']
    assert f.date_readings('20240229',True)[0]['approximate']
    assert not u.valid_value('issue_date','2O24/O2/29')

@pytest.mark.skipif(not arabic_ocr.available(), reason='Arabic OCR model not installed: run setup.ps1')
def test_housing_region_uses_form_label_not_merged_numeric_value():
    im=np.zeros((568,876,3),np.uint8)
    lines=[line('عنوان الكن م٩٤٧٣',175,404,833,495),line('رقم الاستمارة',655,475,821,524),line('12345',309,475,550,534)]
    regions=f.housing_regions(im,lines,'front')
    address=next(r for r in regions if r['key']=='address')
    assert 660<address['box'][1][0]<695
    assert address['box'][2][1]-address['box'][1][1]>80
    assert not f.housing_regions(im,[line('مجرد نص',100,400,800,450)],'front')

def test_adaptive_date_roles_and_unknown_expiry_label(monkeypatch):
    monkeypatch.setattr(f,'colon_column',lambda image:530)
    im=np.zeros((564,899,3),np.uint8)
    lines=[line(t,300,20+i*40,860,52+i*40) for i,t in enumerate([
        'جهة الاصدار','تاريخ الاصدار','تاريخ الثفابؤزي','محل الولادة','تاريخ الولادة','الرقم العائلي'])]
    regions={r['key']:r for r in f.national_regions(im,lines)}
    assert regions['expiry_date']['role_inferred']
    assert not regions['birth_date']['role_inferred']
    assert regions['issue_date']['box'][1][0]>520
    assert not f.national_regions(im,[])

def test_handwritten_partial_is_visible_and_not_a_full_date(monkeypatch):
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':'٣٠١٠٩٦','confidence':.86} for _ in crops])
    fields=f.read_regions(np.zeros((100,200,3),np.uint8),[{'key':'issue_date','box':u.quad([0,0,190,80]),'language':'arabic','method':'housing_date_line','handwritten':True}])
    assert fields['issue_date']['value']=='301096'
    assert fields['issue_date']['date_precision']=='partial'
    assert fields['issue_date']['status']=='approximate'

def test_address_components_require_explicit_labels_and_keep_uncertainty():
    address=u.field('address','بغداد م ٦٧٣ ز ٣ د ٨',.8,method='housing_label_line',status='approximate')
    parts=f.address_parts(address)
    assert {k:v['value'] for k,v in parts.items()}=={'mahalla_number':'673','street':'3','house_number':'8'}
    assert all(v['status']=='approximate' and not v['verified'] for v in parts.values())
    assert f.address_parts({'value':'673 3 8'})=={}

def mrz_lines(birth='010101',expiry='260927'):
    serial='AB1234567'
    return [line('IDIRQ'+serial+check_digit(serial)+'<'*15,y1=370,y2=408),
            line(birth+check_digit(birth)+'M'+expiry+check_digit(expiry)+'1RQ'+'<'*11+'0',y1=413,y2=451)]

def test_date_checksum_works_without_name_but_not_without_serial():
    lines=mrz_lines();checked=f.checked_mrz_dates(lines,(564,899,3))
    assert checked['expiry_date']['yymmdd']=='260927'
    assert not f.checked_mrz_dates(lines[1:],(564,899,3))
    damaged=deepcopy(lines);damaged[1]['text']='020101'+damaged[1]['text'][6:]
    assert 'birth_date' not in f.checked_mrz_dates(damaged,(564,899,3))

def test_mrz_partial_does_not_invent_century_and_conflict_is_visible():
    fields={};f.crosscheck_mrz(fields,mrz_lines(),(564,899,3))
    assert fields['birth_date']['value']=='??01/01/01'
    assert fields['birth_date']['status']=='approximate'
    fields={'birth_date':u.field('birth_date','2001/01/02',.99,note='')}
    f.crosscheck_mrz(fields,mrz_lines(),(564,899,3))
    assert fields['birth_date']['status']=='conflict'
    assert fields['birth_date']['value']=='2001/01/02'

def test_merge_keeps_manual_verified_and_unrelated_fields():
    fields=[u.field('issue_date','2024/09/01',method='manual',status='manual'),
            dict(u.field('address','العنوان المصحح'),verified=True),u.field('name','اسم محفوظ')]
    before=deepcopy(fields)
    updates={'issue_date':u.field('issue_date','2030/09/01'), 'address':u.field('address','نص آخر'),
             'name':u.field('name','اسم آخر'),'expiry_date':u.field('expiry_date','2020/01/01')}
    merged={v['key']:v for v in f.merge_refined(fields,updates,'a'*32)}
    for old in before:assert merged[old['key']]==old
    assert fields==before
    assert merged['expiry_date']['status']=='conflict'

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    for name in ['images','batches','exports']:(tmp_path/name).mkdir()
    monkeypatch.setattr(main.arabic_ocr,'available',lambda:True)
    with TestClient(main.app) as client:yield client

def fixture_batch():
    b=pipeline.new_batch('refinement');b['status']='ready'
    iid=storage.uid();vision.save_image(storage.image_path(iid),np.zeros((100,160,3),np.uint8))
    b['documents']=[{'id':storage.uid(),'kind':'national_id','side':'back','image_id':iid,
      'field_image_id':iid,'fields':[u.field('issue_date'),u.field('name','اسم محفوظ')],'ocr':[],'reviewed':False}]
    storage.save_batch(b);return b

def test_api_refresh_preserves_reviewed_documents(api,monkeypatch):
    b=fixture_batch();reviewed=deepcopy(b['documents'][0]);reviewed.update(id=storage.uid(),reviewed=True)
    b['documents'].append(reviewed);storage.save_batch(b)
    monkeypatch.setattr(f,'extract',lambda *args:{'issue_date':u.field('issue_date','2020/01/01',.99)})
    response=api.post(f"/api/batches/{b['id']}/refine-fields")
    assert response.status_code==200
    result=response.json();assert result['updated_documents']==1 and result['skipped_reviewed']==1
    assert result['batch']['documents'][1]==reviewed
    assert result['batch']['documents'][0]['fields'][0]['source_image_id']==b['documents'][0]['image_id']

def test_concurrent_edit_is_not_overwritten(api,monkeypatch):
    b=fixture_batch()
    def concurrent(*args):
        current=storage.get_batch(b['id']);current['documents'][0]['fields'][0]=u.field('issue_date','2021/01/01',method='manual',status='manual');storage.save_batch(current)
        return {'issue_date':u.field('issue_date','2020/01/01',.99)}
    monkeypatch.setattr(f,'extract',concurrent)
    assert api.post(f"/api/batches/{b['id']}/refine-fields").status_code==409
    assert storage.get_batch(b['id'])['documents'][0]['fields'][0]['value']=='2021/01/01'


def test_compact_address_still_requires_visible_markers():
    parts=f.address_parts({'value':'م٦٧٣ز٣د٨','status':'approximate'})
    assert [parts[k]['value'] for k in ('mahalla_number','street','house_number')]==['673','3','8']
    assert f.address_parts({'value':'المحلة 901 الزقاق 12 الدار 3/4'})['house_number']['value']=='3/4'


def test_housing_date_label_merged_with_value_keeps_its_label_column():
    im=np.zeros((250,370,3),np.uint8)
    lines=[line('تاريخ',316,126,350,146),line('تنظيم',281,127,319,147),
           line('الاستمارة',228,125,283,149),line('W&Ie',141,128,231,150)]
    region=f.housing_regions(im,lines,'back')[0]
    assert region['key']=='issue_date'
    assert 220<region['box'][1][0]<228


def test_partial_update_does_not_erase_clear_date_on_repeated_refinement():
    original=[u.field('issue_date','2020/01/01',.99,method='field_crop')]
    update={'issue_date':u.field('issue_date','202?',.7,method='housing_date_line',status='approximate')}
    once=f.merge_refined(original,update)
    assert once[0]['value']=='2020/01/01' and once[0]['status']=='conflict'
    assert f.merge_refined(once,update)==once


def test_csv_retains_approximate_status_and_precision():
    import csv,io
    from app.export import export_csv
    doc={'group':'test','kind':'housing','side':'back','source_name':'sample','page':1,'reviewed':False,
         'fields':[u.field('issue_date','301096',.7,status='approximate',date_precision='partial',note='قراءة جزئية')]}
    content=export_csv([doc])
    if isinstance(content,bytes):content=content.decode('utf-8-sig')
    row=next(csv.DictReader(io.StringIO(content)))
    assert row['field_status']=='approximate' and row['date_precision']=='partial'


def test_handwritten_year_agreement_does_not_fabricate_month_day(monkeypatch):
    outputs=['٢٠٠٧٤٢٤٤','٢٠٠٧١٤٢٢٤','٢٠٠٧٤٢٠٥']
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':text,'confidence':.8} for text in outputs])
    fields=f.read_regions(np.zeros((100,200,3),np.uint8),[{'key':'issue_date','box':u.quad([0,0,190,80]),'language':'arabic','method':'housing_date_line','handwritten':True}])
    assert fields['issue_date']['value']=='2007/??/??'
    assert fields['issue_date']['status']=='approximate'
    assert fields['issue_date']['date_precision']=='partial'
    assert len(fields['issue_date']['candidates'])==4



def test_back_schema_does_not_request_front_gender(monkeypatch):
    monkeypatch.setattr(f.arabic_ocr,'available',lambda:False)
    fields=u.extract(None,[line('الجنس: ذكر')],'national_id','back',[])
    assert not any(v['key']=='sex' for v in fields)
    assert 'sex' in u.SCHEMAS[('national_id','front')]
    assert 'issuing_authority' in u.SCHEMAS[('national_id','back')]


@pytest.mark.parametrize('gender',['ذكر','أنثى'])
def test_front_gender_reads_its_own_value_column(gender,monkeypatch):
    monkeypatch.setattr(f,'colon_column',lambda *args:700)
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':gender,'confidence':.97} for _ in crops])
    im=np.zeros((580,900,3),np.uint8)
    lines=[line(text,620,y,860,y+36) for text,y in [('الاسم',240),('الأب',280),('الأم',400),('الجنس',480)]]
    regions=f.national_front_regions(im,lines)
    assert len(regions)==1 and regions[0]['box'][1][0]<700
    field=f.read_regions(im,regions)['sex']
    assert field['value']==gender and field['method']=='national_front_sex'
    assert all(point[1]>450 for point in field['box'])
    assert not f.national_front_regions(im,[line('مديرية الجنسية العامة',450,10,860,40)])


def test_issuing_authority_uses_visible_text_not_a_fixed_location_name(monkeypatch):
    monkeypatch.setattr(f,'colon_column',lambda *args:530)
    im=np.zeros((564,899,3),np.uint8)
    lines=[line(text,260,y,860,y+38) for text,y in [('جهة الاصدار',25),('تاريخ الاصدار',65),('تاريخ النفاذ',105),('محل الولادة',145)]]
    region=next(r for r in f.national_regions(im,lines) if r['key']=='issuing_authority')
    assert region['box'][1][0]>520
    assert region['box'][2][1]-region['box'][1][1]>45
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':'دائرة احوال البصرة','confidence':.96} for _ in crops])
    assert f.read_regions(im,[region])['issuing_authority']['value']=='دائرة احوال البصرة'
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':'','confidence':0} for _ in crops])
    assert 'issuing_authority' not in f.read_regions(im,[region])


def test_refresh_removes_old_back_gender_but_keeps_manual_entries(api,monkeypatch):
    b=fixture_batch();d=b['documents'][0]
    d['fields'].append(u.field('sex'))
    storage.save_batch(b)
    monkeypatch.setattr(f,'extract',lambda *args:{'issuing_authority':u.field('issuing_authority','دائرة احوال البصرة',.97)})
    updated=api.post(f"/api/batches/{b['id']}/refine-fields").json()['batch']['documents'][0]
    assert not any(v['key']=='sex' for v in updated['fields'])
    assert next(v['value'] for v in updated['fields'] if v['key']=='issuing_authority')=='دائرة احوال البصرة'
    updated['fields'].append(u.field('sex','ذكر',method='manual',status='manual'))
    b['documents']=[updated];storage.save_batch(b)
    result=api.post(f"/api/batches/{b['id']}/refine-fields").json()['batch']['documents'][0]
    assert next(v['value'] for v in result['fields'] if v['key']=='sex')=='ذكر'


def test_selective_refresh_now_includes_front_gender(api,monkeypatch):
    b=fixture_batch();d=b['documents'][0];d['side']='front';d['fields']=[u.field('sex')];storage.save_batch(b)
    monkeypatch.setattr(f,'extract',lambda image,lines,kind,side:{'sex':u.field('sex','أنثى',.97,method='national_front_sex')} if side=='front' else {})
    result=api.post(f"/api/batches/{b['id']}/refine-fields").json()['batch']['documents'][0]
    assert result['fields'][0]['value']=='أنثى' and result['fields'][0]['source_image_id']==d['image_id']
