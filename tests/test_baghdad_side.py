"""Baghdad mahalla parity (even = Rusafa, odd = Karkh) is a consistency check, never a correction."""
from app import understanding as u
from app.iraqi_addresses import check_baghdad_side


def housing(mahalla, office, **extra):
    return {'mahalla_number': u.field('mahalla_number', mahalla, .8, None, 'eastern_digit_model', 'approximate', **extra),
            'information_office': u.field('information_office', office, .8, None, 'housing_label_line', 'approximate')}


def test_consistent_office_and_mahalla_pass():
    fields = housing('673', 'الغزالية')
    check_baghdad_side(fields)
    assert fields['mahalla_number']['status'] == 'approximate'
    assert fields['mahalla_number']['baghdad_side'] == {'office': 'الكرخ', 'mahalla': 'الكرخ', 'consistent': True}


def test_contradiction_flags_but_never_changes_the_digits():
    candidates = [{'value': '674', 'engine': 'eastern_digit_model'}, {'value': '673', 'engine': 'full_line_ocr'}]
    fields = housing('674', 'مكتب معلومات المنصور', candidates=candidates)
    check_baghdad_side(fields)
    m = fields['mahalla_number']
    assert m['value'] == '674' and m['status'] == 'conflict' and 'الكرخ' in m['note']
    assert [c['value'] for c in m['candidates']] == ['673', '674']  # the reading that fits the office is suggested first


def test_unknown_office_manual_value_or_circular_suggestion_do_nothing():
    for fields in (housing('674', 'الزهور'), housing('674', ''),
                   {**housing('674', ''), 'information_office': u.field('information_office', '', None, None, 'x', 'unreadable',
                                                                         candidates=[{'value': 'الغزالية', 'engine': 'local_geography'}])}):
        check_baghdad_side(fields)
        assert fields['mahalla_number']['status'] == 'approximate' and 'baghdad_side' not in fields['mahalla_number']
    manual = housing('674', 'المنصور')
    manual['mahalla_number'].update(method='manual', status='manual')
    check_baghdad_side(manual)
    assert manual['mahalla_number']['status'] == 'manual'


def test_listed_mahalla_suggests_its_area_but_fills_nothing():
    from app.iraqi_addresses import suggest_mahalla_area, mahalla_area
    fields = housing('215', '')
    suggest_mahalla_area(fields)
    hood = fields['neighborhood']
    assert hood['value'] == '' and hood['candidates'][0]['value'].startswith('الصالحية')
    assert fields['mahalla_number']['area_hint']['side'] == 'الكرخ' and fields['mahalla_number']['value'] == '215'
    assert mahalla_area('850') and mahalla_area('673') is None  # Sadr City range; Ghazaliya is not in the owner table
    unlisted = housing('673', '')
    suggest_mahalla_area(unlisted)
    assert 'neighborhood' not in unlisted
