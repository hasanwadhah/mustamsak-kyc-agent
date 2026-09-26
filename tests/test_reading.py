import numpy as np
from app import arabic_ocr, understanding, vision
from app.textmatch import contains_phrase, find_label


def test_numbers_from_the_english_model_are_added_to_arabic_lines():
    line = arabic_ocr.merge_readings({'text': 'رقم الإجازة', 'confidence': .94}, {'text': 'BL-93262 :09', 'confidence': .91})
    assert line['text'] == 'رقم الإجازة BL-93262' and line['merged_tokens'] == ['BL-93262'] and line['confidence'] == .91
    date = arabic_ocr.merge_readings({'text': 'تاريخ النفاذ', 'confidence': .8}, {'text': '2028/11/27 :', 'confidence': .92})
    assert date['text'].endswith('2028/11/27')


def test_arabic_read_as_latin_letters_is_never_merged():
    line = arabic_ocr.merge_readings({'text': 'الاسم', 'confidence': .99}, {'text': 'AWLL', 'confidence': .9})
    assert line['text'] == 'الاسم' and 'merged_tokens' not in line
    # Noise that happens to contain digits is not a value shape either.
    for noise in ('06LWOLOAW', '01W1 :', 'L0L'):
        merged = arabic_ocr.merge_readings({'text': 'سعد عباس عباس', 'confidence': .9}, {'text': noise, 'confidence': .9})
        assert merged['text'] == 'سعد عباس عباس', noise
    assert arabic_ocr.latin_tokens('IDIRQAB12345671<<<< 2028/11/27 BL-9326 AB1234567') == \
        ['IDIRQAB12345671<<<<', '2028/11/27', 'BL-9326', 'AB1234567']


def test_latin_only_boxes_use_the_english_reading_and_digits_are_not_duplicated():
    mrz = arabic_ocr.merge_readings({'text': 'ا', 'confidence': .4}, {'text': 'IDIRQAB12345671<<<<', 'confidence': .97})
    assert mrz['text'].startswith('IDIRQ') and mrz['engine'] == 'ppocr_v5_en'
    same = arabic_ocr.merge_readings({'text': 'الرقم ٢٠٢٤', 'confidence': .9}, {'text': '2024', 'confidence': .9})
    assert 'merged_tokens' not in same
    assert arabic_ocr.merge_readings({'text': '', 'confidence': .1}, {'text': 'x', 'confidence': .1}) is None


def test_labels_tolerate_ocr_slips_but_short_labels_stay_exact():
    assert find_label('رفم الاجازه BL-1', 'رقم الاجازه')[2] == 1
    assert find_label('الاسم التجاريشركه النور', 'الاسم التجاري')[:2] == (0, 13)
    assert find_label('الام ليلى', 'الاب') is None  # الأم must never be read as الأب
    assert find_label('تاريخ الولاده 1990/01/01', 'تاريخ الاصدار') is None
    assert contains_phrase('الرقمالضريبي 123', 'الرقم الضريبي')
    assert contains_phrase('الهيئه العامه للضراىب', 'الهيئه العامه للضرائب')
    assert not contains_phrase('البطاقه الوطنيه', 'البطاقه الضريبيه')


def test_generic_fields_read_glued_and_misspelled_labels():
    rows = ['اسم صاحب الإجازة محمد حسين علي', 'الاسم التجاريشركة النور للتجارة', 'رفم الإجازة BL-93262',
            'نوع الشاطمقاولات إنشائية', 'ناريخ الإصدار 2025/11/28', 'ناريخ النفاذ 2028/11/27']
    lines = [{'text': t, 'confidence': .9, 'box': [[900, y], [100, y], [100, y + 30], [900, y + 30]]} for y, t in zip(range(0, 600, 60), rows)]
    fields = {f['key']: f['value'] for f in understanding.extract(None, lines, 'business_license', 'page', [])}
    assert fields['license_number'] == 'BL-93262'
    assert fields['issue_date'] == '2025/11/28' and fields['expiry_date'] == '2028/11/27'
    assert fields['business_name'] == 'شركة النور للتجارة'
    assert fields['activity'] == 'مقاولات إنشائية'
    assert fields['name'] == 'محمد حسين علي'
    assert vision.classify(lines)['kind'] == 'business_license'


def test_national_front_reads_values_printed_apart_from_labels(monkeypatch):
    w, h = 1000, 631
    def box(x1, x2, cy):
        return [[x2, cy - 12], [x1, cy - 12], [x1, cy + 12], [x2, cy + 12]]
    labels = [('الاسم', .35), ('الأب', .42), ('الجد', .50), ('اللقب', .57), ('الأم', .65), ('الجنس', .80)]
    lines = [{'text': t, 'confidence': .99, 'box': box(.91 * w, .98 * w, y * h)} for t, y in labels]
    lines += [{'text': 'قيمة', 'confidence': .99, 'box': box(.68 * w, .75 * w, y * h)} for _, y in labels]
    regions = dict((k, b) for k, b, _ in understanding.template_regions(np.zeros((h, w, 3), np.uint8), lines, 'national_id', 'front'))
    assert regions['first_name'][0] < .70 * w < regions['first_name'][2]
    assert regions['father_name'][2] - regions['father_name'][0] > 8
