import random
from app import national_serial as n
from app.grouping import group_documents,regroup_national
from app.mrz import check_digit

def line(text,x1=10,y1=420,x2=260,y2=455,confidence=.98):
    return {'text':text,'confidence':confidence,'box':n.quad([x1,y1,x2,y2])}

def back_line(number,valid=True):
    digit=check_digit(number)
    if not valid:digit=str((int(digit)+1)%10)
    return line('IDIRQ'+number+digit+'123456789012<<<',20,380,830,420)

def doc(identifier,number,side,source='mixed-page'):
    lines=[line(number)] if side=='front' else [back_line(number)]
    return {'id':identifier,'kind':'national_id','side':side,'source_id':source,'width':856,'height':540,
            'fields':[n.extract(lines,side,width=856,height=540)]}

def test_back_first_line_suffices_even_if_name_and_dates_unreadable():
    number='AB1234567';f=n.extract([back_line(number)],'back',width=856,height=540)
    assert f['value']==number and f['mrz_checksum'] and f['pairing_eligible']
    assert len(f['value'])==9 # The following check digit is excluded.
    assert n.mrz_serial('I<IRQ'+number+check_digit(number))['value']==number

def test_wrong_checksum_and_unrelated_numbers_are_not_pairing_keys():
    assert not n.extract([back_line('AB1234567',False)],'back',width=856,height=540)['pairing_eligible']
    assert not n.extract([line('123456789012')],'front',width=856,height=540)['pairing_eligible']
    assert not n.extract([line('AB1234567',400,30,650,65)],'front',width=856,height=540)['pairing_eligible']
    assert n.mrz_serial('IDIRQAB1234567') is None

def test_ocr_whitespace_is_normalized_but_similar_characters_are_not_guessed():
    f=n.extract([line('ab ١٢٣٤٥٦٧')],'front',width=856,height=540)
    assert f['value']=='AB1234567' and f['pairing_eligible']
    assert not n.valid_serial('AB123O567')

def test_multiple_readings_and_duplicate_faces_stay_unresolved():
    f=n.extract([line('AB1234567'),line('AB1234568')],'front',width=856,height=540)
    assert not f['pairing_eligible'] and f['status']=='conflict'
    ds=[doc('f','AB1234567','front'),doc('b','AB1234567','back'),doc('b2','AB1234567','back')]
    group_documents(ds)
    assert len({d['group'] for d in ds})==3
    assert all(d['pairing']['status']=='ambiguous' for d in ds)

def test_three_shuffled_people_pair_by_location_and_number():
    ds=[doc(number+side,number,side) for number in ['AB1234567','CD7654321','EF0123456'] for side in ['front','back']]
    random.Random(31).shuffle(ds);group_documents(ds)
    assert len({d['group'] for d in ds})==3
    for number in ['AB1234567','CD7654321','EF0123456']:
        pair=[d for d in ds if d['fields'][0]['value']==number]
        assert pair[0]['group']==pair[1]['group']
        assert all(d['pairing']['status']=='matched' for d in pair)

def test_bad_checksum_never_falls_back_to_same_page_pairing():
    f=doc('f','AB1234567','front');b=doc('b','AB1234567','back')
    b['fields'][0]=n.extract([back_line('AB1234567',False)],'back',width=856,height=540)
    group_documents([f,b]);assert f['group']!=b['group']

def test_regroup_preserves_manual_and_reviewed_groups_and_is_repeatable():
    f,b=doc('f','AB1234567','front'),doc('b','AB1234567','back')
    f.update(group='Chosen',group_method='manual');b.update(group='Chosen')
    a,c=doc('a','CD7654321','front'),doc('c','CD7654321','back')
    ds=[f,b,a,c];regroup_national(ds)
    assert f['group']==b['group']=='Chosen'
    first=[d['group'] for d in ds];regroup_national(ds)
    assert first==[d['group'] for d in ds]

def test_declared_field_without_location_is_not_enough_to_merge():
    f=doc('f','AB1234567','front');b=doc('b','AB1234567','back')
    f['fields']=[{'key':'document_number','value':'AB1234567'}]
    group_documents([f,b]);assert f['group']!=b['group']


def test_changing_a_serial_invalidates_both_faces_pair_evidence():
    from app.grouping import invalidate_pairing
    f,b=doc('f','AB1234567','front'),doc('b','AB1234567','back')
    group_documents([f,b]);invalidate_pairing([f,b],'f')
    assert f['pairing']['status']==b['pairing']['status']=='needs_recheck'
