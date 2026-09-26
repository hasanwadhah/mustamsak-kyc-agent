from copy import deepcopy
from datetime import date
import pytest
from app import kyc, storage, understanding, vision

TODAY = date(2026, 9, 23)


@pytest.fixture(autouse=True)
def uncalibrated(monkeypatch):
    # Rules are tested independently of whichever calibration file is installed.
    monkeypatch.setattr(kyc, 'calibration', lambda: None)
    monkeypatch.setattr(kyc, 'policy', lambda: {'threshold': .9, 'expiry_warning_days': 30, 'minimum_age': 18})


def f(key, value, confidence=.97, status='read', **extra):
    return {'key': key, 'label': understanding.LABELS.get(key, key), 'value': value, 'confidence': confidence,
            'status': status, 'verified': False, 'method': 'field_crop', **extra}


def doc(kind, side, fields, **extra):
    return {'id': storage.uid(), 'kind': kind, 'side': side, 'fields': fields, 'image_id': storage.uid(),
            'capture': [], 'reviewed': False, **extra}


def id_front(name='محمد حسين علي الجبوري', serial='AB1234567', **kw):
    return doc('national_id', 'front', [f('name', name), f('national_number', '199012345678'), f('document_number', serial)], **kw)


def id_back(serial='AB1234567', birth='1990/01/15', expiry='2030/05/01'):
    return doc('national_id', 'back', [f('document_number', serial), f('birth_date', birth), f('expiry_date', expiry),
                                       f('issue_date', '2020/05/01')])


def license_(name='محمد حسين علي', business='شركة النور للتجارة', expiry='2027/12/31'):
    return doc('business_license', 'page', [f('name', name), f('business_name', business), f('license_number', 'BL-20411'),
                                            f('expiry_date', expiry)])


def tax(name='محمد حسين علي الجبوري', business='شركة النور للتجارة'):
    return doc('tax_card', 'page', [f('name', name), f('tax_number', '4455667788'), f('business_name', business)])


def codes(result):
    return {r['code'] for r in result['reasons'] if r['severity'] == 'block'}


def test_complete_consistent_merchant_case_passes():
    result = kyc.assess_documents([id_front(), id_back(), license_(), tax()], today=TODAY)
    assert result['profile'] == 'merchant'
    assert result['decision'] == 'pass', result['summary_en']
    assert all(c['status'] == 'pass' for c in result['cross_checks'])
    assert 'يمكن اعتماد' in result['summary'] and 'Passed' in result['summary_en']


def test_every_field_has_a_confidence_and_threshold_flag():
    result = kyc.assess_documents([id_front(), id_back()], today=TODAY)
    for d in result['documents']:
        for field in d['fields']:
            assert 0 <= field['confidence'] <= 1 and isinstance(field['below_threshold'], bool)


def test_low_confidence_critical_field_routes_to_human():
    front = id_front()
    front['fields'][1] = f('national_number', '199012345678', confidence=.71, status='uncertain')
    result = kyc.assess_documents([front, id_back()], today=TODAY)
    assert result['decision'] == 'review'
    reason = next(r for r in result['reasons'] if r['field_key'] == 'national_number')
    assert reason['code'] == 'low_confidence' and '90%' in reason['message'] and reason['doc_id'] == front['id']


def test_missing_field_stays_blank_and_input_is_never_modified():
    back = id_back()
    back['fields'] = [x for x in back['fields'] if x['key'] != 'birth_date']
    documents = [id_front(), back]
    before = deepcopy(documents)
    result = kyc.assess_documents(documents, today=TODAY)
    assert documents == before
    birth = next(x for d in result['documents'] for x in d['fields'] if x['key'] == 'birth_date')
    assert birth['value'] == '' and birth['confidence'] == 0 and 'field_missing' in codes(result)


def test_partial_or_approximate_values_never_pass():
    back = id_back()
    back['fields'][1] = f('birth_date', '??90/01/15', confidence=.99, status='approximate', date_precision='partial')
    result = kyc.assess_documents([id_front(), back], today=TODAY)
    birth = next(x for d in result['documents'] for x in d['fields'] if x['key'] == 'birth_date')
    assert birth['confidence'] <= .3 and result['decision'] == 'review'


def test_expired_document_is_flagged():
    result = kyc.assess_documents([id_front(), id_back(expiry='2025/01/01')], today=TODAY)
    assert 'expired' in codes(result) and result['decision'] == 'review'


def test_name_mismatch_across_documents_routes_to_human():
    result = kyc.assess_documents([id_front(), id_back(), license_(name='احمد كريم جاسم'), tax()], today=TODAY)
    check = next(c for c in result['cross_checks'] if c['code'] == 'name_match' and 'business' in c['label_en'])
    assert check['status'] == 'fail' and result['decision'] == 'review'


def test_triple_name_matches_quadruple_and_article_is_ignored():
    assert kyc.compare_names('محمد حسين علي الجبوري', 'محمد حسين علي')[0] == 'pass'
    assert kyc.compare_names('فاطمة عبد الله حسن', 'فاطمه عبدالله حسن')[0] == 'pass'
    assert kyc.compare_names('محمد حسين علي جبوري', 'محمد حسين علي الجبوري')[0] == 'pass'


def test_single_spelling_difference_is_a_review_not_a_pass():
    status, _, _ = kyc.compare_names('محمد حسين علي', 'محمد حسن علي')
    assert status == 'warn'
    result = kyc.assess_documents([id_front(), id_back(), license_(name='محمد حسن علي'), tax()], today=TODAY)
    assert result['decision'] == 'review'


def test_front_and_back_card_numbers_must_agree():
    result = kyc.assess_documents([id_front(serial='AB1234567'), id_back(serial='AB7654321')], today=TODAY)
    check = next(c for c in result['cross_checks'] if c['code'] == 'document_number_match')
    assert check['status'] == 'fail' and result['decision'] == 'review'


def test_required_documents_depend_on_profile():
    result = kyc.assess_documents([license_(), tax()], today=TODAY)
    identity = next(r for r in result['requirements'] if r['id'] == 'identity')
    assert result['profile'] == 'merchant' and not identity['satisfied'] and 'missing_document' in codes(result)
    individual = kyc.assess_documents([id_front(), id_back()], today=TODAY)
    assert individual['profile'] == 'individual' and individual['decision'] == 'pass'


def test_human_approved_value_is_trusted():
    front = id_front()
    front['fields'][1] = f('national_number', '199012345678', confidence=.4, status='manual', method='manual', verified=True)
    result = kyc.assess_documents([front, id_back()], today=TODAY)
    field = next(x for x in result['documents'][0]['fields'] if x['key'] == 'national_number')
    assert field['confidence'] == 1 and field['basis'] == 'human' and result['decision'] == 'pass'


def test_mrz_checksum_evidence_raises_confidence():
    back = id_back()
    back['fields'][0] = f('document_number', 'AB1234567', confidence=.82, status='read', pairing_eligible=True,
                          serial_location='mrz_first_line', mrz_checksum=True)
    raw, basis = kyc.raw_confidence(back['fields'][0])
    assert basis == 'checksum' and raw >= .97


def test_retake_grade_photo_lowers_confidence():
    front = id_front(capture=[{'code': 'glare', 'severity': 'retake', 'message': 'x', 'message_en': 'y'}])
    result = kyc.assess_documents([front, id_back()], today=TODAY)
    assert result['decision'] == 'review' and result['documents'][0]['retake']
    assert 'Ask for a new photo' in result['summary_en']


def test_format_and_chronology_checks():
    front = id_front()
    front['fields'][1] = f('national_number', '12345')
    back = id_back(birth='2021/01/01', expiry='2030/01/01')
    result = kyc.assess_documents([front, back], today=TODAY)
    assert {'format', 'chronology'} <= codes(result)


def test_identical_readings_on_two_documents_corroborate_each_other():
    front = id_front(name='محمد حسين علي الجبوري')
    front['fields'][0] = f('name', 'محمد حسين علي الجبوري', confidence=.8, status='uncertain')
    card = tax()
    card['fields'][0] = f('name', 'محمد حسين علي الجبوري', confidence=.8, status='uncertain')
    licence = license_()
    licence['fields'][0] = f('name', 'محمد حسين علي', confidence=.8, status='uncertain')
    result = kyc.assess_documents([front, id_back(), licence, card], today=TODAY)
    names = {d['kind']: x for d in result['documents'] for x in d['fields'] if x['key'] == 'name'}
    assert names['tax_card']['basis'] == 'corroborated' and names['tax_card']['confidence'] == pytest.approx(.96)
    assert names['national_id']['basis'] == 'corroborated' and names['business_license']['basis'] == 'corroborated'
    assert names['tax_card']['corroborated_by_en'].startswith('national ID')


def test_disagreeing_readings_are_not_corroborated():
    card = tax(name='احمد كريم جاسم الربيعي')
    card['fields'][0] = f('name', 'احمد كريم جاسم الربيعي', confidence=.8, status='uncertain')
    result = kyc.assess_documents([id_front(), id_back(), license_(), card], today=TODAY)
    name = next(x for d in result['documents'] if d['kind'] == 'tax_card' for x in d['fields'] if x['key'] == 'name')
    assert name['basis'] == 'ocr' and name['below_threshold'] and result['decision'] == 'review'


def test_calibration_table_is_monotonic_interpolation():
    table = {'points': [[0, .1], [.5, .4], [1, .95]]}
    assert kyc.calibrated(.25, 'ocr', table) == pytest.approx(.25)
    assert kyc.calibrated(.75, 'ocr', table) == pytest.approx(.675)
    assert kyc.calibrated(1.0, 'human', table) == 1.0


def test_pending_batch_has_no_decision():
    assert kyc.assess_batch({'status': 'processing', 'documents': []}, today=TODAY)['decision'] == 'pending'


def test_new_merchant_document_types_are_classified_and_read():
    lines = [{'text': t, 'confidence': .96, 'box': [[900, y], [100, y], [100, y + 30], [900, y + 30]]}
             for y, t in [(10, 'الهيئة العامة للضرائب'), (60, 'البطاقة الضريبية'), (110, 'اسم المكلف : محمد حسين علي'),
                          (160, 'الرقم الضريبي : 4455667788'), (210, 'تاريخ النفاذ : 2028/01/31')]]
    result = vision.classify(lines)
    assert result['kind'] == 'tax_card' and result['side'] == 'page'
    fields = {x['key']: x for x in understanding.extract(None, lines, 'tax_card', 'page', [])}
    assert fields['tax_number']['value'] == '4455667788'
    assert fields['name']['value'] == 'محمد حسين علي'
    assert fields['expiry_date']['value'] == '2028/01/31'
    assert fields['business_name']['value'] == ''  # Absent stays visible and blank.
    license_lines = [dict(lines[0], text='اجازة ممارسة النشاط التجاري')]
    assert vision.classify(license_lines)['kind'] == 'business_license'
