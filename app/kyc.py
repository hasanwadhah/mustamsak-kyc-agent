"""KYC decision layer: confidence per field, validation, cross-document checks, routing.

This module only READS extracted fields. It never writes, completes or
"corrects" a value: a field that was not read stays blank and is routed to a
person. The decision is either `pass` (every critical field confident, valid
and consistent across documents) or `review` with a short reviewer summary
explaining exactly what to check and why.

Out of scope by design: face matching, liveness and forgery detection.
"""
from copy import deepcopy
from datetime import date, datetime
from difflib import SequenceMatcher
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = ROOT / 'models' / 'kyc_calibration.json'
POLICY_PATH = ROOT / 'models' / 'kyc_policy.json'
DEFAULT_THRESHOLD = .90

SIDE_LABELS = {'front': ('الوجه الأمامي', 'front'), 'back': ('الوجه الخلفي', 'back'),
               'page': ('صفحة', 'page'), 'unknown': ('وجه غير محدد', 'unknown side')}
KIND_EN = {'national_id': 'national ID card', 'passport': 'passport', 'driving': 'driving licence',
           'business_license': 'business licence', 'tax_card': 'tax card', 'housing': 'housing card',
           'civil_id': 'civil status ID', 'nationality': 'nationality certificate', 'residence': 'residence card',
           'unknown': 'unidentified document'}
FIELD_EN = {'name': 'full name', 'national_number': 'national number', 'document_number': 'card number',
            'birth_date': 'date of birth', 'issue_date': 'issue date', 'expiry_date': 'expiry date',
            'business_name': 'business name', 'license_number': 'licence number', 'tax_number': 'tax number',
            'address': 'address', 'activity': 'business activity', 'sex': 'sex'}

# Fields that must be confident for an automatic pass, per document face.
CRITICAL = {
    ('national_id', 'front'): ['name', 'national_number', 'document_number'],
    ('national_id', 'back'): ['document_number', 'birth_date', 'expiry_date'],
    ('passport', 'page'): ['name', 'document_number', 'birth_date', 'expiry_date'],
    ('driving', 'front'): ['name', 'document_number', 'expiry_date'],
    ('driving', 'page'): ['name', 'document_number', 'expiry_date'],
    ('business_license', 'page'): ['name', 'business_name', 'license_number', 'expiry_date'],
    ('tax_card', 'page'): ['name', 'tax_number'],
}
# What a complete case must contain. Any one option satisfies a requirement.
REQUIREMENTS = {
    'identity': {'label': ('مستمسك هوية (الموحدة بوجهيها أو جواز السفر)', 'identity document (national ID both sides, or passport)'),
                 'options': [[('national_id', 'front'), ('national_id', 'back')], [('passport', 'page')]]},
    'business_license': {'label': ('إجازة ممارسة النشاط التجاري', 'business licence'), 'options': [[('business_license', 'page')]]},
    'tax_card': {'label': ('البطاقة الضريبية', 'tax card'), 'options': [[('tax_card', 'page')]]},
}
PROFILES = {'individual': ['identity'], 'merchant': ['identity', 'business_license', 'tax_card']}
FORMATS = {
    'national_number': (r'\d{12}', ('الرقم الوطني يجب أن يتكون من 12 رقمًا', 'national number must be 12 digits')),
    'tax_number': (r'\d{6,15}', ('الرقم الضريبي يجب أن يتكون من 6 إلى 15 رقمًا', 'tax number must be 6-15 digits')),
    'license_number': (r'[A-Z0-9/-]{3,20}', ('صيغة رقم الإجازة غير متوقعة', 'unexpected licence number format')),
}
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
NAME_KEYS = {'name', 'first_name', 'father_name', 'grandfather_name', 'surname', 'mother_name', 'maternal_grandfather'}


# ---------------------------------------------------------------- policy

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def policy():
    data = load_json(POLICY_PATH) or {}
    threshold = float(os.environ.get('MUSTAMSAK_KYC_THRESHOLD', data.get('threshold', DEFAULT_THRESHOLD)))
    return {'threshold': min(.999, max(.5, threshold)), 'expiry_warning_days': int(data.get('expiry_warning_days', 30)),
            'minimum_age': int(data.get('minimum_age', 18))}


def calibration():
    data = load_json(CALIBRATION_PATH)
    if not data or len(data.get('points', [])) < 2:
        return None
    return data


# ---------------------------------------------------------------- confidence

def human_approved(f):
    return bool(f.get('verified')) or f.get('method') == 'manual' or f.get('status') == 'manual'


def raw_confidence(f, capture_issues=()):
    """Combine OCR score, extraction status and independent evidence into one score.

    Returns (score, basis). This is *pre-calibration*; see calibrated().
    """
    value = str(f.get('value') or '').strip()
    if human_approved(f) and value:
        return 1.0, 'human'
    if not value:
        return 0.0, 'missing'
    status = f.get('status') or 'uncertain'
    if status in ('unreadable', 'missing'):
        return 0.0, 'unreadable'
    score = f.get('confidence')
    score = float(score) if isinstance(score, (int, float)) else .5
    basis = 'ocr'
    # Independent arithmetic evidence: MRZ check digits agree with the reading.
    if f.get('key') == 'document_number' and f.get('pairing_eligible') and (
            f.get('serial_location') == 'below_portrait' or f.get('mrz_checksum')):
        score, basis = max(score, .97), 'checksum'
    # Day, month and two-digit year agree with the MRZ date that passed its own check digit: the
    # "approximate" crop reading is then independently confirmed (a conflict still caps it below).
    mrz_confirmed = (f.get('mrz_date_check') or {}).get('matches') is True and f.get('date_precision', 'full') == 'full'
    if mrz_confirmed:
        score, basis = max(score, .97), 'checksum'
    if f.get('method') == 'text_pattern' and 'MRZ' in str(f.get('label', '')):
        score, basis = max(score, .95), 'checksum'
    # Two independent OCR engines produced the same letters (understanding.compare_ambiguous_names).
    engines_agree = bool(f.get('engines_agree')) and status in ('read', 'uncertain')
    if engines_agree:
        score = max(score, .95)
    caps = {'read': 1.0, 'uncertain': 1.0 if engines_agree else .80, 'approximate': .97 if mrz_confirmed else .60, 'conflict': .45}
    score = min(score, caps.get(status, .80))
    if f.get('approximate') and not mrz_confirmed:
        score = min(score, .60)
    if f.get('date_precision') == 'partial' or '??' in value:
        score = min(score, .30)
    # Plausibility of what was read (never used to change the value):
    raw_text = str(f.get('raw_text') or '').translate(DIGITS)
    key = f.get('key', '')
    # These two checks catch a lost or stray digit, unless the second engine read the row with exactly
    # the value's digits and nothing else (understanding.second_opinion).
    echo_ruled_out = engines_agree and bool(f.get('second_reading_clean'))
    if key.endswith('_date') and re.search(r'(?<![\d])\d(?![\d])', raw_text) and not echo_ruled_out:
        score = min(score, .80)  # Printed dates are zero-padded; a one-digit part suggests a lost digit.
    if key in FORMATS and raw_text and re.sub(r'[\s:：;،|.]', '', raw_text).upper() != value.replace(' ', '').upper() \
            and not echo_ruled_out:
        score = min(score, .80)  # A fragment was set aside from the line; a person confirms which part is the number.
    if key in NAME_KEYS:
        tokens = value.split()
        if any(len(t) <= 2 for t in tokens):
            score = min(score, .60)  # Arabic name parts are almost never one or two letters.
        if re.search(r'[A-Za-z0-9]', value):
            score = min(score, .40)  # Latin letters or digits inside an Arabic name.
    severities = {i.get('severity') for i in capture_issues}
    if 'retake' in severities:
        score *= .85
    elif 'warn' in severities:
        score *= .95
    return round(max(0.0, min(1.0, score)), 4), basis


def calibrated(score, basis, table=None):
    """Map a raw score to an empirical probability of being correct.

    The table is fitted by scripts/evaluate_kyc.py (isotonic regression on a
    tuning split) and reported on a held-out split. Human-approved values are
    not model outputs and are never recalibrated.
    """
    if basis in ('human', 'missing', 'unreadable') or not table:
        return score
    points = sorted(table['points'])
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    if score <= xs[0]:
        return round(ys[0], 4)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if score <= x1:
            t = 0 if x1 == x0 else (score - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 4)
    return round(ys[-1], 4)


# ---------------------------------------------------------------- validation

def parse_date(value):
    try:
        return datetime.strptime(str(value).translate(DIGITS).strip(), '%Y/%m/%d').date()
    except ValueError:
        return None


def finding(code, severity, ar, en):
    return {'code': code, 'severity': severity, 'message': ar, 'message_en': en}


def validate_field(f, kind, today, rules):
    """Format and date checks on one field. Never alters the value."""
    key, value = f.get('key'), str(f.get('value') or '').strip()
    if not value:
        return []
    out = []
    compact = re.sub(r'\s', '', value.translate(DIGITS)).upper()
    if key in FORMATS and not re.fullmatch(FORMATS[key][0], compact):
        out.append(finding('format', 'block', *FORMATS[key][1]))
    if key == 'document_number' and kind == 'national_id':
        from .national_serial import valid_serial
        if not valid_serial(compact):
            out.append(finding('format', 'block', 'صيغة رقم البطاقة غير متوقعة (حرف أو حرفان ثم أرقام، 9 خانات)',
                               'unexpected card number format (1-2 letters then digits, 9 characters)'))
    if key.endswith('_date'):
        d = parse_date(value)
        if d is None:
            out.append(finding('date_incomplete', 'block', 'التاريخ غير مكتمل أو غير صالح؛ لم يُفترض أي رقم مفقود',
                               'date is incomplete or invalid; no missing digit was assumed'))
        elif key == 'expiry_date':
            if d < today:
                out.append(finding('expired', 'block', f'المستمسك منتهي الصلاحية منذ {value}', f'document expired on {value}'))
            elif (d - today).days <= rules['expiry_warning_days']:
                out.append(finding('expiring_soon', 'warn', f'تنتهي الصلاحية قريبًا ({value})', f'document expires soon ({value})'))
        elif key in ('birth_date', 'issue_date') and d > today:
            out.append(finding('future_date', 'block', f'التاريخ في المستقبل ({value})', f'date is in the future ({value})'))
        elif key == 'birth_date':
            age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
            if age < rules['minimum_age']:
                out.append(finding('minor', 'warn', f'العمر {age} سنة أقل من {rules["minimum_age"]}',
                                   f'age {age} is below {rules["minimum_age"]}'))
    check = f.get('mrz_date_check') or {}
    if check.get('matches') is False:
        out.append(finding('mrz_mismatch', 'block', 'التاريخ المطبوع لا يطابق الشريط الآلي ذي رقم التحقق',
                           'printed date does not match the check-digit-verified MRZ'))
    return out


def chronology(fields):
    dates = {k: parse_date(fields[k]['value']) for k in ('birth_date', 'issue_date', 'expiry_date') if fields.get(k, {}).get('value')}
    out = []
    for a, b in [('birth_date', 'issue_date'), ('issue_date', 'expiry_date'), ('birth_date', 'expiry_date')]:
        if dates.get(a) and dates.get(b) and dates[a] >= dates[b]:
            out.append(finding('chronology', 'block', 'تسلسل التواريخ غير منطقي (الولادة ثم الإصدار ثم النفاذ)',
                               'dates are out of order (birth, then issue, then expiry)'))
            break
    return out


# ---------------------------------------------------------------- cross-document

def name_tokens(value):
    from .focused_fields import normalize
    from .people import normalize_name
    tokens = normalize_name(normalize(value)).split()
    # Drop the definite article on surnames: الجبوري ~ جبوري.
    return [t[2:] if t.startswith('ال') and len(t) > 4 else t for t in tokens]


def compare_names(a, b):
    """Return (status, note_ar, note_en) for two person names.

    Iraqi documents mix triple (الاسم الثلاثي) and quadruple names, so a shorter
    name that is an exact prefix of the longer one (>= 3 parts) is consistent.
    """
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 'unverifiable', 'اسم غير مقروء', 'name not readable'
    if ta == tb:
        return 'pass', 'الاسمان متطابقان', 'names match'
    short, long = sorted([ta, tb], key=len)
    if len(short) >= 3 and long[:len(short)] == short:
        return 'pass', 'تطابق الاسم الثلاثي مع الاسم الأطول', 'triple name matches the longer name'
    pairs = list(zip(short, long))
    differences = [(x, y) for x, y in pairs if x != y]
    if len(short) >= 3 and len(differences) == 1 and SequenceMatcher(None, *differences[0]).ratio() >= .7:
        return 'warn', f'اختلاف تهجئة في جزء واحد: «{differences[0][0]}» مقابل «{differences[0][1]}»', \
               'one name part differs in spelling'
    return 'fail', 'الاسمان مختلفان', 'names differ'


def same_value(key, a, b):
    if key.endswith('_date'):
        return parse_date(a) is not None and parse_date(a) == parse_date(b)
    clean = lambda v: re.sub(r'[\s/-]', '', str(v).translate(DIGITS)).upper()
    if key == 'business_name':
        return name_tokens(a) == name_tokens(b)
    return clean(a) == clean(b)


# ---------------------------------------------------------------- assessment

def doc_label(d, lang='ar'):
    from .vision import TYPES
    kind = TYPES.get(d['kind'], d['kind']) if lang == 'ar' else KIND_EN.get(d['kind'], d['kind'].replace('_', ' '))
    side = SIDE_LABELS.get(d.get('side'), SIDE_LABELS['unknown'])[0 if lang == 'ar' else 1]
    if d.get('side') in ('page', None) or d['kind'] == 'unknown':
        return kind
    return f'{kind} · {side}' if lang == 'ar' else f'{kind} ({side})'


def field_label(f, lang='ar'):
    if lang == 'en':
        return FIELD_EN.get(f['key'], f['key'].replace('_', ' '))
    from .understanding import LABELS
    return f.get('label') or LABELS.get(f['key'], f['key'])


def document_fields(d):
    """The fields KYC looks at for one document, with critical ones always present."""
    from .people import full_name
    fields = {f['key']: f for f in d.get('fields', []) if f.get('key') and f['key'] not in ('dates_found', 'numbers_found')}
    if d['kind'] == 'national_id' and d.get('side') == 'front':
        assembled = full_name(d)
        if assembled.get('value') and not fields.get('name', {}).get('value'):
            fields['name'] = dict(assembled, key='name')
    for key in CRITICAL.get((d['kind'], d.get('side')), []):
        fields.setdefault(key, {'key': key, 'value': '', 'status': 'missing'})
    return fields


NAME_PARTS = ['first_name', 'father_name', 'grandfather_name', 'surname']
PERSON_NAME_DOCS = [('national_id', 'front'), ('passport', 'page'), ('driving', 'front'), ('driving', 'page'),
                    ('business_license', 'page'), ('tax_card', 'page')]


def corroborate(docs, fields_by_doc, raws):
    """Raise confidence when two documents independently read the same fact identically.

    Two separate photos and OCR passes rarely make the *same* mistake, so agreement
    is combined as independent evidence (noisy-OR of both scores). A shorter name
    that matches the start of a longer one corroborates only the shorter reading.
    Calibration (scripts/evaluate_kyc.py) measures how much this is worth.
    """
    boosted = {}

    def candidates(key, kinds=None):
        out = []
        for d in docs:
            f = fields_by_doc[d['id']].get(key)
            raw, basis = raws.get((d['id'], key), (0, 'missing'))
            if f and str(f.get('value') or '').strip() and basis not in ('missing', 'unreadable') and \
                    (kinds is None or (d['kind'], d.get('side')) in kinds):
                out.append((d, str(f['value']), raw))
        return out

    def support(d, key, partner, raw):
        if (d['id'], key) not in raws:
            return
        current = boosted.get((d['id'], key))
        if current is None or raw > current[1]:
            boosted[(d['id'], key)] = (partner, raw)

    def support_parts(d, tokens, partner, partner_tokens, raw):
        # The ID front's separate name parts share the evidence, position by position, where both names overlap
        # (a triple name on the licence confirms the first three parts only).
        if (d['kind'], d.get('side')) != ('national_id', 'front'):
            return
        for i, part in enumerate(NAME_PARTS):
            value = (fields_by_doc[d['id']].get(part) or {}).get('value')
            if i < min(len(tokens), len(partner_tokens)) and tokens[i] == partner_tokens[i] and name_tokens(value) == [tokens[i]]:
                support(d, part, partner, raw)

    groups = [('name', PERSON_NAME_DOCS), ('national_number', None), ('birth_date', None),
              ('business_name', [('business_license', 'page'), ('tax_card', 'page')]),
              ('document_number', [('national_id', 'front'), ('national_id', 'back')])]
    for key, kinds in groups:
        found = candidates(key, kinds)
        for i, (a, va, ra) in enumerate(found):
            for b, vb, rb in found[i + 1:]:
                if a['id'] == b['id'] or (key == 'document_number' and a.get('side') == b.get('side')):
                    continue
                if key == 'name':
                    ta, tb = name_tokens(va), name_tokens(vb)
                    if ta == tb and len(ta) >= 2:
                        support(a, key, b, rb); support(b, key, a, ra)
                        support_parts(a, ta, b, tb, rb); support_parts(b, tb, a, ta, ra)
                    elif compare_names(va, vb)[0] == 'pass':
                        shorter, other, other_raw = (a, b, rb) if len(ta) < len(tb) else (b, a, ra)
                        support(shorter, key, other, other_raw)
                        support_parts(a, ta, b, tb, rb); support_parts(b, tb, a, ta, ra)
                elif same_value(key, va, vb):
                    support(a, key, b, rb); support(b, key, a, ra)
    for (doc_id, key), (partner, partner_raw) in boosted.items():
        raw, basis = raws[(doc_id, key)]
        if basis == 'human':
            continue
        combined = min(.99, 1 - (1 - raw) * (1 - partner_raw))
        if combined > raw:
            raws[(doc_id, key)] = (round(combined, 4), 'corroborated')
    return {k: v[0] for k, v in boosted.items()}


def assess_fields(d, fields, raws, partners, threshold, table, today, rules):
    critical = CRITICAL.get((d['kind'], d.get('side')), [])
    results = []
    for key, f in fields.items():
        raw, basis = raws[(d['id'], key)]
        conf = calibrated(raw, basis, table)
        partner = partners.get((d['id'], key)) if basis == 'corroborated' else None
        results.append({'key': key, 'label': field_label(f), 'label_en': field_label(f, 'en'),
                        'value': str(f.get('value') or ''), 'confidence': conf, 'raw_confidence': raw, 'basis': basis,
                        'status': f.get('status') or ('manual' if basis == 'human' else 'uncertain'),
                        'critical': key in critical, 'below_threshold': conf < threshold,
                        'checks': validate_field(f, d['kind'], today, rules),
                        **({'corroborated_by': doc_label(partner), 'corroborated_by_en': doc_label(partner, 'en')} if partner else {})})
    order = {k: i for i, k in enumerate(critical)}
    results.sort(key=lambda r: (not r['critical'], order.get(r['key'], 99)))
    return results, chronology(fields)


def assess_documents(documents, profile='auto', threshold=None, today=None, status='ready'):
    rules = policy()
    threshold = rules['threshold'] if threshold is None else float(threshold)
    today = today or date.today()
    table = calibration()
    docs = deepcopy([d for d in documents if d.get('kind') != 'unknown' or d.get('fields')])
    if profile == 'auto':
        profile = 'merchant' if any(d['kind'] in ('business_license', 'tax_card') for d in docs) else 'individual'
    reasons = []

    def reason(code, severity, ar, en, d=None, field=None, action=None):
        reasons.append({'code': code, 'severity': severity, 'message': ar, 'message_en': en,
                        'doc_id': d['id'] if d else None, 'field_key': field, 'action': action})

    # Requirements: is every expected document present?
    present = {(d['kind'], d.get('side')) for d in docs}
    requirements = []
    for rid in PROFILES[profile]:
        req = REQUIREMENTS[rid]
        best = min(req['options'], key=lambda opt: sum(o not in present for o in opt))
        missing = [o for o in best if o not in present]
        requirements.append({'id': rid, 'label': req['label'][0], 'label_en': req['label'][1],
                             'satisfied': not missing, 'missing': [list(m) for m in missing]})
        if missing:
            names = '، '.join(doc_label({'kind': k, 'side': s}) for k, s in missing)
            names_en = ', '.join(doc_label({'kind': k, 'side': s}, 'en') for k, s in missing)
            unidentified = sum(d['kind'] == 'unknown' or d.get('side') == 'unknown' for d in docs)
            if unidentified:
                # Likely present but not recognised (often a poor photo): do not claim it is missing.
                reason('unidentified_document', 'block',
                       f'لم يُتعرّف على: {names}. يوجد {unidentified} مستمسك غير محدد النوع أو الوجه — حدّد نوعه يدويًا أو أعد تصويره',
                       f'not identified: {names_en}. {unidentified} document(s) have an unknown type or side — set it manually or retake the photo',
                       action='classify')
            else:
                reason('missing_document', 'block', f'مستمسك مطلوب غير موجود: {names}', f'required document missing: {names_en}',
                       action='upload')

    # Per-document fields: own evidence first, then agreement across documents.
    fields_by_doc = {d['id']: document_fields(d) for d in docs}
    raws = {(d['id'], key): raw_confidence(f, d.get('capture') or []) for d in docs for key, f in fields_by_doc[d['id']].items()}
    partners = corroborate(docs, fields_by_doc, raws)
    assessed = []
    for d in docs:
        fields, order_findings = assess_fields(d, fields_by_doc[d['id']], raws, partners, threshold, table, today, rules)
        capture_issues = d.get('capture') or []
        entry = {'id': d['id'], 'kind': d['kind'], 'side': d.get('side'), 'label': doc_label(d), 'label_en': doc_label(d, 'en'),
                 'image_id': d.get('image_id'), 'reviewed': bool(d.get('reviewed')), 'capture': capture_issues,
                 'retake': any(i.get('severity') == 'retake' for i in capture_issues), 'fields': fields,
                 'findings': order_findings}
        assessed.append(entry)
        required_doc = (d['kind'], d.get('side')) in CRITICAL
        for f in fields:
            # One reason per field, so the reviewer sees each problem once.
            where = f'{f["label"]} ({entry["label"]})'
            where_en = f'{f["label_en"]} ({entry["label_en"]})'
            pct, limit = round(f['confidence'] * 100), round(threshold * 100)
            problems = []
            if f['critical'] and not f['value']:
                problems.append(('field_missing', 'block', 'لم يُقرأ — يبقى فارغًا ولم يُملأ تلقائيًا', 'not read — left blank, never filled in'))
            elif f['value'] and f['below_threshold'] and (f['critical'] or required_doc):
                conflict = ' (قراءات متعارضة)' if f['status'] == 'conflict' else ''
                conflict_en = ' (conflicting readings)' if f['status'] == 'conflict' else ''
                problems.append(('low_confidence' if f['critical'] else 'low_confidence_optional', 'block' if f['critical'] else 'warn',
                                 f'«{f["value"]}» بثقة {pct}% أقل من الحد {limit}%{conflict} — قارن بالصورة',
                                 f'"{f["value"]}" at {pct}% confidence, below the {limit}% threshold{conflict_en} — compare with the image'))
            for c in f['checks']:
                severity = c['severity'] if f['critical'] or c['code'] in ('expired', 'mrz_mismatch') else 'warn'
                problems.append((c['code'], severity, c['message'], c['message_en']))
            if problems:
                severity = 'block' if any(p[1] == 'block' for p in problems) else 'warn'
                reason(problems[0][0], severity, f'{where}: ' + '؛ '.join(p[2] for p in problems),
                       f'{where_en}: ' + '; '.join(p[3] for p in problems), d, f['key'],
                       'read_image' if problems[0][0] == 'field_missing' else 'compare')
        for c in order_findings:
            reason(c['code'], 'block', f'{entry["label"]}: {c["message"]}', f'{entry["label_en"]}: {c["message_en"]}', d)
        for i in capture_issues:
            if i.get('severity') == 'retake':
                reason('retake', 'warn', f'{entry["label"]}: {i["message"]}', f'{entry["label_en"]}: {i["message_en"]}', d,
                       action='retake')

    cross = cross_checks(assessed, threshold)
    for c in cross:
        if c['status'] in ('fail', 'warn', 'unverifiable'):
            severity = 'block'
            reason('cross_' + c['code'], severity, f'{c["label"]}: {c["message"]}', f'{c["label_en"]}: {c["message_en"]}',
                   action='compare')

    if status in ('queued', 'processing'):
        decision = 'pending'
    else:
        decision = 'review' if any(r['severity'] == 'block' for r in reasons) else 'pass'
    fields_all = [f for e in assessed for f in e['fields']]
    counts = {'documents': len(assessed), 'fields': len(fields_all),
              'critical_fields': sum(f['critical'] for f in fields_all),
              'routed_fields': sum(f['critical'] and (f['below_threshold'] or not f['value']) for f in fields_all),
              'blocking_reasons': sum(r['severity'] == 'block' for r in reasons),
              'retake_documents': sum(e['retake'] for e in assessed)}
    result = {'decision': decision, 'profile': profile, 'threshold': threshold, 'as_of': today.isoformat(),
              'calibration': {'fitted': bool(table), **({k: table.get(k) for k in ('fitted_on', 'samples', 'created')} if table else {})},
              'requirements': requirements, 'documents': assessed, 'cross_checks': cross, 'reasons': reasons, 'counts': counts}
    result['summary'], result['summary_en'] = summarize(result)
    return result


def cross_checks(assessed, threshold):
    """Compare the same fact across documents. Low confidence makes a check unverifiable."""
    def values(key, kinds=None):
        out = []
        for e in assessed:
            if kinds and (e['kind'], e['side']) not in kinds and e['kind'] not in kinds:
                continue
            f = next((f for f in e['fields'] if f['key'] == key and f['value']), None)
            if f:
                out.append({'doc_id': e['id'], 'document': e['label'], 'document_en': e['label_en'], 'kind': e['kind'],
                            'side': e['side'], 'value': f['value'], 'confidence': f['confidence']})
        return out

    checks = []
    person_kinds = [('national_id', 'front'), 'passport', 'driving', 'business_license', 'tax_card']
    names = values('name', person_kinds)
    anchor = next((n for n in names if n['kind'] in ('national_id', 'passport')), None)
    if anchor:
        for other in names:
            if other is anchor or other['kind'] == anchor['kind'] and other['side'] == anchor['side']:
                continue
            status, note, note_en = compare_names(anchor['value'], other['value'])
            if status == 'pass' and min(anchor['confidence'], other['confidence']) < threshold:
                status, note, note_en = 'unverifiable', 'تبدو متطابقة لكن ثقة القراءة أقل من الحد', 'appear to match but reading confidence is below threshold'
            checks.append({'code': 'name_match', 'label': f'الاسم: {anchor["document"]} ↔ {other["document"]}',
                           'label_en': f'Name: {anchor["document_en"]} vs {other["document_en"]}', 'status': status,
                           'message': f'{note} («{anchor["value"]}» / «{other["value"]}»)',
                           'message_en': f'{note_en} ("{anchor["value"]}" / "{other["value"]}")', 'values': [anchor, other]})
    for key, label, label_en, kinds in [
            ('document_number', 'رقم البطاقة بين وجهي الموحدة', 'Card number, national ID front vs back', ['national_id']),
            ('national_number', 'الرقم الوطني بين المستمسكات', 'National number across documents', None),
            ('birth_date', 'تاريخ الولادة بين المستمسكات', 'Date of birth across documents', None),
            ('business_name', 'الاسم التجاري بين الإجازة والبطاقة الضريبية', 'Business name, licence vs tax card', ['business_license', 'tax_card'])]:
        found = values(key, kinds)
        if key == 'document_number':
            # Only the national card's two faces share this number.
            found = [v for v in found if v['kind'] == 'national_id']
            if {v['side'] for v in found} != {'front', 'back'}:
                continue
        if len(found) < 2:
            continue
        agree = all(same_value(key, found[0]['value'], v['value']) for v in found[1:])
        confident = min(v['confidence'] for v in found) >= threshold
        status = 'pass' if agree and confident else 'unverifiable' if agree else 'fail'
        shown = ' / '.join(f'«{v["value"]}»' for v in found)
        message = {'pass': 'متطابق', 'unverifiable': 'متطابق لكن ثقة القراءة أقل من الحد', 'fail': 'قيم مختلفة'}[status]
        message_en = {'pass': 'consistent', 'unverifiable': 'consistent but below the confidence threshold', 'fail': 'values differ'}[status]
        checks.append({'code': key + '_match', 'label': label, 'label_en': label_en, 'status': status,
                       'message': f'{message} ({shown})', 'message_en': f'{message_en} ({shown})', 'values': found})
    return checks


def summarize(result, limit=8):
    """A short, human-readable brief for the reviewer (Arabic and English)."""
    t = round(result['threshold'] * 100)
    if result['decision'] == 'pending':
        return 'المعالجة جارية؛ سيظهر القرار عند اكتمال القراءة.', 'Processing; the decision appears when reading completes.'
    blocks = [r for r in result['reasons'] if r['severity'] == 'block']
    retakes = [r for r in result['reasons'] if r['code'] == 'retake']
    if result['decision'] == 'pass':
        ar = f'يمكن اعتماد الملف: كل الحقول الأساسية مقروءة بثقة {t}% أو أكثر، صالحة، ومتطابقة بين المستمسكات.'
        en = f'Passed: every critical field was read at {t}% confidence or higher, is valid, and is consistent across documents.'
        if not result['calibration']['fitted']:
            ar += ' (الثقة غير معايرة بعد.)'
            en += ' (Confidence is not calibrated yet.)'
        return ar, en
    ar = [f'يحتاج مراجعة بشرية — {len(blocks)} نقطة:']
    en = [f'Needs human review — {len(blocks)} item(s):']
    for i, r in enumerate(blocks[:limit], 1):
        ar.append(f'{i}. {r["message"]}')
        en.append(f'{i}. {r["message_en"]}')
    if len(blocks) > limit:
        ar.append(f'… و{len(blocks) - limit} نقاط أخرى.')
        en.append(f'… and {len(blocks) - limit} more.')
    if retakes:
        ar.append('اطلب إعادة التصوير: ' + ' | '.join(r['message'] for r in retakes[:3]))
        en.append('Ask for a new photo: ' + ' | '.join(r['message_en'] for r in retakes[:3]))
    return '\n'.join(ar), '\n'.join(en)


def assess_batch(batch, profile='auto', threshold=None, today=None):
    return assess_documents(batch.get('documents', []), profile, threshold, today, batch.get('status', 'ready'))
