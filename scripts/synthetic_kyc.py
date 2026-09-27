"""Generate fictional KYC document photos with ground truth, badly photographed on purpose.

Every person, number and business here is invented by this script. Templates
are marked "نموذج / SPECIMEN". Do NOT add real identity documents to this set.

Each case is one onboarding file: national ID front + back, business licence and
tax card. Some cases carry a deliberate inconsistency (another person's licence,
an expired licence, a back face from another card) so the KYC decision can be
scored. Photos are degraded at three levels: clean, poor and worst.

Usage:
  python scripts/synthetic_kyc.py --split tune --cases 14 --seed 11
  python scripts/synthetic_kyc.py --split heldout --cases 14 --seed 907
Tune and held-out splits use disjoint name pools and different seeds.
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mrz import check_digit  # noqa: E402

REFERENCE_DAY = date(2026, 9, 23)   # Evaluation "today"; keeps expiry labels reproducible.
FONTS = Path('C:/Windows/Fonts')
PRINT, BOLD, HAND, MRZ = 'tahoma.ttf', 'tahomabd.ttf', 'DIWANLTR.TTF', 'OCRAEXT.TTF'

# ------------------------------------------------------------------ Arabic shaping
# Pillow without libraqm does not join Arabic letters. Map each letter to its
# contextual presentation form (isolated, final, initial, medial), then reorder.
FORMS = {
    'ء': 'ﺀ', 'آ': 'ﺁﺂ', 'أ': 'ﺃﺄ', 'ؤ': 'ﺅﺆ', 'إ': 'ﺇﺈ', 'ئ': 'ﺉﺊﺋﺌ', 'ا': 'ﺍﺎ', 'ب': 'ﺏﺐﺑﺒ',
    'ة': 'ﺓﺔ', 'ت': 'ﺕﺖﺗﺘ', 'ث': 'ﺙﺚﺛﺜ', 'ج': 'ﺝﺞﺟﺠ', 'ح': 'ﺡﺢﺣﺤ', 'خ': 'ﺥﺦﺧﺨ', 'د': 'ﺩﺪ',
    'ذ': 'ﺫﺬ', 'ر': 'ﺭﺮ', 'ز': 'ﺯﺰ', 'س': 'ﺱﺲﺳﺴ', 'ش': 'ﺵﺶﺷﺸ', 'ص': 'ﺹﺺﺻﺼ', 'ض': 'ﺽﺾﺿﻀ',
    'ط': 'ﻁﻂﻃﻄ', 'ظ': 'ﻅﻆﻇﻈ', 'ع': 'ﻉﻊﻋﻌ', 'غ': 'ﻍﻎﻏﻐ', 'ف': 'ﻑﻒﻓﻔ', 'ق': 'ﻕﻖﻗﻘ', 'ك': 'ﻙﻚﻛﻜ',
    'ل': 'ﻝﻞﻟﻠ', 'م': 'ﻡﻢﻣﻤ', 'ن': 'ﻥﻦﻧﻨ', 'ه': 'ﻩﻪﻫﻬ', 'و': 'ﻭﻮ', 'ى': 'ﻯﻰ', 'ي': 'ﻱﻲﻳﻴ',
}
LAM_ALEF = {'آ': 'ﻵﻶ', 'أ': 'ﻷﻸ', 'إ': 'ﻹﻺ', 'ا': 'ﻻﻼ'}


def shape(text):
    out, i = [], 0
    joins_next = lambda c: c in FORMS and len(FORMS[c]) == 4
    while i < len(text):
        c = text[i]
        prev = text[i - 1] if i else ''
        # Alef (and so a lam-alef ligature) never joins forward, so this also covers ligatures.
        prev_joins = joins_next(prev)
        if c == 'ل' and i + 1 < len(text) and text[i + 1] in LAM_ALEF:
            out.append(LAM_ALEF[text[i + 1]][1 if prev_joins else 0]); i += 2; continue
        if c not in FORMS:
            out.append(c); i += 1; continue
        forms = FORMS[c]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        next_joins = nxt in FORMS and nxt != 'ء' and len(forms) == 4
        if prev_joins and next_joins: out.append(forms[3])
        elif prev_joins: out.append(forms[1])
        elif next_joins: out.append(forms[2])
        else: out.append(forms[0])
        i += 1
    return ''.join(out)


def visual(text):
    return get_display(shape(text))


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def text(draw, xy, value, size, anchor='rm', name=PRINT, fill=(28, 32, 38)):
    draw.text(xy, visual(value), font=font(name, size), anchor=anchor, fill=fill)


# ------------------------------------------------------------------ fictional identities
MALE = [('محمد', 'MOHAMMED'), ('احمد', 'AHMED'), ('علي', 'ALI'), ('حسن', 'HASSAN'), ('حسين', 'HUSSEIN'), ('عمر', 'OMAR'),
        ('خالد', 'KHALID'), ('سعد', 'SAAD'), ('كريم', 'KAREEM'), ('جاسم', 'JASIM'), ('قاسم', 'QASIM'), ('عباس', 'ABBAS'),
        ('حيدر', 'HAIDER'), ('مصطفى', 'MUSTAFA'), ('يوسف', 'YOUSIF'), ('سالم', 'SALIM'), ('ماجد', 'MAJID'), ('طارق', 'TARIQ'),
        ('عادل', 'ADIL'), ('نبيل', 'NABEEL'), ('فاضل', 'FADHIL'), ('رائد', 'RAED'), ('سمير', 'SAMEER'), ('وليد', 'WALEED')]
FEMALE = [('فاطمة', 'FATIMA'), ('زينب', 'ZAINAB'), ('مريم', 'MARYAM'), ('نور', 'NOOR'), ('سارة', 'SARA'), ('هدى', 'HUDA'),
          ('رقية', 'RUQAYA'), ('آمنة', 'AMINA'), ('ليلى', 'LAYLA'), ('سعاد', 'SUAD'), ('نادية', 'NADIA'), ('رنا', 'RANA')]
SURNAMES = [('الجبوري', 'ALJUBOURI'), ('التميمي', 'ALTAMIMI'), ('الربيعي', 'ALRUBAIE'), ('العبيدي', 'ALOBAIDI'),
            ('الساعدي', 'ALSAADI'), ('الخفاجي', 'ALKHAFAJI'), ('الشمري', 'ALSHAMMARI'), ('الدليمي', 'ALDULAIMI'),
            ('الزبيدي', 'ALZUBAIDI'), ('الكعبي', 'ALKAABI'), ('العامري', 'ALAMERI'), ('البياتي', 'ALBAYATI'),
            ('السامرائي', 'ALSAMARRAI'), ('الحديثي', 'ALHADITHI'), ('المالكي', 'ALMALIKI'), ('الطائي', 'ALTAI')]
CITIES = ['بغداد', 'البصرة', 'الموصل', 'النجف', 'كربلاء', 'الحلة', 'الناصرية', 'الديوانية', 'الكوت', 'السماوة']
BUSINESS = ['شركة النور للتجارة العامة', 'مكتب الرافدين للخدمات', 'شركة دجلة للمقاولات', 'متجر الفرات للأجهزة',
            'شركة بابل للنقل', 'مكتب الأمل للسفر', 'شركة الواحة للمواد الغذائية', 'معرض السلام للسيارات',
            'شركة الجسر للبرمجيات', 'مخبز الربيع الحديث', 'صيدلية الشفاء الأهلية', 'شركة الضياء للطاقة']
ACTIVITY = ['تجارة عامة', 'خدمات مكتبية', 'مقاولات إنشائية', 'بيع أجهزة كهربائية', 'نقل بضائع', 'خدمات سفر وسياحة',
            'بيع مواد غذائية', 'تجارة سيارات', 'تطوير برمجيات', 'مخابز', 'صيدلة']
DISTRICTS = ['الكرادة', 'المنصور', 'الأعظمية', 'زيونة', 'الجادرية', 'حي الجامعة', 'العشار', 'الحكيمية']


def pool(items, split):
    # Disjoint pools: tune uses even positions, held-out uses odd positions.
    return items[0::2] if split == 'tune' else items[1::2]


def random_date(rng, start, end):
    return start + timedelta(days=int(rng.integers(0, (end - start).days)))


def fmt(d):
    return d.strftime('%Y/%m/%d')


def person(rng, split):
    female = rng.random() < .35
    first = pool(FEMALE if female else MALE, split)[rng.integers(len(pool(FEMALE if female else MALE, split)))]
    males = pool(MALE, split)
    father, grand = males[rng.integers(len(males))], males[rng.integers(len(males))]
    surname = pool(SURNAMES, split)[rng.integers(len(pool(SURNAMES, split)))]
    mother = pool(FEMALE, split)[rng.integers(len(pool(FEMALE, split)))]
    mother_father = males[rng.integers(len(males))]
    letters = 'ABCDEFGHJKLMNPRSTUVWXYZ'
    serial = ''.join(rng.choice(list(letters), 2)) + ''.join(str(d) for d in rng.integers(0, 10, 7))
    birth = random_date(rng, date(1962, 1, 1), date(2003, 12, 31))
    issue = random_date(rng, date(2017, 1, 1), date(2025, 12, 31))
    return {
        'first_name': first[0], 'father_name': father[0], 'grandfather_name': grand[0], 'surname': surname[0],
        'latin_given': first[1], 'latin_surname': surname[1], 'mother_name': mother[0], 'maternal_grandfather': mother_father[0],
        'sex': 'أنثى' if female else 'ذكر', 'mrz_sex': 'F' if female else 'M',
        'blood_group': ['A+', 'B+', 'O+', 'AB+', 'A-', 'O-'][rng.integers(6)],
        'national_number': str(rng.integers(1, 3)) + ''.join(str(d) for d in rng.integers(0, 10, 11)),
        'document_number': serial, 'family_number': ''.join(str(d) for d in rng.integers(0, 10, 18)),
        'birth_date': birth, 'issue_date': issue, 'expiry_date': issue.replace(year=issue.year + 10) if not (issue.month == 2 and issue.day == 29) else issue + timedelta(days=3652),
        'birth_place': CITIES[rng.integers(len(CITIES))], 'issuing_authority': 'مديرية الأحوال المدنية والجوازات',
    }


def full_name(p, parts=4):
    return ' '.join([p['first_name'], p['father_name'], p['grandfather_name'], p['surname']][:parts])


# ------------------------------------------------------------------ templates
def canvas(width, height, top, bottom, seed):
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, height)[:, None, None]
    base = (np.array(top) * (1 - y) + np.array(bottom) * y) * np.ones((1, width, 1))
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    guilloche = 6 * np.sin(xx / 23 + np.sin(yy / 31) * 3) * np.cos(yy / 17)
    base = base + guilloche[..., None] + rng.normal(0, 2, (height, width, 1))
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def specimen(draw, width, height):
    draw.text((18, height - 22), 'SPECIMEN', font=font(BOLD, 18), anchor='lm', fill=(180, 40, 40))
    text(draw, (width - 18, height - 22), 'نموذج اختباري', 16, fill=(180, 40, 40))


def id_front(p, seed):
    w, h = 1000, 631
    im = canvas(w, h, (206, 226, 214), (226, 232, 206), seed)
    d = ImageDraw.Draw(im)
    text(d, (w - 30, 34), 'جمهورية العراق', 28, name=BOLD)
    text(d, (w - 30, 72), 'وزارة الداخلية - البطاقة الوطنية', 22)
    d.text((30, 40), 'REPUBLIC OF IRAQ', font=font(BOLD, 22), anchor='lm', fill=(28, 32, 38))
    text(d, (w - 30, 150), 'الرقم الوطني', 22, name=BOLD)
    d.text((.757 * w, 150), p['national_number'], font=font(BOLD, 28), anchor='rm', fill=(20, 24, 30))
    # Portrait placeholder (no face is drawn; face matching is out of scope).
    d.rounded_rectangle((40, 150, 290, 500), 12, fill=(185, 195, 200), outline=(120, 130, 140), width=2)
    d.ellipse((115, 210, 215, 320), fill=(160, 170, 178)); d.pieslice((80, 330, 250, 520), 180, 360, fill=(160, 170, 178))
    d.text((40, 545), p['document_number'], font=font(BOLD, 30), anchor='lm', fill=(20, 24, 30))
    rows = [('الاسم', p['first_name']), ('الأب', p['father_name']), ('الجد', p['grandfather_name']), ('اللقب', p['surname']),
            ('الأم', p['mother_name']), ('الجد', p['maternal_grandfather']), ('الجنس', p['sex'])]
    for i, (label, value) in enumerate(rows):
        y = .345 * h + i * .075 * h
        text(d, (w - 30, y), label, 23, name=BOLD)
        d.text((.795 * w, y), ':', font=font(BOLD, 24), anchor='mm', fill=(30, 30, 30))
        text(d, (.745 * w, y), value, 27)
    y = .345 * h + 7 * .075 * h
    text(d, (w - 30, y), 'فصيلة الدم', 21, name=BOLD)
    d.text((.60 * w, y), p['blood_group'], font=font(BOLD, 24), anchor='mm', fill=(20, 24, 30))
    specimen(d, w, h)
    return np.array(im)


def mrz_lines(p):
    serial = p['document_number']
    line1 = ('IDIRQ' + serial + check_digit(serial)).ljust(30, '<')
    birth, expiry = p['birth_date'].strftime('%y%m%d'), p['expiry_date'].strftime('%y%m%d')
    body = birth + check_digit(birth) + p['mrz_sex'] + expiry + check_digit(expiry) + 'IRQ'
    line2 = body.ljust(29, '<')
    line2 += check_digit(line1[5:30] + line2[:7] + line2[8:15] + line2[18:29])
    line3 = (p['latin_surname'] + '<<' + p['latin_given']).ljust(30, '<')[:30]
    return [line1, line2, line3]


def id_back(p, seed):
    w, h = 1000, 631
    im = canvas(w, h, (226, 230, 212), (208, 224, 216), seed + 1)
    d = ImageDraw.Draw(im)
    rows = [('جهة الإصدار', p['issuing_authority'], .08, PRINT, 22), ('تاريخ الإصدار', fmt(p['issue_date']), .165, BOLD, 24),
            ('تاريخ النفاذ', fmt(p['expiry_date']), .245, BOLD, 24), ('محل الولادة', p['birth_place'], .325, PRINT, 25),
            ('تاريخ الولادة', fmt(p['birth_date']), .405, BOLD, 24), ('الرقم العائلي', p['family_number'], .485, BOLD, 22)]
    for label, value, y, face, size in rows:
        text(d, (w - 30, y * h), label, 22, name=BOLD)
        d.text((.60 * w, y * h), ':', font=font(BOLD, 24), anchor='mm', fill=(30, 30, 30))
        if value[:1].isdigit():
            d.text((.53 * w, y * h), value, font=font(face, size), anchor='rm', fill=(20, 24, 30))
        else:
            text(d, (.53 * w, y * h), value, size, name=face)
    for i, line in enumerate(mrz_lines(p)):
        d.text((40, .72 * h + i * .085 * h), line, font=font(MRZ, 33), anchor='lm', fill=(15, 18, 22))
    specimen(d, w, h)
    return np.array(im)


def license_doc(p, biz, seed):
    w, h = 1400, 990
    im = canvas(w, h, (247, 244, 234), (240, 236, 222), seed + 2)
    d = ImageDraw.Draw(im)
    text(d, (w / 2, 60), 'جمهورية العراق - وزارة التجارة', 32, anchor='mm', name=BOLD)
    text(d, (w / 2, 115), 'غرفة تجارة بغداد', 26, anchor='mm')
    text(d, (w / 2, 180), 'إجازة ممارسة النشاط التجاري', 40, anchor='mm', name=BOLD, fill=(20, 60, 110))
    rows = [('اسم صاحب الإجازة', biz['owner'], True), ('الاسم التجاري', biz['name'], False),
            ('رقم الإجازة', biz['license_number'], False), ('نوع النشاط', biz['activity'], False),
            ('العنوان', biz['address'], False), ('تاريخ الإصدار', fmt(biz['issue_date']), False),
            ('تاريخ النفاذ', fmt(biz['expiry_date']), False)]
    for i, (label, value, handwritten) in enumerate(rows):
        y = 290 + i * 88
        line = f'{label} :'
        text(d, (w - 90, y), line, 30, name=BOLD)
        x = w - 110 - font(BOLD, 30).getlength(visual(line))
        d.line((140, y + 24, x, y + 24), fill=(170, 170, 170), width=1)
        if value[:1].isdigit() or value[:1].isascii() and value[:1].isalpha():
            d.text((x - 20, y), value, font=font(BOLD, 30), anchor='rm', fill=(25, 35, 90))
        else:
            # The owner's name is "filled in by hand" on some licences.
            text(d, (x - 20, y), value, 34 if handwritten else 30, name=HAND if handwritten and biz['hand'] else PRINT,
                 fill=(25, 35, 90))
    d.ellipse((160, 760, 360, 960), outline=(40, 70, 160), width=5)
    text(d, (260, 860), 'ختم الغرفة', 22, anchor='mm', fill=(40, 70, 160))
    d.line([(1000, 900), (1060, 870), (1100, 910), (1160, 860), (1220, 905)], fill=(30, 30, 80), width=3)
    specimen(d, w, h)
    return np.array(im)


def tax_card(p, biz, seed):
    w, h = 1000, 631
    im = canvas(w, h, (232, 222, 206), (220, 214, 232), seed + 3)
    d = ImageDraw.Draw(im)
    text(d, (w / 2, 40), 'جمهورية العراق - وزارة المالية', 24, anchor='mm', name=BOLD)
    text(d, (w / 2, 80), 'الهيئة العامة للضرائب', 24, anchor='mm')
    text(d, (w / 2, 128), 'البطاقة الضريبية', 34, anchor='mm', name=BOLD, fill=(110, 40, 30))
    rows = [('اسم المكلف', biz['tax_name']), ('الاسم التجاري', biz['name']), ('الرقم الضريبي', biz['tax_number']),
            ('تاريخ الإصدار', fmt(biz['tax_issue'])), ('تاريخ النفاذ', fmt(biz['tax_expiry']))]
    for i, (label, value) in enumerate(rows):
        y = 205 + i * 72
        line = f'{label} :'
        text(d, (w - 40, y), line, 25, name=BOLD)
        x = w - 60 - font(BOLD, 25).getlength(visual(line))
        if value[:1].isdigit():
            d.text((x - 12, y), value, font=font(BOLD, 26), anchor='rm', fill=(20, 24, 30))
        else:
            text(d, (x - 12, y), value, 26)
    specimen(d, w, h)
    return np.array(im)


# ------------------------------------------------------------------ bad photography
def desk(rng, width, height):
    tone = rng.integers(35, 110)
    y, x = np.mgrid[:height, :width]
    grain = 10 * np.sin(x / rng.uniform(8, 30) + np.sin(y / 90) * 4)
    tint = np.array([rng.uniform(.8, 1.1), rng.uniform(.75, 1.0), rng.uniform(.6, .9)])
    img = (tone + grain)[..., None] * tint + rng.normal(0, 4, (height, width, 1))
    return np.clip(img, 0, 255).astype(np.float32)


def photograph(doc, level, rng):
    """Place the document in a phone-like photo and degrade it. Returns (photo, applied)."""
    applied = []
    W, H = 1600, 1200
    scene = desk(rng, W, H)
    h, w = doc.shape[:2]
    frac = {'clean': rng.uniform(.62, .80), 'poor': rng.uniform(.5, .72), 'worst': rng.uniform(.42, .8)}[level]
    dw = frac * W
    dh = dw * h / w
    if dh > .85 * H:
        dh = .85 * H; dw = dh * w / h
    angle = np.radians(rng.uniform(-1, 1) * {'clean': 4, 'poor': 10, 'worst': 18}[level])
    jitter = {'clean': .015, 'poor': .045, 'worst': .09}[level] * dw
    cx, cy = W / 2 + rng.uniform(-.08, .08) * W, H / 2 + rng.uniform(-.08, .08) * H
    if level == 'worst' and rng.random() < .35:
        side = rng.choice(['left', 'right', 'top', 'bottom'])
        beyond = rng.uniform(.08, .18)
        if side in ('left', 'right'):
            cx = (dw / 2 - beyond * dw) if side == 'left' else W - (dw / 2 - beyond * dw)
        else:
            cy = (dh / 2 - beyond * dh) if side == 'top' else H - (dh / 2 - beyond * dh)
        applied.append(f'cut_off_{side}')
    corners = np.array([[-dw / 2, -dh / 2], [dw / 2, -dh / 2], [dw / 2, dh / 2], [-dw / 2, dh / 2]])
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    corners = corners @ rot.T + [cx, cy] + rng.uniform(-jitter, jitter, (4, 2))
    matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(corners))
    warped = cv2.warpPerspective(doc.astype(np.float32), matrix, (W, H))
    mask = cv2.warpPerspective(np.ones((h, w), np.float32), matrix, (W, H))[..., None]
    scene = scene * (1 - mask) + warped * mask
    if abs(np.degrees(angle)) > 10 or jitter > .06 * dw:
        applied.append('angle')
    # Uneven light, dim rooms.
    yy, xx = np.mgrid[:H, :W]
    gradient = 1 - rng.uniform(0, {'clean': .15, 'poor': .35, 'worst': .5}[level]) * (xx / W if rng.random() < .5 else yy / H)
    scene *= gradient[..., None]
    if level == 'worst' and rng.random() < .4:
        scene *= rng.uniform(.3, .5); applied.append('dark')
    elif level == 'poor' and rng.random() < .3:
        scene *= rng.uniform(.55, .7); applied.append('dim')
    # Glare from a lamp or window.
    if rng.random() < {'clean': 0, 'poor': .2, 'worst': .45}[level]:
        gx, gy = corners.mean(0) + rng.uniform(-.3, .3, 2) * [dw, dh]
        r = rng.uniform(.07, .16) * dw
        spot = np.exp(-(((xx - gx) / r) ** 2 + ((yy - gy) / (r * rng.uniform(.5, 1))) ** 2))
        scene += spot[..., None] * rng.uniform(260, 420)
        applied.append('glare')
    # A thumb or a sheet of paper over part of the document.
    if level == 'worst' and rng.random() < .3:
        edge = rng.integers(4)
        a, b = corners[edge], corners[(edge + 1) % 4]
        t = rng.uniform(.2, .8)
        px, py = a + t * (b - a)
        radius = rng.uniform(.08, .14) * dw
        color = rng.choice([[190, 140, 115], [238, 238, 232]])
        cv2.ellipse(scene, (int(px), int(py)), (int(radius), int(radius * 1.6)), float(rng.uniform(0, 180)), 0, 360,
                    [float(c) for c in color], -1)
        applied.append('occlusion')
    scene = np.clip(scene, 0, 255).astype(np.uint8)
    if level == 'poor':
        scene = cv2.GaussianBlur(scene, (0, 0), rng.uniform(.6, 1.4))
    elif level == 'worst':
        if rng.random() < .5:
            k = int(rng.integers(9, 17))
            kernel = np.zeros((k, k), np.float32); kernel[k // 2, :] = 1 / k
            kernel = cv2.warpAffine(kernel, cv2.getRotationMatrix2D((k / 2, k / 2), float(rng.uniform(0, 180)), 1), (k, k))
            scene = cv2.filter2D(scene, -1, kernel / max(kernel.sum(), 1e-6)); applied.append('motion_blur')
        else:
            scene = cv2.GaussianBlur(scene, (0, 0), rng.uniform(1.8, 3.2)); applied.append('blur')
    noise = {'clean': 2, 'poor': 5, 'worst': 9}[level]
    scene = np.clip(scene.astype(np.float32) + rng.normal(0, noise, scene.shape), 0, 255).astype(np.uint8)
    quality = {'clean': 88, 'poor': 62, 'worst': 38}[level]
    ok, jpeg = cv2.imencode('.jpg', cv2.cvtColor(scene, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return jpeg.tobytes(), applied


# ------------------------------------------------------------------ cases
# The demo split tells one story per case instead of random draws (tune and held-out stay random):
# (planted problem, photo level per document id_front/id_back/license/tax, handwritten licence name).
DEMO_PLAN = [
    (None, ['clean', 'clean', 'clean', 'clean'], False),               # a good file: the agent can pass it alone
    ('name_mismatch', ['clean', 'clean', 'clean', 'clean'], False),    # the licence belongs to someone else
    ('expired_license', ['clean', 'clean', 'clean', 'clean'], False),  # the licence ran out
    ('serial_mismatch', ['clean', 'clean', 'clean', 'clean'], False),  # the two ID faces are different cards
    (None, ['poor', 'clean', 'poor', 'clean'], True),                  # real-life photos: a person checks a few fields
    (None, ['worst', 'poor', 'worst', 'poor'], False),                 # unusable photos: the agent asks for retakes
]


def make_case(index, split, rng, plan=None):
    p = person(rng, split)
    other = person(rng, split)
    names = pool(BUSINESS, split)
    biz = {'owner': full_name(p, 3), 'name': names[rng.integers(len(names))], 'activity': ACTIVITY[rng.integers(len(ACTIVITY))],
           'license_number': f'BL-{rng.integers(10000, 99999)}', 'address': f'بغداد - {DISTRICTS[rng.integers(len(DISTRICTS))]}',
           'issue_date': random_date(rng, date(2023, 10, 1), date(2025, 12, 31)), 'hand': rng.random() < .5,
           'tax_name': full_name(p, 4), 'tax_number': ''.join(str(d) for d in rng.integers(0, 10, 10))}
    biz['expiry_date'] = biz['issue_date'] + timedelta(days=3 * 365)
    # Consistent cases must hold documents that are valid on REFERENCE_DAY.
    biz['tax_issue'] = random_date(rng, date(2025, 1, 1), date(2026, 6, 1))
    biz['tax_expiry'] = biz['tax_issue'] + timedelta(days=2 * 365)
    back_person = p
    roll = rng.random()
    problem = 'name_mismatch' if roll < .15 else 'expired_license' if roll < .25 else 'serial_mismatch' if roll < .35 else None
    if plan:
        problem, biz['hand'] = plan[0], plan[2]
    if problem == 'name_mismatch':
        biz['owner'] = full_name(other, 3)
    elif problem == 'expired_license':
        biz['issue_date'] = random_date(rng, date(2019, 1, 1), date(2022, 6, 1))
        biz['expiry_date'] = biz['issue_date'] + timedelta(days=3 * 365)
    elif problem == 'serial_mismatch':
        back_person = dict(p, document_number=other['document_number'])
    seed = int(rng.integers(1, 10 ** 6))
    truth_front = {k: p[k] for k in ('first_name', 'father_name', 'grandfather_name', 'surname', 'mother_name', 'sex',
                                     'national_number', 'document_number')} | {'name': full_name(p)}
    truth_back = {'document_number': back_person['document_number'], 'birth_date': fmt(p['birth_date']),
                  'issue_date': fmt(p['issue_date']), 'expiry_date': fmt(p['expiry_date']), 'birth_place': p['birth_place']}
    truth_license = {'name': biz['owner'], 'business_name': biz['name'], 'license_number': biz['license_number'],
                     'activity': biz['activity'], 'issue_date': fmt(biz['issue_date']), 'expiry_date': fmt(biz['expiry_date'])}
    truth_tax = {'name': biz['tax_name'], 'business_name': biz['name'], 'tax_number': biz['tax_number'],
                 'issue_date': fmt(biz['tax_issue']), 'expiry_date': fmt(biz['tax_expiry'])}
    return problem, [
        ('id_front', 'national_id', 'front', id_front(p, seed), truth_front),
        ('id_back', 'national_id', 'back', id_back(back_person, seed), truth_back),
        ('license', 'business_license', 'page', license_doc(p, biz, seed), truth_license),
        ('tax', 'tax_card', 'page', tax_card(p, biz, seed), truth_tax)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['tune', 'heldout', 'demo'], required=True)  # demo: fresh cases for the UI, never scored
    parser.add_argument('--cases', type=int, default=14)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--out', default=str(ROOT / 'eval' / 'synthetic'))
    parser.add_argument('--clean-copies', action='store_true', help='also save undegraded templates for inspection')
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else {'tune': 11, 'heldout': 907, 'demo': 4242}[args.split]
    rng = np.random.default_rng(seed)
    out = Path(args.out) / args.split
    out.mkdir(parents=True, exist_ok=True)
    labels = []
    levels = ['clean', 'poor', 'worst']
    count = len(DEMO_PLAN) if args.split == 'demo' else args.cases
    for case in range(count):
        plan = DEMO_PLAN[case] if args.split == 'demo' else None
        problem, docs = make_case(case, args.split, rng, plan)
        for n, (name, kind, side, image, truth) in enumerate(docs):
            level = levels[rng.choice(3, p=[.3, .4, .3])]
            if plan:
                level = plan[1][n]
            photo, applied = photograph(image, level, rng)
            file = f'case{case:03}_{name}.jpg'
            (out / file).write_bytes(photo)
            if args.clean_copies:
                Image.fromarray(image).save(out / f'case{case:03}_{name}_template.png')
            labels.append({'file': file, 'case': f'{args.split}-{case:03}', 'document': name, 'kind': kind, 'side': side,
                           'level': level, 'degradations': applied, 'case_problem': problem, 'fields': truth})
    (out / 'labels.json').write_text(json.dumps({'split': args.split, 'seed': seed, 'reference_day': REFERENCE_DAY.isoformat(),
                                                 'fictional': True, 'items': labels}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'split': args.split, 'images': len(labels), 'out': str(out)}))


if __name__ == '__main__':
    main()
