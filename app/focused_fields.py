"""Local, evidence-based reading of dates and housing address lines.

Layout anchors determine where to read; they never provide field values.
Approximate output preserves uncertainty and is not eligible for auto-linking.
"""
from datetime import datetime
import re
import cv2
import numpy as np
from . import arabic_ocr

DATE_KEYS = ('issue_date', 'expiry_date', 'birth_date')
ADDRESS_KEYS = ('address', 'neighborhood', 'mahalla_number', 'street', 'house_number')
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def normalize(text):
    text = re.sub('[\u200e\u200f\u202a-\u202e\u2066-\u2069]', '', str(text)).translate(DIGITS).translate(str.maketrans('أإآٱىة', 'اااايه'))
    return re.sub('[\u064b-\u065f\u0670\u0640]', '', text).replace('تااريخ', 'تاريخ')


def date_readings(text, allow_compact=False):
    """Recognize calendar-valid dates. Character repairs remain approximate."""
    raw = normalize(text).strip()
    raw = re.sub(r'(?<!\d)(\d{4})\s+(\d{1,2})\s+(\d{1,2})(?!\d)', r'\1/\2/\3', raw)
    raw = re.sub(r'(?<!\d)(\d{1,2})\s+(\d{1,2})\s+(\d{4})(?!\d)', r'\1/\2/\3', raw)
    # Restrict lookalike correction to a digit-shaped date token, not words.
    result = []
    pattern = r'(?<![\w])([0-9OolISB]{1,4})\s*[/\\.\-–—٫:|]\s*([0-9OolISB]{1,2})\s*[/\\.\-–—٫:|]\s*([0-9OolISB]{1,4})(?![\w])'
    for match in re.finditer(pattern, raw):
        parts = list(match.groups())
        repaired = any(re.search('[OolISB]', p) for p in parts)
        clean = [p.translate(str.maketrans('OolISB', '001158')) for p in parts]
        if len(clean[0]) == 4:
            y, m, d = clean
        elif len(clean[2]) == 4:
            d, m, y = clean
        else:
            continue  # A two-digit year does not establish the century.
        try:
            value = datetime(int(y), int(m), int(d)).strftime('%Y/%m/%d')
        except ValueError:
            continue
        if not 1800 <= int(y) <= 2199:
            continue
        result.append({'value': value, 'approximate': repaired, 'raw_text': match[0], 'precision': 'full'})
    if allow_compact and not result:
        for token in re.findall(r'(?<!\d)\d{8}(?!\d)', raw):
            for y, m, d in [(token[:4], token[4:6], token[6:]), (token[4:], token[2:4], token[:2])]:
                try:
                    value = datetime(int(y), int(m), int(d)).strftime('%Y/%m/%d')
                    if 1800 <= int(y) <= 2199:
                        result.append({'value': value, 'approximate': True, 'raw_text': token, 'precision': 'full'})
                except ValueError:
                    pass
    return list({r['value']: r for r in result}.values())


def partial_date(text):
    raw = normalize(text)
    m = re.search(r'(?<!\d)([12][0-9?؟_]{3})\s*[/.-]\s*([0-9?؟_]{1,2})\s*[/.-]\s*([0-9?؟_]{1,2})(?!\d)', raw)
    if not m or not re.search('[?؟_]', m[0]):
        return None
    return '/'.join(p.replace('؟', '?').replace('_', '?') for p in m.groups())


def box_of(line):
    b = np.asarray(line.get('box', []), dtype=float)
    return b if b.shape == (4, 2) and np.isfinite(b).all() else None


def center_at(line, x):
    b = box_of(line)
    left, right = (b[0] + b[3]) / 2, (b[1] + b[2]) / 2
    return float(left[1] + (x - left[0]) * (right[1] - left[1]) / max(1, right[0] - left[0]))


def line_region(line, x1, x2, height, image):
    h, w = image.shape[:2]
    x1, x2 = max(0, x1), min(w - 1, x2)
    box = [[x1, center_at(line, x1)-height/2], [x2, center_at(line, x2)-height/2],
           [x2, center_at(line, x2)+height/2], [x1, center_at(line, x1)+height/2]]
    return np.clip(box, [0, 0], [w-1, h-1]).tolist()


def crop_box(image, box):
    b = np.asarray(box, np.float32)
    w = max(1, round(max(np.linalg.norm(b[1]-b[0]), np.linalg.norm(b[2]-b[3]))))
    h = max(1, round(max(np.linalg.norm(b[3]-b[0]), np.linalg.norm(b[2]-b[1]))))
    matrix = cv2.getPerspectiveTransform(b, np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]))
    return cv2.warpPerspective(image, matrix, (w,h), borderMode=cv2.BORDER_REPLICATE)


def colon_column(image, x_range=(.45,.68), y_range=(.02,.54)):
    """Detect repeated colon dots separating the national-ID value column."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 11)
    _, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    dots = [(cx,cy) for (_,_,cw,ch,area),(cx,cy) in zip(stats[1:],centers[1:])
            if x_range[0]*w<cx<x_range[1]*w and y_range[0]*h<cy<y_range[1]*h and 1<=cw<.018*w and 1<=ch<.03*h and area>=2 and .25<cw/ch<3]
    pairs = []
    for i,a in enumerate(dots):
        for b in dots[i+1:]:
            if abs(a[0]-b[0])<max(2,.004*w) and .009*h<abs(a[1]-b[1])<.037*h:
                pairs.append(((a[0]+b[0])/2,(a[1]+b[1])/2))
    groups = []
    for x,y in sorted(pairs):
        if groups and abs(x-np.mean([p[0] for p in groups[-1]]))<.01*w:
            groups[-1].append((x,y))
        else:
            groups.append([(x,y)])
    groups = [g for g in groups if len({round(y/(.025*h)) for _,y in g})>=3 and max(y for _,y in g)-min(y for _,y in g)>.15*h]
    if not groups:
        return None
    best = max(groups, key=lambda g: len({round(y/(.025*h)) for _,y in g}))
    return float(np.median([x for x,_ in best]))


def date_label(text):
    t = normalize(text).replace(' ', '')
    if any(s in t for s in ('تاريخ', 'تاريح', 'تاريخ')):
        if any(s in t for s in ('اصدار', 'تنظيم', 'صدور')):
            return 'issue_date'
        if any(s in t for s in ('نفاذ', 'انتهاء', 'انتها', 'صلاحي')):
            return 'expiry_date'
        if any(s in t for s in ('ولاد', 'ميلاد')):
            return 'birth_date'
    return None


def national_regions(image, lines):
    h,w = image.shape[:2]
    if not 1.3 < w/h < 2.2:
        return []
    anchors = {}
    unknown_dates = []
    inferred = set()
    for line in lines:
        b = box_of(line)
        if b is None or b[:,1].mean()>.56*h or b[:,0].max()<.72*w:
            continue
        t = normalize(line['text'])
        key = date_label(t)
        if not key:
            if 'جه' in t and 'اصدار' in t:key='issuing_authority'
            elif 'محل' in t and 'ولاد' in t:key='birth_place'
            elif 'الرقم' in t and any(s in t for s in ('عائل','عانل','خيزان')):key='family_number'
        if key:
            anchors.setdefault(key, line)
        elif 'تاريخ' in t:
            unknown_dates.append(line)
    if 'expiry_date' not in anchors and all(k in anchors for k in ('issue_date','birth_place')):
        a,b=(center_at(anchors[k],.43*w) for k in ('issue_date','birth_place'))
        between=[l for l in unknown_dates if a<center_at(l,.43*w)<b]
        if len(between)==1 and .07*h<b-a<.22*h and abs(center_at(between[0],.43*w)-(a+b)/2)<.18*(b-a):
            anchors['expiry_date']=between[0];inferred.add('expiry_date')
    if len(anchors)<3 or not ('issuing_authority' in anchors or sum(k in anchors for k in DATE_KEYS)>=2):
        return []
    column = colon_column(image)
    right = column-max(2,.008*w) if column else .605*w
    centers = sorted(center_at(l, .43*w) for l in anchors.values())
    gaps = [b-a for a,b in zip(centers,centers[1:]) if .035*h<b-a<.14*h]
    step = float(np.median(gaps)) if gaps else .077*h
    if not .035*h<step<.14*h:
        return []
    result = []
    for key,line in anchors.items():
        if key not in (*DATE_KEYS,'birth_place','issuing_authority'):continue
        left = .25*w if key in DATE_KEYS else .065*w if key in ('issuing_authority','family_number') else .20*w
        if key=='issuing_authority' and box_of(line)[:,0].min()<right-.12*w:
            left=max(.02*w,float(box_of(line)[:,0].min())-.025*w)
        result.append({'key':key,'box':line_region(line,left,right,step*(1.18 if key=='issuing_authority' else .94),image),
                       'language':'en' if key in DATE_KEYS or key=='family_number' else 'arabic',
                       'method':'adaptive_column','layout_uncertain':column is None or key in inferred,'role_inferred':key in inferred})
    return result


HOUSING_LABELS = {'information_office': 'مكتب معلومات', 'name': 'اسم رب الاسره',
                  'address': 'عنوان السكن', 'form_number': 'رقم الاستماره'}


def housing_role(text):
    """Which printed housing-card label a row contains, tolerating OCR slips
    (منوان الكن, مب مومت). Labels locate rows only; they never supply a value."""
    from .textmatch import contains_phrase
    t = normalize(text)
    for role, label in HOUSING_LABELS.items():
        # The four printed labels are long and mutually distinct, so two slips are safe.
        if contains_phrase(t, label, limit=2):
            return role
    return None


def housing_label_rows(image, lines):
    """Re-detect the printed label column when full-page OCR merged handwriting
    into the labels or misread them.

    Positions locate labels only. Field values are always read from image pixels.
    """
    from .understanding import rows_from_lines
    h,w=image.shape[:2]
    rows=rows_from_lines(lines)
    lower=[r for r in rows if box_of(r) is not None and box_of(r)[:,1].mean()>.48*h]
    merged=any(box_of(r)[:,0].min()<.55*w and box_of(r)[:,0].max()>.85*w
               and any(t in normalize(r['text']) for t in ('معلومات','اسر','عنوان')) for r in lower)
    found={housing_role(r['text']) for r in lower}-{None}
    if not merged and len(found)>=3:return rows
    x,y=int(.70*w),int(.44*h)
    panel=image[y:int(.96*h),x:]
    labels=[]
    for line in arabic_ocr.read(panel):
        b=box_of(line)
        if b is None:continue
        labels.append(dict(line,box=(b+np.array([x,y])).tolist()))
    refined=rows_from_lines(labels)
    roles=len({housing_role(r['text']) for r in refined}-{None})
    return refined if roles>=3 and roles>=len(found) else rows


# Rows of the handwritten fields on the printed housing-card front, as fractions of the card
# (centre y, right edge x = the printed label's left edge, row height). Measured on precisely
# cropped cards (reference geometry): office .565, name .671, address .774, form .913.
HOUSING_TEMPLATE_ROWS = {'information_office': (.565, .718, .15), 'name': (.671, .736, .17),
                         'address': (.774, .761, .18), 'form_number': (.913, .747, .17)}


def template_housing_regions(image, lines=()):
    """Field rows placed from the printed form's fixed layout, for a card whose printed labels
    are too blurred to read (development card: «الصمري التسرة» for «اسم رب الاسرة»).

    Needs evidence that this is the card: at least one garbled label (a word of it read
    within two letter slips). Rows snap to the printed labels seen in the label column,
    whatever their text; rows without one follow the template, shifted like the rows that
    were seen. Every reading from these rows stays approximate.
    """
    from .textmatch import contains_phrase
    h, w = image.shape[:2]
    if not 1.3 < w / h < 1.7:
        return []
    words = ('الاسره', 'السكن', 'الاستماره', 'معلومات', 'مكتب', 'عنوان')
    texts = [normalize(l.get('text', '')) for l in lines]
    if not any(contains_phrase(t, word, limit=2) for t in texts for word in words):
        return []
    labels = []
    for line in lines:
        b = box_of(line)
        if b is not None and b[:, 0].min() > .55 * w and b[:, 1].mean() > .45 * h:
            labels.append(float(b[:, 1].mean()) / h)
    rows = {}
    for key, (cy, _, _) in HOUSING_TEMPLATE_ROWS.items():
        near = [y for y in labels if abs(y - cy) < .06]
        if near:
            rows[key] = min(near, key=lambda y: abs(y - cy))
    shift = float(np.median([rows[k] - HOUSING_TEMPLATE_ROWS[k][0] for k in rows])) if rows else 0.0
    out = []
    for key, (cy, right, height) in HOUSING_TEMPLATE_ROWS.items():
        y = rows.get(key, cy + shift)
        # Handwriting sits on the printed line or above it (a blurred card's form number was
        # cut at the top by a centred row): reach higher than below.
        top, bottom = max(0, (y - .68 * height) * h), min(h - 1, (y + .42 * height) * h)
        out.append({'key': key, 'box': [[.02 * w, top], [right * w, top], [right * w, bottom], [.02 * w, bottom]],
                    'language': 'arabic', 'method': 'form_template', 'handwritten': True, 'layout_uncertain': True})
    return out


def housing_regions(image, lines, side):
    from .understanding import rows_from_lines
    h,w=image.shape[:2]
    if not 1.2<w/h<2.25:
        return []
    rows=housing_label_rows(image,lines) if side=='front' else rows_from_lines(lines)
    result=[]
    if side=='front':
        anchors={}
        for row in rows:
            b=box_of(row)
            if b is None or b[:,1].mean()<.38*h or b[:,0].max()<.65*w:continue
            t=normalize(row['text']).replace(' ','')
            if 'مكتب' in t and 'معلومات' in t:anchors['information_office']=row
            elif 'عنوان' in t and ('سكن' in t or 'كن' in t):anchors['address']=row
            elif 'استمار' in t and 'رقم' in t:anchors['form_number']=row
            elif any(s in t for s in ('رب','راب','اسم')) and any(s in t for s in ('اسر','اله','الاس')):anchors['name']=row
            elif housing_role(row['text']) and housing_role(row['text']) not in anchors:anchors[housing_role(row['text'])]=row
        if 'address' not in anchors or len(anchors)<2:return template_housing_regions(image,lines)
        # The printed form-number label helps locate the right-hand label column
        # even when OCR merges handwriting and the address label into one box.
        form=anchors.get('form_number')
        form_parts=[p for p in (form or {}).get('parts',[]) if box_of(p) is not None
                    and ('استمار' in normalize(p['text']) or 'رقم' in normalize(p['text']))
                    and box_of(p)[:,0].min()>.5*w]
        edge=min(float(box_of(p)[:,0].min()) for p in form_parts)+.02*w if form_parts else .76*w
        edge=max(.66*w,min(.79*w,edge))
        for key,row in anchors.items():
            if key not in ('address','information_office','name'):continue
            b=box_of(row)
            cy=b[:,1].mean()
            other=[abs(box_of(r)[:,1].mean()-cy) for k,r in anchors.items() if k!=key]
            step=min(other) if other else .14*h
            height=min(.19*h,max(.12*h,(b[:,1].max()-b[:,1].min())*.90))
            aliases={'address':('عنوان','السكن'),'information_office':('مكتب','معلومات'),'name':('اسم','رب','اسره')}[key]
            labels=[p for p in row.get('parts',[]) if box_of(p) is not None
                    and box_of(p)[:,0].min()>.55*w
                    and any(a in normalize(p['text']) for a in aliases)]
            right=min(float(box_of(p)[:,0].min()) for p in labels)-2 if labels else edge
            anchor=min(labels,key=lambda p:box_of(p)[:,0].min()) if labels else row
            if labels:
                label_height=np.ptp(box_of(anchor)[:,1])
                height=min(.18*h,max((.18 if key=='address' else .17 if key=='name' else .145)*h,label_height*1.20,step*1.35))
            if labels:
                # A short word's box angle is noisy. Estimate skew from all printed labels.
                printed=[p for r in anchors.values() for p in r.get('parts',[]) if box_of(p) is not None and box_of(p)[:,0].min()>.55*w]
                slopes=[(center_at(p,w)-center_at(p,0))/w for p in printed]
                slope=float(np.median(slopes)) if slopes else 0
                cx=float(box_of(anchor)[:,0].mean());cy=float(box_of(anchor)[:,1].mean())
                yleft=cy-slope*cx
                anchor=dict(anchor,box=[[0,yleft-1],[w,yleft+slope*w-1],[w,yleft+slope*w+1],[0,yleft+1]])
            left=0 if key in ('address','name') else .25*w
            result.append({'key':key,'box':line_region(anchor,left,right,height,image),'language':'arabic',
                           'method':'housing_label_line','handwritten':True})
        if form:
            # The form number is usually written on or below its dotted line; read
            # a band shifted downward, left of the printed label.
            b=box_of(form)
            label_left=min((float(box_of(p)[:,0].min()) for p in form_parts),default=float(b[:,0].min()))
            cy=float(b[:,1].mean())+.035*h
            top,bottom=max(0,cy-.085*h),min(h-1,cy+.10*h)
            right=max(.4*w,label_left-2)
            result.append({'key':'form_number','box':[[.02*w,top],[right,top],[right,bottom],[.02*w,bottom]],
                           'language':'arabic','method':'housing_label_line','handwritten':True})
    elif side=='back':
        for row in rows:
            if date_label(row['text'])!='issue_date':continue
            parts=[p for p in row.get('parts',[]) if box_of(p) is not None
                   and (normalize(p['text']).strip() in ('تاريخ','تنظيم','الاستماره') or date_label(p['text'])=='issue_date')
                   and box_of(p)[:,0].min()>.45*w]
            if len(parts)<2 and not any(date_label(p['text'])=='issue_date' for p in parts):continue
            edge=min(box_of(p)[:,0].min() for p in parts)-max(2,.009*w)
            anchor=next((p for p in parts if normalize(p['text']).strip()=='تاريخ'),parts[0])
            result.append({'key':'issue_date','box':line_region(anchor,.03*w,edge,.14*h,image),
                           'language':'arabic','method':'housing_date_line','handwritten':True})
    return result


def prepared_crops(image, regions):
    crops, metadata=[],[]
    for region in regions:
        crop=crop_box(image,region['box'])
        if not crop.size:continue
        scale=min(3,max(1,96/crop.shape[0]))
        crop=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
        for variant,work in [('color',crop),('gray',cv2.cvtColor(gray,cv2.COLOR_GRAY2RGB)),
                             ('contrast',cv2.cvtColor(cv2.createCLAHE(2,(4,4)).apply(gray),cv2.COLOR_GRAY2RGB))]:
            crops.append(work);metadata.append(dict(region,variant=variant))
        if region.get('handwritten') and region['key']=='name':
            margin=round(crop.shape[1]*.10)
            trimmed=crop[:,margin:]
            crops.append(trimmed);metadata.append(dict(region,variant='name_margin'))
        if region.get('handwritten') and region['key'] in ('name','information_office'):
            from .housing_handwriting import ink_variants
            for variant,work in ink_variants(crop)[1:]:
                crops.append(work);metadata.append(dict(region,variant=variant))
            # The pen alone, the stamp removed by ink darkness: another view of the same line.
            from . import handwritten_digits as hd
            mask,_=hd.local_mask(crop)
            layer=hd.pen_layer(crop,mask)
            if layer is not None and layer.any():
                layer=cv2.dilate(layer,np.ones((2,2),np.uint8))
                crops.append(cv2.cvtColor(255-layer,cv2.COLOR_GRAY2RGB));metadata.append(dict(region,variant='pen_layer'))
    return crops,metadata


def clean_address(text):
    text=str(text).strip(' \n:：|~`؛;.,')
    text=re.sub(r'^(?:عنوان\s*(?:السكن|الكن)|محل\s*السكن)\s*[:：]?', '',text).strip()
    return text if len(text)>=2 and re.search('[\u0621-\u064a0-9۰-۹٠-٩]',text) else ''


def read_regions(image, regions):
    from .understanding import field, valid_value
    collected={r['key']:[] for r in regions}
    for language in ('en','arabic'):
        selected=[r for r in regions if r['language']==language or (language=='arabic' and r['key'] in DATE_KEYS)]
        crops,metadata=prepared_crops(image,selected)
        for meta,reading in zip(metadata,arabic_ocr.recognize_crops(crops,language)):
            key=meta['key'];text=reading['text'];score=reading['confidence']
            if score<.30:continue
            if key in DATE_KEYS:
                values=date_readings(text,allow_compact=True)
                if not values:
                    partial=partial_date(text)
                    if not partial and meta.get('handwritten'):
                        chunks=re.findall(r'[0-9]+',normalize(text))
                        if 3<=sum(map(len,chunks))<=10:partial=' '.join(chunks)
                    values=[{'value':partial,'approximate':True,'precision':'partial','raw_text':text}] if partial else []
            else:
                value=clean_address(text) if key in ('address','information_office') else valid_value(key,text)
                if key=='information_office' and not plausible_office(value):value=''
                if key=='issuing_authority':value=re.sub(r'\s+',' ',value).strip()
                values=[{'value':value,'approximate':bool(meta.get('handwritten')),'raw_text':text}] if value else []
            for value in values:
                collected[key].append(dict(value,confidence=score,engine='ppocr_v5_'+language,
                                           variant=meta['variant'],box=meta['box'],handwritten=bool(meta.get('handwritten'))))
    result={}
    for region in regions:
        key=region['key'];reads=collected[key]
        if not reads:continue
        # Agreement on an observed four-digit year can still be useful when
        # stamps hide the month/day. Do not turn the remaining digits into dates.
        if key in DATE_KEYS and region.get('handwritten') and not any(c.get('precision')=='full' for c in reads):
            year_reads={}
            for c in reads:
                match=re.match(r'^([12][0-9]{3})[0-9 /?.-]*$',normalize(c['value']))
                if match and 1800<=int(match[1])<=2199 and c['confidence']>=.65:
                    year_reads.setdefault(match[1],[]).append(c)
            if len(year_reads)==1:
                year,agree=next(iter(year_reads.items()))
                if len({c['variant'] for c in agree})>=2:
                    reads=reads+[dict(c,value=year+'/??/??',approximate=True,precision='partial',year_only=True) for c in agree]
        grouped={}
        for c in reads:
            token=normalize(c['value']).strip()
            grouped.setdefault(token,[]).append(c)
        ranked=sorted(grouped.values(),key=lambda group:(any(c.get('precision')=='full' for c in group),sum(c['confidence']>=.65 for c in group),max(c['confidence'] for c in group)),reverse=True)
        candidates=[]
        for group in ranked:
            best=max(group,key=lambda c:c['confidence'])
            candidates.append(dict(best,support=len(group)))
        best=candidates[0]
        substantial=[c for c in candidates if c['confidence']>=.70 and (c['support']>=2 or c['confidence']>=.95)]
        conflict=len(substantial)>1
        approximate=best['approximate'] or region.get('handwritten') or best['confidence']<.90 or region.get('layout_uncertain')
        status='conflict' if conflict else 'approximate' if approximate else 'read'
        note='قراءة تقريبية من الصورة؛ راجع الأرقام والحروف قبل الاعتماد.' if approximate else 'قراءة من سطر الحقل بعد تحديد عمود القيم وتصحيح ميل السطر.'
        if conflict:note+=' توجد قراءات بديلة مختلفة.'
        if best.get('year_only'):note+=' اتفقت القراءات على السنة فقط؛ الشهر واليوم غير محددين.'
        if best.get('precision')=='partial':note+=' قراءة جزئية لا تكفي لتحديد تاريخ كامل؛ لم تُفترض سنة أو أرقام مفقودة.'
        result[key]=field(key,best['value'],best['confidence'],best['box'],region['method'],status,
                          candidates=candidates[:5],note=note,approximate=bool(approximate),raw_text=best['raw_text'])
        if key=='name' and region.get('handwritten'):
            # Every reading of every image variant: the name suggestions weigh them together.
            result[key]['readings']=[{'value':c['value'],'confidence':c['confidence'],'variant':c.get('variant')} for c in reads]
        if key in DATE_KEYS:
            result[key]['date_precision']=best.get('precision','full')
            result[key]['role_inferred']=bool(region.get('role_inferred'))
    return result


def check_chronology(fields):
    for first,second in [('birth_date','issue_date'),('issue_date','expiry_date')]:
        a,b=fields.get(first,{}),fields.get(second,{})
        try:
            earlier=datetime.strptime(a.get('value',''),'%Y/%m/%d')
            later=datetime.strptime(b.get('value',''),'%Y/%m/%d')
        except ValueError:continue
        if earlier>later:
            for f in (a,b):
                if f.get('verified') or f.get('method')=='manual' or f.get('status')=='manual':continue
                f['status']='conflict';f['note']=f.get('note','')+' تسلسل التواريخ غير متوافق؛ راجع الصورة. لم تُغيّر الأرقام تلقائيًا.'


def extract(image,lines,kind,side):
    if image is None or not arabic_ocr.available():return {}
    if kind=='national_id' and side=='back':regions=national_regions(image,lines)
    elif kind=='national_id' and side=='front':regions=national_front_regions(image,lines)
    elif kind=='housing':regions=housing_regions(image,lines,side)
    else:return {}
    result=read_regions(image,regions)
    if kind=='national_id' and side=='back':crosscheck_mrz(result,lines,image.shape)
    if kind=='housing':
        result.update(address_parts(result.get('address',{})))
        address_region=next((r for r in regions if r['key']=='address'),None)
        if address_region:
            from .housing_handwriting import read_address_symbols
            result.update(read_address_symbols(image,address_region,lines))
        if side=='front':
            from .housing_handwriting import digit_model_readings,combine_digit_readings
            combine_digit_readings(result,digit_model_readings(image,regions,lines))
        office=result.get('information_office');office_region=next((r for r in regions if r['key']=='information_office'),None)
        if office and office_region:
            # Full-line OCR of the office row is an independent reading of the same handwriting.
            ys=np.asarray(office_region['box'])[:,1];margin=image.shape[0]*.03
            for line in lines:
                b=box_of(line)
                if b is not None and b[:,0].min()<image.shape[1]*.6 and ys.min()-margin<=b[:,1].mean()<=ys.max()+margin and line.get('text'):
                    if not any(c.get('value')==line['text'] for c in office.get('candidates',[])):
                        office.setdefault('candidates',[]).append({'value':line['text'],'confidence':line.get('confidence'),'engine':'full_line_ocr','box':line['box']})
        from .iraqi_addresses import enrich_housing
        enrich_housing(result)
        name=result.get('name');name_region=next((r for r in regions if r['key']=='name'),None)
        if name and name_region:
            center=np.asarray(name_region['box'])[:,1].mean()
            for line in lines:
                b=box_of(line)
                if b is not None and b[:,0].min()<image.shape[1]*.5 and np.ptp(b[:,0])>image.shape[1]*.35 and abs(b[:,1].mean()-center)<image.shape[0]*.05:
                    if line.get('text') and not any(c['value']==line['text'] for c in name.get('candidates',[])):
                        name.setdefault('candidates',[]).append({'value':line['text'],'confidence':line.get('confidence'),'engine':'full_line_ocr','box':line['box']})
        from .housing_names import add_name_suggestions
        add_name_suggestions(name)
        if name and name_region and not name.get('verified') and name.get('method')!='manual' and name.get('readings'):
            # Rank the name suggestions on the line image itself (lexicon-constrained decoding).
            from .name_decoder import suggest
            try:ranked=suggest(crop_box(image,name_region['box']),name['readings'])
            except Exception:ranked=[]
            if ranked:
                shown=normalize(name.get('value','')).replace(' ','')
                others=[c for c in name.get('candidates',[]) if c.get('engine')!='name_spelling_suggestion']
                name['candidates']=[{'value':v,'confidence':None,'engine':'name_spelling_suggestion',
                                     'note':'اقتراح اسم من صورة السطر وقراءاته معًا؛ يحتاج مقارنة بالصورة.'}
                                    for v,_ in ranked if normalize(v).replace(' ','')!=shown]+others
        if name:name['label']='اسم رب الأسرة'
        if side=='front':
            # Optional local contextual reader (Ollama); a no-op when it is not installed/running.
            from .vision_llm import review_housing
            review_housing(image,result)
    check_chronology(result)
    return result


REFINABLE_KEYS = frozenset((*DATE_KEYS,*ADDRESS_KEYS,'name','birth_place','information_office','governorate','district','issuing_authority','sex','form_number'))
VERSION = 'local-fields-v16'  # v16: Mustamsak's own number reader (whole-strip CTC) votes on handwritten numbers


def address_parts(address):
    """Extract explicit Iraqi address labels, including محلة/زقاق/دار shorthand.

    A number's position alone never establishes its meaning. Propagate the
    source's uncertainty and retain its image evidence for every component.
    """
    from .understanding import field
    value=normalize(address.get('value',''))
    aliases={'mahalla_number':r'(?:ال)?محله|م', 'street':r'(?:ال)?زقاق|ز',
             'house_number':r'رقم\s*الدار|الدار|دار|د'}
    result={}
    for key,label in aliases.items():
        matches=list(re.finditer(r'(?<![A-Za-z\u0621-\u064a])(?:'+label+r')\s*[:：/-]?\s*(\d{1,6}(?:/\d{1,6})?)(?!\d)',value))
        values=list(dict.fromkeys(m[1] for m in matches))
        if not values:continue
        status='conflict' if len(values)>1 or address.get('status')=='conflict' else 'approximate' if address.get('status')!='read' else 'read'
        result[key]=field(key,values[0],address.get('confidence'),address.get('box'),'address_label',status,
                          approximate=status!='read',raw_text=address.get('raw_text',address.get('value')),
                          candidates=[{'value':v,'confidence':address.get('confidence'),'engine':'address_label'} for v in values],
                          note='مستخرج من رمز الحقل المكتوب في عنوان السكن؛ يحتفظ بدرجة عدم يقين قراءة العنوان.')
    return result


def checked_mrz_dates(lines,shape):
    """Validate date checks independently of an unreadable MRZ name line.

    A checked serial and a nearby, aligned TD1 second row are required.
    MRZ supplies YYMMDD only, so this function never invents a century.
    """
    from .national_serial import mrz_serial,compact
    from .mrz import check_digit
    h,w=shape[:2];serials=[];found={}
    for line in lines:
        b=box_of(line);serial=mrz_serial(line.get('text',''))
        if b is not None and serial and serial['checksum_valid'] and b[:,1].mean()>.48*h and np.ptp(b[:,0])>.4*w:
            serials.append(line)
    if len(serials)!=1:return {}
    first=box_of(serials[0]);cy=first[:,1].mean()
    for line in lines:
        b=box_of(line);text=compact(line.get('text',''))
        if b is None or not .025*h<b[:,1].mean()-cy<.18*h:continue
        if abs(b[:,0].min()-first[:,0].min())>.10*w or np.ptp(b[:,0])<.45*w:continue
        if not re.fullmatch(r'\d{7}[MF<]\d{7}[I1]RQ[A-Z0-9<]{5,12}',text):continue
        for key,start in [('birth_date',0),('expiry_date',8)]:
            token=text[start:start+6]
            if check_digit(token)!=text[start+6]:continue
            try:datetime(2000+int(token[:2]),int(token[2:4]),int(token[4:]))
            except ValueError:continue
            found.setdefault(key,[]).append({'yymmdd':token,'box':line['box'],'raw_text':line['text']})
    return {key:items[0] for key,items in found.items() if len({v['yymmdd'] for v in items})==1}


def crosscheck_mrz(fields,lines,shape):
    from .understanding import field
    for key,evidence in checked_mrz_dates(lines,shape).items():
        token=evidence['yymmdd'];f=fields.get(key)
        values=date_readings(f.get('value','')) if f else []
        partial=f"??{token[:2]}/{token[2:4]}/{token[4:]}"
        if values:
            matched=values[0]['value'][2:].replace('/','')==token
            f['mrz_date_check']={'matches':matched,**evidence}
            if matched:
                f['note']+=' تتطابق الأرقام مع تاريخ الشريط الآلي ذي رقم التحقق؛ القرن مأخوذ من التاريخ المطبوع.'
                if f.get('role_inferred') and not any(c.get('approximate') for c in f.get('candidates',[]) if c['value']==f['value']) and f.get('confidence',0)>=.9 and f['status']=='approximate':
                    f.update(status='read',approximate=False)
            else:
                f['status']='conflict'
                f['note']+=' يختلف عن تاريخ الشريط الآلي؛ راجع الصورة.'
                f.setdefault('candidates',[]).append({'value':partial,'engine':'mrz_date_check','confidence':None,'box':evidence['box']})
        elif not f or f.get('date_precision')=='partial':
            candidate=field(key,partial,None,evidence['box'],'mrz_date_check','approximate',
                approximate=True,date_precision='partial',raw_text=evidence['raw_text'],mrz_date_check=evidence,
                note='اليوم والشهر والسنة المختصرة اجتازت رقم التحقق في الشريط الآلي. ?? تعني أن القرن غير محدد؛ أكمل السنة من الصورة.')
            if f:candidate['candidates']=f.get('candidates',[])
            fields[key]=candidate


def plausible_office(text):
    """An office name is Arabic words, possibly with a separate number («9 نيسان»); no Latin
    letters, no digit glued to letters, and at least three letters (a blurred photo gave «١عه», «Co»)."""
    text=normalize(text)
    if re.search(r'[A-Za-z]',text):return False
    if any(re.search(r'[0-9]',t) and re.search(r'[ء-ي]',t) for t in text.split()):return False
    return len(re.findall(r'[ء-ي]',text))>=3


def merge_refined(existing,updates,image_id=None):
    """Preserve reviewed/manual fields and avoid degrading a clear older value."""
    from copy import deepcopy
    fields={f['key']:deepcopy(f) for f in existing}
    for key,reading in updates.items():
        if key not in REFINABLE_KEYS:continue
        if not reading.get('value'):
            # A flagged blank (e.g. a digit fused with a stamp) replaces only an empty field,
            # so its explanation and suggestion are shown instead of a bare "missing".
            old=fields.get(key,{})
            if reading.get('status')=='unreadable' and reading.get('note') and not old.get('value')                     and not old.get('verified') and old.get('method')!='manual' and old.get('status')!='manual':
                fields[key]=deepcopy(reading)|({'source_image_id':image_id} if image_id else {})
            continue
        if key=='name' and reading.get('method') not in ('housing_label_line','form_template'):continue
        old=fields.get(key,{})
        if old.get('verified') or old.get('method')=='manual' or old.get('status')=='manual':continue
        fresh=deepcopy(reading)
        if image_id:fresh['source_image_id']=image_id
        if old.get('value') and old.get('status') in ('read','conflict') and (old.get('confidence') or 0)>=.9:
            if normalize(old['value'])!=normalize(fresh['value']):
                if old.get('method') in ('adaptive_column','mrz_date_check') or fresh.get('status')!='read':
                    old['status']='conflict'
                    old['note']='اختلفت القراءة الجديدة عن السابقة؛ قارن القيمتين بالصورة.'
                    candidate={k:fresh.get(k) for k in ('value','confidence','box','source_image_id','method')}
                    if candidate not in old.setdefault('candidates',[]):old['candidates'].append(candidate)
                    continue
        fields[key]=fresh
    check_chronology(fields)
    return list(fields.values())



def national_front_regions(image,lines):
    """Read the printed sex field in the front value column only.

    Require the front's name/family labels and a gender label in the lower right;
    the nationality header, portrait and MRZ are never gender evidence.
    """
    h,w=image.shape[:2]
    if not 1.3<w/h<2.2:return []
    rows=[l for l in lines if box_of(l) is not None and box_of(l)[:,0].max()>.82*w
          and .32*h<box_of(l)[:,1].mean()<.94*h and np.ptp(box_of(l)[:,1])<.15*h]
    anchors=[l for l in rows if any(t in normalize(l['text']) for t in ('الاسم','الاب','الام','اللقب','الجد'))]
    labels=[l for l in rows if re.search(r'الجنس(?![\u0621-\u064a])',normalize(l['text']))
            and box_of(l)[:,1].mean()>.65*h]
    if len(anchors)<3 or len(labels)!=1:return []
    line=labels[0];column=colon_column(image,(.70,.87),(.33,.93))
    b=box_of(line)
    right=column-max(2,.006*w) if column is not None else .795*w
    left=max(.45*w,min(b[:,0].min()-.035*w,right-.16*w))
    centers=sorted(center_at(l,.68*w) for l in anchors+[line])
    gaps=[b-a for a,b in zip(centers,centers[1:]) if .035*h<b-a<.13*h]
    step=float(np.median(gaps)) if gaps else .07*h
    return [{'key':'sex','box':line_region(line,left,right,step*.96,image),
             'language':'arabic','method':'national_front_sex','layout_uncertain':column is None}]
