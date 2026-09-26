from app.mrz import check_digit
from app.vision import extract_fields

def test_bad_birth_checksum_does_not_get_promoted_to_checked_field():
    a='IDIRQ'+'A12345678'+check_digit('A12345678')+'<'*15
    wrong=str((int(check_digit('900101'))+1)%10)
    b='900101'+wrong+'M'+'300101'+check_digit('300101')+'IRQ'+'<'*11
    b+=check_digit(a[5:30]+b[:7]+b[8:15]+b[18:29])
    c='SAMPLE<<TEST'.ljust(30,'<')
    fields=extract_fields([{'text':text,'confidence':.9} for text in [a,b,c]],'national_id')
    keys={f['key'] for f in fields}
    assert 'document_number' in keys
    assert 'expiry_yymmdd' in keys
    assert 'birth_yymmdd' not in keys
