import io
import zipfile
import numpy as np
import cv2
import pytest
import pypdfium2 as pdfium
from PIL import Image
from app import vision,pipeline,export,storage

def line(text):return {'text':text,'confidence':.9,'box':[[0,0],[10,0],[10,10],[0,10]]}

def test_filename_is_never_a_classification_input():
    assert vision.classify([line('مكتب المعلومات عنوان السكن اسم رب الاسرة')])['kind']=='housing'
    assert vision.classify([line('الرقم الوطني البطاقة الوطنية')])['kind']=='national_id'
    assert vision.classify([line('a holiday photo')])['kind']=='unknown'

def test_arabic_numeric_extraction_preserves_leading_zeroes():
    fields=vision.extract_fields([line('٠١٢٣٤٥٦٧٨٩٠١')],'national_id')
    assert fields[0]['value']=='012345678901'
    assert not fields[0]['verified']

def test_ambiguous_text_is_unknown():
    assert vision.classify([line('البطاقة الوطنية بطاقة السكن')])['kind']=='unknown'

def test_separate_cards_and_warp():
    im=np.full((1100,1100,3),50,np.uint8)
    cv2.rectangle(im,(60,65),(900,480),(220,233,240),-1)
    cv2.rectangle(im,(90,590),(930,1020),(235,240,230),-1)
    regions=vision.detect_regions(im)
    assert len(regions)==2
    assert all(vision.warp(im,r['points']).shape[1]>800 for r in regions)

def test_blank_page_is_retained():
    regions=vision.detect_regions(np.full((1100,780,3),255,np.uint8))
    assert len(regions)==1 and regions[0]['method']=='whole_page'

def test_invalid_quadrilateral():
    with pytest.raises(ValueError):vision.warp(np.zeros((100,100,3),np.uint8),[[1,1]]*4)

def test_grouping_does_not_merge_people_by_upload():
    docs=[{'id':'a','source_id':'s','kind':'national_id','side':'front'}, {'id':'b','source_id':'s','kind':'national_id','side':'front'}, {'id':'c','source_id':'z','kind':'housing','side':'front'}]
    pipeline.group_documents(docs)
    assert len({d['group'] for d in docs})==3

def test_national_grouping_requires_serial_even_on_same_page():
    docs=[{'id':'a','source_id':'s','kind':'national_id','side':'front'}, {'id':'b','source_id':'s','kind':'national_id','side':'back'}]
    pipeline.group_documents(docs);assert docs[0]['group']!=docs[1]['group']

def test_bad_image_is_rejected():
    with pytest.raises(ValueError):list(pipeline.pages_from_bytes(b'not an image','fake.png'))

def test_pdf_roundtrip_and_no_clipping(tmp_path,monkeypatch):
    paths={}
    for i in range(3):
        p=tmp_path/f'{i}.png';Image.new('RGB',(856,540),(80+i*60,180,150)).save(p);paths[str(i)]=p
    monkeypatch.setattr(export,'image_path',lambda iid:paths[iid])
    ds=[{'id':str(i),'image_id':str(i),'kind':'national_id','side':'front' if i==0 else 'back','group':'a' if i<2 else 'b','order':i} for i in range(3)]
    data=export.export_pdf(ds,size='card');doc=pdfium.PdfDocument(data)
    assert len(doc)==2
    assert all(abs(doc[i].get_size()[0]-595.2756)<1 for i in range(2))
    pixels=np.array(doc[0].render(scale=1).to_pil().convert('RGB'))
    mask=(pixels[:,:,1]>160)&(pixels[:,:,0]<150)&((pixels[:,:,1].astype(int)-pixels[:,:,0].astype(int))>30)
    ys,xs=np.where(mask)
    assert 240<=xs.max()-xs.min()<=244
    assert ys.min()>20 and ys.max()<800
    pages=list(pipeline.pages_from_bytes(data,'test.pdf'));assert len(pages)==2

def test_csv_formula_injection():
    d={'group':'=cmd','kind':'unknown','side':'unknown','source_name':'@file','page':1,'fields':[{'label':'Name','value':'+formula'}],'reviewed':False}
    csv=export.export_csv([d]).decode('utf-8-sig')
    assert "'=cmd" in csv and "'+formula" in csv

def test_no_path_traversal():
    with pytest.raises(ValueError):storage.image_path('../../secret')
