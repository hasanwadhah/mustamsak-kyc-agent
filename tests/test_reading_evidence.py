"""Reading fixes and the independent evidence that may lift a field's confidence.

Every rule here either parses what the image shows more carefully or records that a
second, independent source agrees. None of them changes or completes a value.
"""
import numpy as np

from app import focused_fields, kyc, understanding


def f(key, value, confidence=.85, status='uncertain', **extra):
    return {'key': key, 'value': value, 'confidence': confidence, 'status': status, 'method': 'label_neighbors', **extra}


# ---------------------------------------------------------------- parsing what was read
def test_reversed_date_echo_does_not_borrow_the_year():
    assert [r['value'] for r in focused_fields.date_readings('09/08/ 2028/09/08')] == ['2028/09/08']
    assert [r['value'] for r in focused_fields.date_readings('08/09/2028')] == ['2028/09/08']


def test_stray_digit_fragment_is_not_glued_to_a_number():
    assert understanding.valid_value('tax_number', '79 8252371709') == '8252371709'
    assert understanding.valid_value('license_number', 'BL-93262 019') == 'BL-93262'


def test_letter_prefixes_and_even_splits_stay_joined():
    assert understanding.valid_value('document_number', 'AV 9293334') == 'AV9293334'
    assert understanding.valid_value('license_number', 'BL 93262') == 'BL93262'
    # Neither part dominates, so this is one number split by the OCR, not a stray fragment.
    assert understanding.valid_value('tax_number', '8252 371709') == '8252371709'


def test_persian_letters_compare_equal_to_arabic_ones():
    assert kyc.compare_names('أمنة مصطفی رائد الكعبي', 'آمنة مصطفى رائد الكعبي')[0] == 'pass'


# ---------------------------------------------------------------- independent evidence
def test_mrz_confirmed_date_is_not_capped_as_approximate():
    check = {'matches': True, 'yymmdd': '841007'}
    confirmed = f('birth_date', '1984/10/07', status='approximate', approximate=True, date_precision='full',
                  raw_text='1984/10/07', mrz_date_check=check)
    assert kyc.raw_confidence(confirmed) == (.97, 'checksum')
    alone = dict(confirmed, mrz_date_check=None)
    assert kyc.raw_confidence(alone)[0] == .60


def test_mrz_does_not_rescue_a_conflict():
    conflict = f('birth_date', '1984/10/07', status='conflict', date_precision='full', raw_text='1984/10/07',
                 mrz_date_check={'matches': True})
    assert kyc.raw_confidence(conflict)[0] <= .45


def test_two_engines_agreeing_lift_an_uncertain_reading():
    assert kyc.raw_confidence(f('surname', 'الزبيدي', raw_text='الزبيدي'))[0] == .80
    assert kyc.raw_confidence(f('surname', 'الزبيدي', raw_text='الزبيدي', engines_agree=True))[0] == .95
    # A recorded disagreement always wins over agreement.
    assert kyc.raw_confidence(f('surname', 'الزبيدي', status='conflict', engines_agree=True))[0] <= .45


def test_a_set_aside_fragment_keeps_the_number_for_a_person_unless_the_second_engine_saw_only_it():
    number = f('tax_number', '8252371709', confidence=.97, status='read', raw_text='79 8252371709')
    assert kyc.raw_confidence(number)[0] == .80
    assert kyc.raw_confidence(dict(number, engines_agree=True))[0] == .80
    assert kyc.raw_confidence(dict(number, engines_agree=True, second_reading_clean=True))[0] == .97


def test_second_opinion_values_by_field_shape():
    assert understanding.second_opinion_values('tax_number', '1071802221 الرقم الضريبي') == {'1071802221'}
    assert understanding.second_opinion_values('expiry_date', '2026/12/21 تاريخ النفاذ') == {'2026/12/21'}
    # A lookalike digit in the letter prefix is only tolerated when comparing.
    assert 'BL-12321' in understanding.second_opinion_values('license_number', '8L-12321 رقم الإجازة')


def test_second_opinion_marks_only_exact_agreement(monkeypatch):
    # Rows are re-read in SECOND_OPINION_KEYS order: tax number, then expiry date.
    answers = iter([[(None, '1071802221', .9)], [(None, '2026/12/21 تاريخ النفاذ', .9)]])

    class Reader:
        def readtext(self, image, **_):
            return next(answers)
    monkeypatch.setattr('app.vision.reader', lambda: Reader())
    monkeypatch.setattr('app.vision.ocr_available', lambda: True)
    box = [[10, 10], [300, 10], [300, 40], [10, 40]]
    fields = {'expiry_date': f('expiry_date', '2026/12/21', box=box), 'tax_number': f('tax_number', '1071802222', box=box)}
    understanding.second_opinion(np.full((200, 400, 3), 255, np.uint8), fields)
    assert fields['expiry_date'].get('engines_agree') and fields['expiry_date'].get('second_reading_clean')
    assert not fields['tax_number'].get('engines_agree')
    assert fields['tax_number']['value'] == '1071802222'  # never changed


def test_a_name_confirmed_by_another_document_confirms_the_matching_name_parts(monkeypatch):
    from datetime import date
    from app import storage
    monkeypatch.setattr(kyc, 'calibration', lambda: None)
    part = lambda key, value, **kw: dict(f(key, value, confidence=.97, status='read', raw_text=value), **kw)
    front = {'id': storage.uid(), 'kind': 'national_id', 'side': 'front', 'capture': [], 'fields': [
        part('name', 'رائد طارق حسن العبيدي', status='conflict'), part('first_name', 'رائد', status='conflict'),
        part('father_name', 'طارق'), part('grandfather_name', 'حسن'), part('surname', 'العبيدي', status='conflict')]}
    licence = {'id': storage.uid(), 'kind': 'business_license', 'side': 'page', 'capture': [],
               'fields': [part('name', 'رائد طارق حسن')]}
    result = kyc.assess_documents([front, licence], 'individual', .9, date(2026, 9, 23))
    got = {x['key']: x for x in next(d for d in result['documents'] if d['id'] == front['id'])['fields']}
    # The triple name on the licence confirms the first three parts, not the surname it does not contain.
    assert got['first_name']['basis'] == 'corroborated' and got['first_name']['confidence'] > .9
    assert got['surname']['basis'] != 'corroborated' and got['surname']['confidence'] < .9
    assert got['first_name']['value'] == 'رائد'  # evidence only; values never change


# ---------------------------------------------------------------- recovering what the first pass missed
def test_page_line_inside_the_field_box_fills_a_failed_date_crop():
    region = {'key': 'birth_date', 'box': [[285, 262], [674, 262], [674, 315], [285, 315]], 'method': 'adaptive_column'}
    lines = [{'text': '1966/11/12', 'confidence': 1.0, 'box': [[420, 275], [600, 275], [600, 300], [420, 300]]},
             {'text': '2019/01/31', 'confidence': 1.0, 'box': [[420, 110], [600, 110], [600, 140], [420, 140]]}]
    result = {}
    focused_fields.page_line_dates(result, [region], lines)
    assert result['birth_date']['value'] == '1966/11/12'
    assert result['birth_date']['method'] == 'page_line_in_field'


def test_page_line_is_ignored_when_the_box_holds_two_different_dates():
    region = {'key': 'birth_date', 'box': [[0, 0], [700, 0], [700, 60], [0, 60]], 'method': 'adaptive_column'}
    lines = [{'text': '1966/11/12', 'confidence': 1.0, 'box': [[10, 10], [200, 10], [200, 40], [10, 40]]},
             {'text': '1967/11/12', 'confidence': 1.0, 'box': [[300, 10], [500, 10], [500, 40], [300, 40]]}]
    result = {}
    focused_fields.page_line_dates(result, [region], lines)
    assert 'birth_date' not in result
