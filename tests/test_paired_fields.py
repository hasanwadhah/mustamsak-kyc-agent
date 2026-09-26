from copy import deepcopy
from app.paired_fields import reconcile

def pair():
    front={'id':'f','kind':'national_id','side':'front','image_id':'fimg','fields':[{'key':'document_number','value':'AB1234567','pairing_eligible':True,'serial_location':'below_portrait','mrz_checksum':True},{'key':'sex','value':'','verified':False}]}
    back={'id':'b','kind':'national_id','side':'back','image_id':'bimg','fields':[{'key':'document_number','value':'AB1234567','pairing_eligible':True,'serial_location':'mrz_first_line','mrz_checksum':True},{'key':'sex','value':'أنثى','method':'mrz_checked_syntax','confidence':.8,'box':[[0,0],[50,0],[50,20],[0,20]],'verified':False}]}
    return front,back

def test_missing_front_gender_is_not_filled_from_back():
    front,back=pair();reconcile([front,back]);field=front['fields'][1]
    assert field['value']=='' and 'source_image_id' not in field
    assert field['candidates'][0]['value']=='أنثى' and not field['verified']

def test_no_matching_by_upload_or_group_or_ambiguous_number():
    front,back=pair();back['fields'][0]['value']='AB7654321';reconcile([front,back])
    assert front['fields'][1]['value']==''
    front,back=pair();reconcile([front,back,deepcopy(back)])
    assert front['fields'][1]['value']==''

def test_manual_sex_is_preserved_and_conflicting_ocr_is_flagged():
    front,back=pair();front['fields'][1].update(value='ذكر',method='manual')
    reconcile([front,back]);assert front['fields'][1]['value']=='ذكر' and 'status' not in front['fields'][1]
    front['fields'][1]['method']='field_crop';reconcile([front,back])
    assert front['fields'][1]['value']=='ذكر' and front['fields'][1]['status']=='conflict'
    assert front['fields'][1]['candidates'][0]['value']=='أنثى'

def test_unchecked_mrz_or_manual_back_does_not_propagate():
    front,back=pair();back['fields'][1]['method']='manual';reconcile([front,back])
    assert front['fields'][1]['value']==''



def test_stale_back_ocr_and_reviewed_front_are_not_reinterpreted():
    front,back=pair();back['field_image_id']='old_image'
    reconcile([front,back]);assert 'candidates' not in front['fields'][1]
    front,back=pair();front['reviewed']=True;before=deepcopy(front)
    reconcile([front,back]);assert front==before


def test_checked_mrz_without_back_gender_field_is_only_a_comparison():
    from app.mrz import check_digit
    front,back=pair();back['fields']=back['fields'][:1]
    a='IDIRQ'+'AB1234567'+check_digit('AB1234567')+'<'*15
    b='900101'+check_digit('900101')+'F'+'300101'+check_digit('300101')+'IRQ'+'<'*11
    b+=check_digit(a[5:30]+b[:7]+b[8:15]+b[18:29])
    back['ocr']=[{'text':t} for t in [a,b,'SAMPLE<<TEST'.ljust(30,'<')]]
    reconcile([front,back])
    assert front['fields'][1]['value']=='' and front['fields'][1]['candidates'][0]['value']=='أنثى'
    assert not any(f['key']=='sex' for f in back['fields'])
