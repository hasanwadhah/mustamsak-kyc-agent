import numpy as np
from app import understanding as u

def line(text,x1,y1,x2,y2,confidence=.96):
    return {'text':text,'confidence':confidence,'box':u.quad([x1,y1,x2,y2])}

def test_arabic_label_neighbors_and_address_components():
    lines=[line('اسم رب الأسرة',280,100,400,122),line('أحمد سالم محمود',20,100,267,122),
           line('عنوان السكن',280,135,400,157),line('بغداد الكرادة محلة 901',20,135,267,157),
           line('المحافظة : بغداد',100,180,400,202)]
    f=u.generic_fields(lines,'housing')
    assert f['name']['value']=='أحمد سالم محمود'
    assert f['address']['value']=='بغداد الكرادة محلة 901'
    assert f['governorate']['value']=='بغداد'
    assert 'district' not in f

def test_explicit_dates_do_not_follow_page_order():
    f=u.generic_fields([line('تاريخ النفاذ : 2030/12/03',0,0,400,20),
                       line('تاريخ الولادة : ٢٠٠٠/١١/٠٢',0,40,400,60),
                       line('تاريخ الإصدار : 2020/12/04',0,80,400,100)],'civil_id')
    assert f['birth_date']['value']=='2000/11/02'
    assert f['expiry_date']['value']=='2030/12/03'
    assert f['issue_date']['value']=='2020/12/04'

def test_sex_is_explicit_and_blood_requires_abo_and_rh():
    assert u.valid_value('sex','ذكر')=='ذكر'
    assert u.valid_value('sex','أنثى')=='أنثى'
    assert u.valid_value('sex','أحمد')==''
    assert u.valid_value('sex','نكر')==''
    assert u.valid_value('blood_group','0 +')=='O+'
    assert u.valid_value('blood_group','AB−')=='AB-'
    assert u.valid_value('blood_group','C+')==''
    assert u.valid_value('blood_group','O')=='O'  # Rh is not invented
    assert u.valid_value('birth_date','2023/02/29')==''

def test_nationality_header_does_not_hide_sex_label():
    im=np.zeros((540,856,3),np.uint8)
    lines=[line('مديرية الجنسية العامة',450,10,810,40),
           line('الاسم / ناو : خالد',520,215,810,252),
           line('الأب / باوك : سامي',520,260,810,295),
           line('الأم / دايك : مريم',520,355,810,390),
           line('الجنس : ذكر',520,442,810,480)]
    regions=u.template_regions(im,lines,'national_id','front')
    keys={r[0] for r in regions}
    assert {'first_name','father_name','mother_name','sex'}<=keys
    assert not u.template_regions(im,lines,'housing','front')

def test_layout_requires_anchors_not_just_category():
    im=np.full((540,856,3),255,np.uint8)
    assert not u.template_regions(im,[],'national_id','front')
    assert not u.template_regions(im,[line('الجنس',0,0,100,20)],'national_id','front')
    assert not u.template_regions(np.zeros((900,500,3),np.uint8),[],'national_id','back')

def test_handwriting_candidates_are_not_saved_as_facts(monkeypatch):
    monkeypatch.setattr(u.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':'عنوان مقترح','confidence':.99} for _ in crops])
    f=u.read_regions(np.zeros((100,200,3),np.uint8),[('address',[0,0,190,30],'arabic')],'housing')['address']
    assert f['value']=='' and f['status']=='unreadable'
    assert f['candidates'][0]['value']=='عنوان مقترح'
    assert not f['verified']

def test_ocr_disagreement_is_visible(monkeypatch):
    monkeypatch.setattr(u.arabic_ocr,'recognize_crops',lambda crops,language:[{'text':'خالد','confidence':.97},{'text':'حالد','confidence':.96}])
    f=u.read_regions(np.zeros((100,200,3),np.uint8),[('first_name',[0,0,190,30],'arabic')],'national_id')['first_name']
    assert f['status']=='conflict' and len(f['candidates'])==2

def test_unknown_person_does_not_receive_guessed_name_or_address(monkeypatch):
    monkeypatch.setattr(u.arabic_ocr,'available',lambda:False)
    f=u.extract(None,[],'housing','front',[])
    assert all(x['value']=='' and not x['verified'] for x in f)
    assert {'address','name','neighborhood'}<={x['key'] for x in f}


def test_missing_labels_can_use_regular_rows_but_single_grand_label_keeps_its_side():
    im=np.zeros((540,856,3),np.uint8)
    lines=[line('الاسم ناو خالد',530,210,810,248),line('الأب باوك سامي',530,250,810,288),
           line('نص لقب غير واضح',510,330,810,368),line('الأم دايك مريم',530,370,810,408),
           line('الجد حسن',530,410,810,448),line('الجنس ذكر',530,450,810,488),line('نص آخر',490,490,810,528)]
    regions=u.template_regions(im,lines,'national_id','front');r={k:b for k,b,_ in regions}
    assert {'surname','blood_group','grandfather_name','maternal_grandfather'}<=r.keys()
    assert r['grandfather_name'][1]<r['mother_name'][1]<r['maternal_grandfather'][1]
