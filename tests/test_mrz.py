from app.mrz import check_digit,parse

def test_icao_td1_checks_and_tampering():
    a='IDIRQ'+'A12345678'+check_digit('A12345678')+'<'*15
    b='900101'+check_digit('900101')+'M'+'300101'+check_digit('300101')+'IRQ'+'<'*11
    b+=check_digit(a[5:30]+b[:7]+b[8:15]+b[18:29])
    c='SAMPLE<<TEST'.ljust(30,'<')
    result=parse([a,b,c])
    assert result['valid'] and result['document_number']=='A12345678'
    bad=a[:6]+'9'+a[7:]
    assert parse([bad,b,c])['valid'] is False

def test_never_complete_truncated_mrz():
    assert parse(['IDIRQA12345','900101','SAMPLE']) is None
