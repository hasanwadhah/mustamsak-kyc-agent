from copy import deepcopy
import numpy as np

from app import focused_fields as f, understanding as u
from app.housing_names import add_name_suggestions
from app.iraqi_addresses import enrich_housing, reference
from app.housing_handwriting import read_address_symbols


def test_mahalla_and_named_area_are_separate_and_digits_are_preserved():
    parts=f.address_parts(u.field('address','بغداد / الغزالية م ٦٧٣ ز ٢٧ د ٨',status='approximate'))
    assert {k:v['value'] for k,v in parts.items()}=={'mahalla_number':'673','street':'27','house_number':'8'}
    assert 'neighborhood' not in parts
    assert all(v['status']=='approximate' and not v['verified'] for v in parts.values())
    assert f.address_parts({'value':'673 27 8'})=={}
    parts=f.address_parts({'value':'المحلة 0673 الزقاق 040 الدار 9/2','status':'read'})
    assert parts['mahalla_number']['value']=='0673' and parts['house_number']['value']=='9/2'


def test_geography_requires_both_a_name_and_mahalla_and_keeps_source():
    fields={'information_office':u.field('information_office','الفزالية',.7,status='approximate'),
            'mahalla_number':u.field('mahalla_number','673',.8,status='approximate')}
    enrich_housing(fields)
    assert fields['information_office']['value']=='الفزالية'
    assert fields['information_office']['candidates'][0]['value']=='الغزالية'
    assert fields['neighborhood']['value']=='الغزالية'
    assert fields['governorate']['value']=='بغداد'
    assert fields['governorate']['status']=='approximate' and not fields['governorate']['verified']
    assert fields['governorate']['source']['url'].startswith('https://iasj.')
    assert len(reference()['governorates'])==19 and 'حلبجة' in reference()['governorates']


def test_no_province_from_number_alone_or_conflicting_geography():
    for fields in [
        {'mahalla_number':u.field('mahalla_number','673')},
        {'information_office':u.field('information_office','الغزالية')},
        {'information_office':u.field('information_office','الغزالية'), 'mahalla_number':u.field('mahalla_number','673',status='conflict')},
        {'information_office':u.field('information_office','الغزالية'), 'mahalla_number':u.field('mahalla_number','999')},
        {'information_office':u.field('information_office','الغزالية'), 'mahalla_number':u.field('mahalla_number','673'), 'address':u.field('address','محافظة البصرة م 673 ز 40 د 9')}
    ]:
        enrich_housing(fields)
        assert fields.get('governorate',{}).get('value')!='بغداد'
        assert not fields.get('neighborhood',{}).get('value')


def test_name_correction_is_an_option_not_a_new_identity():
    # Different test names from the user's sample; exercise fused prefix and tail.
    value='محمداحمدعيد الأ فير'
    field=u.field('name',value,status='approximate',candidates=[{'value':value,'confidence':.6}])
    add_name_suggestions(field)
    assert field['value']==value and not field['verified']
    assert field['candidates'][0]['value']=='محمد احمد عبد الأمير'
    assert field['candidates'][0]['confidence'] is None
    for value in ['اسم غريب الأفير','محمد احمد زيد علي','محمد احمد عبدالجبار']:
        field=u.field('name',value,status='approximate',candidates=[{'value':value}])
        add_name_suggestions(field)
        assert not any(c.get('engine')=='name_spelling_suggestion' for c in field['candidates'])


def test_manual_values_are_not_replaced_by_housing_ocr():
    old=u.field('name','اسم اختاره المستخدم',method='manual',status='manual')
    fresh=u.field('name','اقتراح',method='housing_label_line',status='approximate')
    assert f.merge_refined([old],{'name':fresh})==[old]
    untouched=u.field('name','اسم من الموحدة')
    assert f.merge_refined([untouched],{'name':u.field('name','اسم آخر')})==[untouched]
    assert f.merge_refined([] ,{'name':fresh})[0]['value']=='اقتراح'


def test_blank_image_cannot_supply_address_symbols(monkeypatch):
    monkeypatch.setattr(f.arabic_ocr,'recognize_crops',lambda crops,language='arabic':[])
    image=np.full((100,500,3),255,np.uint8)
    assert read_address_symbols(image,{'box':u.quad([0,0,499,99])})=={}


def test_address_assembly_keeps_disputed_zero_visible():
    fields={key:u.field(key,value,.7,method='housing_ink_components',status='approximate')
            for key,value in [('mahalla_number','901'),('street','40'),('house_number','9')]}
    fields['street'].update(status='conflict',candidates=[{'value':'40'},{'value':'4'}])
    enrich_housing(fields)
    assert fields['address']['value']=='م 901 — ز 40 — د 9'
    assert fields['address']['status']=='conflict'
    assert len(fields['street']['candidates'])==2


def test_compound_name_missing_letter_remains_only_a_suggestion():
    value='محمد احمد عد الأ فير'
    field=u.field('name',value,status='approximate',candidates=[{'value':value}])
    add_name_suggestions(field)
    assert field['value']==value
    assert field['candidates'][0]['value']=='محمد احمد عبد الأمير'
    assert field['candidates'][0]['confidence'] is None


def test_zero_dot_does_not_come_from_tiny_guides_or_diacritics():
    from app.housing_handwriting import trailing_zero_dot
    digit=(20,10,25,65,400)
    dot=(51,28,10,9,62)
    assert trailing_zero_dot([digit,dot],[digit])==dot
    for mark in [(51,28,2,2,4), (51,0,10,9,62), (51,74,10,9,62), (11,28,10,9,62), (85,28,10,9,62)]:
        assert trailing_zero_dot([digit,mark],[digit]) is None


def test_merged_housing_labels_are_redetected_without_inventing_values(monkeypatch):
    image=np.full((600,900,3),255,np.uint8)
    merged=[dict(text='عنوان السكن 123',box=u.quad([80,410,870,500]),confidence=.8)]
    detected=[dict(text=text,box=u.quad([5,y,240,y+25]),confidence=.95)
              for text,y in [('مكتب معلومات',40),('اسم رب الاسرة',105),('عنوان السكن',170),('رقم الاستمارة',235)]]
    monkeypatch.setattr(f.arabic_ocr,'read',lambda image:detected)
    regions=f.housing_regions(image,merged,'front')
    assert {r['key'] for r in regions}=={'information_office','name','address','form_number'}
    assert all(max(p[0] for p in r['box'])<650 for r in regions)
    assert all('value' not in r for r in regions)


def test_unique_prefix_spelling_is_a_choice_and_ambiguous_names_are_left_alone():
    from app.housing_names import split_near_names
    assert split_near_names('محمدسقيد')==['محمد','سعيد']
    assert split_near_names('محمدعيد') is None
    assert split_near_names('محمدسعيد') is None
    value='محمد سقيد عبد الجبار'
    field=u.field('name',value,status='approximate',candidates=[{'value':value}])
    add_name_suggestions(field)
    assert field['value']==value and field['candidates'][0]['value']=='محمد سعيد عبد الجبار'
