"""Local geometry and neural OCR. No network calls at inference time."""
from __future__ import annotations
import re
import threading
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'models' / 'easyocr'
_reader = None
_lock = threading.Lock()

TYPES = {
    'national_id': 'البطاقة الوطنية الموحدة', 'housing': 'بطاقة السكن',
    'civil_id': 'هوية الأحوال المدنية', 'nationality': 'شهادة الجنسية العراقية',
    'ration': 'البطاقة التموينية', 'passport': 'جواز السفر',
    'driving': 'إجازة السوق', 'vehicle': 'سنوية المركبة', 'voter': 'بطاقة الناخب',
    'birth': 'شهادة الولادة', 'death': 'شهادة الوفاة', 'marriage': 'عقد الزواج',
    'residence': 'بطاقة الإقامة',
    'business_license': 'إجازة ممارسة النشاط التجاري', 'tax_card': 'البطاقة الضريبية',
    'unknown': 'مستمسك غير محدد',
}
# Single-face documents whose side is always "page".
PAGE_KINDS = ['passport','birth','death','marriage','business_license','tax_card']
RULES = {
 'national_id': [('البطاقة الوطنية', 7), ('البطاقة الموحدة', 7), ('الرقم الوطني', 5), ('المعلومات المدنية', 2), ('I<IRQ', 8)],
 'housing': [('مكتب المعلومات', 6), ('عنوان السكن', 4), ('رب الاسرة', 4), ('بطاقة السكن', 8), ('رقم الاستمارة', 2), ('ضابط المكتب', 3)],
 'civil_id': [('الاحوال المدنية', 6), ('هوية الاحوال', 7), ('رقم الصحيفة', 3), ('السجل', 1)],
 'nationality': [('شهادة الجنسية', 9), ('قانون الجنسية', 4), ('اكتسب الجنسية', 4)],
 'ration': [('وزارة التجارة', 4), ('البطاقة التموينية', 9), ('المواد الغذائية', 3), ('اسم الوكيل', 3)],
 'passport': [('PASSPORT', 7), ('جواز سفر', 7), ('جواز السفر', 7), ('P<IRQ', 8)],
 'driving': [('DRIVER', 6), ('DRIVING', 6), ('اجازة السوق', 9), ('رخصة القيادة', 9), ('صنف الاجازة', 4)],
 'vehicle': [('سنوية', 7), ('تسجيل المركبات', 7), ('رقم الشاصي', 5), ('رقم المحرك', 4)],
 'voter': [('المفوضية', 4), ('بطاقة الناخب', 9), ('رقم الناخب', 6), ('مركز الاقتراع', 4)],
 'birth': [('شهادة الولادة', 9), ('بيان الولادة', 9), ('اسم المولود', 5)],
 'death': [('شهادة الوفاة', 9), ('بيان الوفاة', 9), ('سبب الوفاة', 5)],
 'marriage': [('عقد الزواج', 9), ('حجة الزواج', 9), ('اسم الزوجة', 3), ('المهر', 3)],
 'residence': [('بطاقة الاقامة', 9), ('RESIDENCE PERMIT', 9), ('مديرية الاقامة', 5)],
 'business_license': [('اجازة ممارسة', 8), ('ممارسة النشاط', 6), ('الرخصة التجارية', 8), ('رخصة تجارية', 8), ('غرفة تجارة', 5), ('مسجل الشركات', 6), ('شهادة تاسيس', 7), ('الاسم التجاري', 3), ('رقم الاجازة', 3)],
 'tax_card': [('الهيئة العامة للضرائب', 8), ('البطاقة الضريبية', 9), ('رقم التعريف الضريبي', 6), ('الرقم الضريبي', 5), ('اسم المكلف', 5), ('الضرائب', 2)],
}

def normalize(text):
    text = str(text).translate(str.maketrans('أإآىة٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', 'ااايه01234567890123456789'))
    return re.sub(r'[\u064b-\u065fـ]', '', text).upper()

def read_image(path):
    with Image.open(path) as im:
        if im.width * im.height > 45_000_000:
            raise ValueError('الصورة أكبر من 45 مليون بكسل؛ يرجى تصغيرها.')
        return np.array(ImageOps.exif_transpose(im).convert('RGB'))

def save_image(path, image):
    Image.fromarray(image.astype('uint8')).save(path, 'PNG')

def ordered(points):
    p = np.asarray(points, np.float32)
    # Angle order handles rotated diamonds where sum/difference ordering duplicates corners.
    c = p.mean(axis=0)
    p = p[np.argsort(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]))]
    return np.roll(p, -np.argmin(p.sum(axis=1)), axis=0)

def warp(image, points):
    p = ordered(points)
    if len(np.unique(p, axis=0)) != 4 or not cv2.isContourConvex(p.astype(np.int32)):
        raise ValueError('يجب تحديد أربع زوايا مختلفة تشكّل مستطيلاً حول المستمسك.')
    w = int(max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[3])))
    h = int(max(np.linalg.norm(p[3]-p[0]), np.linalg.norm(p[2]-p[1])))
    if min(w, h) < 30 or w*h > 45_000_000:
        raise ValueError('منطقة القص صغيرة جدًا أو كبيرة جدًا.')
    matrix = cv2.getPerspectiveTransform(p, np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]))
    return cv2.warpPerspective(image, matrix, (w,h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def readable_size(image, small=700, target=1000):
    """Enlarge a small crop (a card that filled a small part of the photo) so print and
    handwriting are big enough to read. Crops of normal size are left exactly as they are:
    enlarging a 900 px card by 11% changed readings that were right."""
    h, w = image.shape[:2]
    if w >= small or w < 30:
        return image
    scale = min(4.0, target / w)
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

CARD_WIDTH = 900  # the width the housing-card readers were developed and tuned at


def standard_card(image, lines=()):
    """Resize a card crop to CARD_WIDTH and scale its OCR boxes to match: (image, lines, factor).

    Handwriting rules (pen width, dot sizes, marker sizes) behave the same on every card only
    when cards reach them at one scale. Stress test on development cards: ×1.5 larger photos went
    from 30/32 to 18/32 numbers right (stray «٠», «0105»), ×0.6 smaller to 24/32. Cards
    already close to the standard (850–950 px) are left exactly as they are.
    """
    h, w = image.shape[:2]
    if 850 <= w <= 950 or w < 30:
        return image, list(lines), 1.0
    factor = CARD_WIDTH / w
    resized = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC)
    scaled = []
    for line in lines:
        line = dict(line)
        if line.get('box') is not None:
            line['box'] = (np.asarray(line['box'], float) * factor).round(2).tolist()
        scaled.append(line)
    return resized, scaled, factor

def text_angle(lines, width):
    """Tilt of the printed text in degrees (median of the long OCR lines' top edges), or 0."""
    angles = []
    for line in lines:
        b = np.asarray(line.get('box', []), float)
        if b.shape != (4, 2) or np.linalg.norm(b[1] - b[0]) < .12 * width:
            continue
        angles.append(np.degrees(np.arctan2(b[1][1] - b[0][1], b[1][0] - b[0][0])))
    return float(np.median(angles)) if len(angles) >= 3 else 0.0

def straighten(image, angle):
    """Rotate a card crop so its printed text is horizontal (white margins filled from the edges)."""
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def sharpened(image, amount=1.5):
    """Unsharp-masked copy for a blurred photo: strokes regain their edges and gaps."""
    blurred = cv2.GaussianBlur(image, (0, 0), 2)
    return cv2.addWeighted(image, 1 + amount, blurred, -amount, 0)

def even_lighting(image):
    """The card with its lighting evened out: each colour channel divided by its own smooth
    background (text removed first), so paper becomes one white and ink keeps its contrast.
    Stress test: brighter photos 11/32 numbers right, darker 22/32, at the photo's own lighting."""
    f = image.astype(np.float32)
    h, w = image.shape[:2]
    k = max(3, (min(h, w) // 60) | 1)
    paper = cv2.dilate(f, np.ones((k, k), np.uint8))  # remove dark text before estimating the paper
    paper = cv2.GaussianBlur(paper, (0, 0), max(3, min(h, w) / 25))
    return np.clip(f / np.maximum(paper, 1) * 235, 0, 255).astype(np.uint8)

def _iou(a,b):
    ax,ay,aw,ah=cv2.boundingRect(np.asarray(a,np.float32)); bx,by,bw,bh=cv2.boundingRect(np.asarray(b,np.float32))
    intersection=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    return intersection/max(1,min(aw*ah,bw*bh))

def detect_regions(image):
    """Find complete quadrilaterals first, then a strong full-width fold/gap.

    An uncertain page is kept whole, never silently discarded.
    """
    h,w=image.shape[:2]; scale=min(1,1600/max(h,w))
    small=cv2.resize(image,None,fx=scale,fy=scale)
    gray=cv2.cvtColor(small,cv2.COLOR_RGB2GRAY)
    sh,sw=gray.shape
    blur=cv2.GaussianBlur(gray,(5,5),0)
    edges=cv2.Canny(blur,35,110)
    masks=[cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))]
    _,light=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    masks.append(light)
    candidates=[]
    for mask in masks:
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area=cv2.contourArea(c)
            if not .03*sh*sw < area < .97*sh*sw: continue
            p=cv2.approxPolyDP(c,.025*cv2.arcLength(c,True),True)
            if len(p)!=4 or not cv2.isContourConvex(p): continue
            rect=cv2.minAreaRect(p); rw,rh=rect[1]
            if min(rw,rh)<40 or max(rw,rh)/min(rw,rh)>2.5: continue
            if area / max(1,rw*rh)<.72: continue
            # Several documents in one photo (a whole file laid on a desk): a card can be as small
            # as 3% of the frame, but only a card- or paper-shaped quad counts at that size.
            if area<.09*sh*sw and not 1.2<max(rw,rh)/min(rw,rh)<1.9: continue
            candidates.append((area,p.reshape(4,2)/scale))
    candidates.sort(reverse=True,key=lambda x:x[0])
    accepted=[]
    for area,p in candidates:
        # Overlap is measured against the smaller box, so a box printed inside a document already
        # found (photo frame, table, MRZ zone) is never taken for a document of its own.
        if all(_iou(p,q)<.35 for q in accepted): accepted.append(p)
    if len(accepted)>=2:
        return [{'points':ordered(p).round(2).tolist(),'method':'contour','score':.82} for p in sorted(accepted,key=lambda p:(p[:,1].mean(),p[:,0].mean()))][:20]
    # A folded card spanning the frame: seek a narrow, coherent horizontal boundary.
    # Avoid splitting ordinary portrait A4 pages merely because they have blank lines.
    if .57 < w/h < .94:
        central=gray[:,int(sw*.02):int(sw*.98)]
        row_std=central.std(axis=1)
        start,end=int(sh*.38),int(sh*.62)
        candidates=np.arange(start,end)
        objective=row_std[start:end]+np.abs(candidates-sh*.5)*.035
        k=start+int(np.argmin(objective))
        surrounding=np.median(row_std[start:end])
        if row_std[k]<9 and surrounding>max(16,row_std[k]*2.2):
            y=int(k/scale)
            return [{'points':[[0,0],[w-1,0],[w-1,y],[0,y]],'method':'seam','score':.60},
                    {'points':[[0,y+1],[w-1,y+1],[w-1,h-1],[0,h-1]],'method':'seam','score':.60}]
    if accepted:
        return [{'points':ordered(accepted[0]).round(2).tolist(),'method':'contour','score':.76}]
    return [{'points':[[0,0],[w-1,0],[w-1,h-1],[0,h-1]],'method':'whole_page','score':.35}]

def ocr_available():
    return all((MODEL_DIR / f).exists() for f in ['craft_mlt_25k.pth','arabic.pth'])

def reader():
    global _reader
    if _reader is None:
        if not ocr_available(): raise RuntimeError('نماذج القراءة المحلية غير مثبّتة. شغّل scripts/setup_models.py مرة واحدة مع الإنترنت.')
        import easyocr
        import torch
        torch.set_num_threads(4)
        _reader=easyocr.Reader(['ar','en'],gpu=False,model_storage_directory=str(MODEL_DIR),download_enabled=False,verbose=False,quantize=False)
    return _reader

def ocr(image):
    from . import arabic_ocr
    if arabic_ocr.available():
        return arabic_ocr.read(image)
    with _lock:
        h,w=image.shape[:2]
        factor=min(2,max(1,1200/max(h,w)))
        working=cv2.resize(image,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC)
        rows=reader().readtext(working,detail=1,paragraph=False,canvas_size=1800,mag_ratio=1,rotation_info=None,batch_size=8,workers=0)
        lines=[{'text':str(t),'confidence':round(float(c),3),'box':(np.array(b)/factor).round(1).tolist()} for b,t,c in rows]
        from .numeric_ocr import improve
        return improve(image,lines,MODEL_DIR)

def classify(lines, image=None):
    from .textmatch import contains_phrase
    text='\n'.join(x['text'] for x in lines)
    clean=normalize(text); scores={}; evidence={}
    for kind,rules in RULES.items():
        # Spacing-insensitive, OCR-slip-tolerant keyword presence (textmatch.contains_phrase).
        matched=[(word,weight) for word,weight in rules if contains_phrase(clean,normalize(word))]
        scores[kind]=sum(weight for _,weight in matched)
        evidence[kind]=[word for word,_ in matched]
    mrz_lines=[t['text'] for t in lines if t['text'].count('<')>=3 and len(t['text'])>=20]
    compact=re.sub(r'\s','',clean)
    if len(mrz_lines)>=3: scores['national_id']+=10; evidence['national_id'].append('TD1 MRZ layout')
    if re.search(r'(?:ID|I[<KL])IRQ',compact): scores['national_id']+=8; evidence['national_id'].append('MRZ IRQ')
    if re.search(r'P[<]IRQ',compact): scores['passport']+=8; evidence['passport'].append('MRZ IRQ')
    top=sorted(scores,key=scores.get,reverse=True)
    kind=top[0]; score=scores[kind]
    confidence=min(.94,.45+score*.035) if score>=4 and score-scores[top[1]]>=2 else .0
    method='ocr_rules'; match=None
    if not confidence: kind='unknown'
    if image is not None:
        from .references import match_reference
        match=match_reference(image)
        if match and (kind=='unknown' or match['kind']==kind):
            kind=match['kind']; confidence=max(confidence,match['score']); method='visual_reference+ocr'
            evidence[kind].append('تطابق سمات مرجع بصري')
    side=match.get('side','unknown') if match and match['kind']==kind else 'unknown'
    if kind=='national_id':
        if len(mrz_lines)>=3 or re.search(r'(?:ID|I[<KL])IRQ',compact) or any(normalize(v) in clean for v in ['تاريخ النفاذ','جهة الاصدار','تاريخ الاصدار','الرقم العائلي']): side='back'
        elif any(normalize(v) in clean for v in ['الرقم الوطني','فصيلة الدم','الاسم','اللقب']): side='front'
    elif kind=='housing':
        if any(normalize(v) in clean for v in ['رب الاسرة','عنوان السكن']): side='front'
        elif any(normalize(v) in clean for v in ['ضابط المكتب','اسم ودرجة','تاريخ تنظيم']): side='back'
    elif kind in PAGE_KINDS: side='page'
    from .learned import suggest
    suggestion=suggest(image) if image is not None and kind=='unknown' else None
    return {'suggestion':suggestion,'kind':kind,'side':side,'confidence':round(confidence,2),'method':method,'evidence':evidence.get(kind,[])}

def extract_fields(lines, kind, image=None, side="unknown"):
    text='\n'.join(x['text'] for x in lines); clean=normalize(text)
    fields=[]
    def add(key,label,value,conf=.5):
        if value and not any(f['key']==key for f in fields): fields.append({'key':key,'label':label,'value':value,'confidence':conf,'verified':False})
    # Numeric values have explicit type constraints; unlabeled dates remain unassigned.
    if kind=='national_id':
        number=re.search(r'(?<!\d)(\d{12})(?!\d)',clean)
        if number: add('national_number','الرقم الوطني',number[1],.7)
        serial=re.search(r'\b([A-Z]{1,2}\d{6,9})\b',clean)
        if serial: add('document_number','رقم البطاقة',serial[1],.6)
    dates=re.findall(r'(?<!\d)(\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})(?!\d)',clean)
    if dates: add('dates_found','تواريخ مقروءة (تحتاج تعيينًا)', ' | '.join(dict.fromkeys(dates)),.5)
    labels=[('name','الاسم',['الاسم الكامل','اسم رب الاسرة','اسم رب الأسرة']),('address','العنوان',['عنوان السكن']),('birth_date','تاريخ الولادة',['تاريخ الولادة']),('issue_date','تاريخ الإصدار',['تاريخ الاصدار','تاريخ الإصدار']),('expiry_date','تاريخ النفاذ',['تاريخ النفاذ'])]
    for key,label,aliases in labels:
        for line in lines:
            # Only take values explicitly following a colon in the same OCR line.
            parts=re.split(r'[:：]',line['text'],maxsplit=1)
            if len(parts)==2 and any(normalize(a) in normalize(parts[0]) for a in aliases):
                value=parts[1].strip()
                if len(value)>1: add(key,label,value,round(line['confidence'],2))
    from .mrz import parse
    machine=parse([l['text'] for l in lines])
    if machine and machine['checks']['document_number'] and machine['checks']['composite']:
        fields=[f for f in fields if f['key']!='document_number']
        add('document_number','رقم البطاقة من MRZ',machine['document_number'],.95)
        if machine['checks']['birth_date']:add('birth_yymmdd','الولادة من MRZ (سنة شهر يوم)',machine['birth_yymmdd'],.95)
        if machine['checks']['expiry_date']:add('expiry_yymmdd','النفاذ من MRZ (سنة شهر يوم)',machine['expiry_yymmdd'],.95)
        add('latin_name','الاسم اللاتيني (قراءة غير محققة)',machine['latin_name'],.50)
    if kind=='housing':
        numbers=re.findall(r'(?<!\d)\d{4,9}(?!\d)',clean)
        if numbers:add('numbers_found','أرقام مقروءة (تحتاج تعيينًا)',' | '.join(dict.fromkeys(numbers)),.5)
    if image is not None:
        from .understanding import extract
        return extract(image,lines,kind,side,fields)
    return fields

def quality(image):
    h,w=image.shape[:2]; gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
    notices=[]
    if w<700 or h<400: notices.append('دقة الصورة منخفضة؛ راجع الأرقام والكتابة الصغيرة.')
    if cv2.Laplacian(gray,cv2.CV_64F).var()<60: notices.append('الصورة ضبابية وقد تؤثر في قراءة النص.')
    return notices
