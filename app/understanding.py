"""Document-aware local extraction. Templates locate text, never supply values.

Scores describe OCR output, not calibrated probabilities. Conflicting/handwritten
readings are retained as suggestions, and are never silently marked verified.
"""
from datetime import datetime
import re
import cv2
import numpy as np
from . import arabic_ocr

VERSION = 'local-fields-v5'
LABELS = {
 'name':'الاسم الكامل', 'first_name':'الاسم', 'father_name':'اسم الأب',
 'grandfather_name':'اسم الجد', 'surname':'اللقب', 'mother_name':'اسم الأم',
 'maternal_grandfather':'اسم جد الأم', 'sex':'الجنس', 'blood_group':'فصيلة الدم',
 'national_number':'الرقم الوطني', 'document_number':'رقم البطاقة',
 'birth_date':'تاريخ الولادة', 'issue_date':'تاريخ الإصدار', 'expiry_date':'تاريخ النفاذ',
 'birth_place':'محل الولادة', 'issuing_authority':'جهة الإصدار', 'family_number':'الرقم العائلي',
 'address':'عنوان السكن', 'governorate':'المحافظة', 'district':'القضاء / الناحية',
 'neighborhood':'المنطقة / الحي', 'mahalla_number':'رقم المحلة', 'street':'الزقاق', 'house_number':'رقم الدار',
 'form_number':'رقم الاستمارة', 'information_office':'مكتب المعلومات', 'card_serial':'التسلسل',
 'nationality':'الجنسية', 'profession':'المهنة',
 'business_name':'الاسم التجاري', 'license_number':'رقم الإجازة', 'activity':'نوع النشاط',
 'tax_number':'الرقم الضريبي',
}
ALIASES = {
 'name':['الاسم الكامل','اسم رب الأسرة','الاسم الثلاثي','اسم صاحب البطاقة','اسم صاحب الإجازة','اسم المالك','اسم المكلف'],
 'father_name':['اسم الأب'], 'mother_name':['اسم الأم'], 'surname':['اللقب'],
 'address':['عنوان السكن','العنوان الدائم','محل السكن','العنوان'],
 'governorate':['المحافظة'], 'district':['القضاء','الناحية'],
 'neighborhood':['الحي','المنطقة'], 'mahalla_number':['المحلة','رقم المحلة'], 'street':['الزقاق'], 'house_number':['رقم الدار'],
 'birth_date':['تاريخ الولادة','تأريخ الولادة','تاريخ الميلاد'],
 'issue_date':['تاريخ الإصدار','تأريخ الإصدار','تاريخ تنظيم الاستمارة'],
 'expiry_date':['تاريخ النفاذ','تأريخ النفاذ','تاريخ الانتهاء'],
 'birth_place':['محل الولادة','مكان الولادة'], 'issuing_authority':['جهة الإصدار'],
 'family_number':['الرقم العائلي'], 'national_number':['الرقم الوطني'],
 'document_number':['رقم البطاقة','رقم الجواز','رقم الهوية'], 'form_number':['رقم الاستمارة'],
 'information_office':['مكتب المعلومات','مكتب معلومات'],
 'sex':['الجنس'], 'blood_group':['فصيلة الدم','فئة الدم'], 'profession':['المهنة'],
 'nationality':['الجنسية'],
 'business_name':['الاسم التجاري','اسم الشركة','اسم المنشأة'],
 'license_number':['رقم الإجازة','رقم الرخصة','رقم التسجيل التجاري'],
 'activity':['نوع النشاط','طبيعة النشاط'],
 'tax_number':['الرقم الضريبي','رقم التعريف الضريبي','رقم الملف الضريبي'],
}
SCHEMAS = {
 ('national_id','front'):['national_number','document_number','name','first_name','father_name','grandfather_name','surname','mother_name','maternal_grandfather','sex','blood_group'],
 ('national_id','back'):['document_number','birth_date','expiry_date','issue_date','birth_place','family_number','issuing_authority'],
 ('housing','front'):['name','address','governorate','district','neighborhood','mahalla_number','street','house_number','form_number','information_office'],
 ('housing','back'):['card_serial','issue_date'],
 ('passport','page'):['name','document_number','nationality','sex','birth_date','birth_place','issue_date','expiry_date'],
 ('business_license','page'):['name','business_name','license_number','activity','issue_date','expiry_date','address'],
 ('tax_card','page'):['name','business_name','tax_number','issue_date','expiry_date'],
}

def norm(text):
    return str(text).translate(str.maketrans('أإآىة٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','ااايه01234567890123456789')).upper()

def bounds(line):
    box = np.asarray(line.get('box', []))
    if box.shape != (4,2): return None
    return [float(box[:,0].min()),float(box[:,1].min()),float(box[:,0].max()),float(box[:,1].max())]

def quad(rect):
    x1,y1,x2,y2=rect
    return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]

def rows_from_lines(lines):
    groups=[]
    for line in sorted(lines,key=lambda l:bounds(l)[1] if bounds(l) else 0):
        b=bounds(line)
        if not b:continue
        cy=(b[1]+b[3])/2; height=b[3]-b[1]
        for group in groups:
            gb=group['rect']
            if abs(cy-(gb[1]+gb[3])/2)<.42*min(height,gb[3]-gb[1]):
                group['parts'].append(line)
                group['rect']=[min(b[0],gb[0]),min(b[1],gb[1]),max(b[2],gb[2]),max(b[3],gb[3])]
                break
        else:groups.append({'parts':[line],'rect':b})
    result=[]
    for g in groups:
        parts=sorted(g['parts'],key=lambda l:bounds(l)[0],reverse=True)
        result.append({'text':' '.join(l['text'] for l in parts),'box':quad(g['rect']),
                       'confidence':min(l.get('confidence',0) for l in parts),'parts':parts})
    return result

def valid_value(key,text):
    text=text.strip(' \n:：;،|.'); clean=norm(text)
    if key=='sex':
        match=re.search(r'(?<![\w])(?:ذكر|انثي|انثى|انثا|MALE|FEMALE)(?![\w])',clean)
        if not match:return ''
        return 'ذكر' if match[0] in ['ذكر','MALE'] else 'أنثى'
    if key=='blood_group':
        clean=re.sub(r'\s','',clean).replace('−','-')
        if re.fullmatch(r'(?:AB|A|B|O)',clean):return clean
        match=re.search(r'(?<![A-Z0-9])(?:AB|A|B|O|0)[+-](?![A-Z0-9])',clean)
        return match[0].replace('0','O') if match else ''
    if key.endswith('_date'):
        from .focused_fields import date_readings
        readings=date_readings(text)
        return next((r['value'] for r in readings if not r['approximate']), '')
    if key in ['national_number','document_number','family_number','form_number','house_number','license_number','tax_number']:
        clean=re.sub(r'\s','',clean).strip(':：;،|.')
        patterns={'national_number':r'\d{12}','document_number':r'[A-Z0-9/-]{5,20}',
                  'family_number':r'[A-Z0-9]{10,22}','form_number':r'\d{3,12}','house_number':r'\d{1,6}(?:/\d{1,6})?',
                  'license_number':r'[A-Z0-9/-]{3,20}','tax_number':r'\d{6,15}'}
        return clean if re.fullmatch(patterns[key],clean) else ''
    # Preserve the spelling actually read, including final ي/ى and ه/ة.
    if not re.search(r'[\u0621-\u064aA-Za-z]',text) or len(text)<2:return ''
    return text

def field(key,value='',score=None,box=None,method='label',status=None,**extra):
    return {'key':key,'label':LABELS.get(key,key),'value':value,'confidence':score,'verified':False,
            'status':status or ('read' if value and (score or 0)>=.9 else 'uncertain' if value else 'missing'),
            'method':method,'box':box,**extra}

def generic_fields(lines,kind):
    """Parse explicit labels and neighboring text, not arbitrary date order."""
    from .textmatch import find_label
    result={}
    rows=rows_from_lines(lines) or lines
    used=set()
    # Exact labels first; OCR-tolerant labels only for fields still missing,
    # and never on a row an exact label already claimed.
    for tolerant in (False,True):
        for index,row in enumerate(rows):
            if tolerant and index in used:continue
            raw=row['text'];text=norm(raw)
            for key,aliases in ALIASES.items():
                if key in result:continue
                for alias in aliases:
                    found=find_label(text,norm(alias))
                    if not found or bool(found[2])!=tolerant:continue
                    start,end,typos=found
                    # Bilingual national ID rows are read separately by the guarded layout.
                    if kind=='national_id' and key not in ['sex','blood_group'] and '/' in raw[end:] and not key.endswith('_date'):continue
                    tail=raw[end:].strip(' :：/|-')
                    if not tail and start>0 and re.search(r'[:：]',raw[:start]):tail=raw[:start].strip(' :：/|-')
                    value=valid_value(key,tail)
                    if not value:continue
                    if key not in ['sex','blood_group'] and any(norm(other) in norm(value) for aliases2 in ALIASES.values() for other in aliases2):continue
                    result[key]=field(key,value,row.get('confidence',.5),row.get('box'),'label_neighbors',raw_text=tail,
                                      **({'label_typos':typos} if typos else {}))
                    used.add(index);break
    return result

def template_regions(image,lines,kind,side):
    h,w=image.shape[:2]
    if not 1.32<w/h<2.18:return []
    rows=rows_from_lines(lines)
    def find(alias):
        pattern=re.escape(norm(alias)) + (r'(?![\u0621-\u064a])' if alias=='الجنس' else '')
        return [l for l in rows if re.search(pattern,norm(l['text']))]
    regions=[]
    def add(key,b,language='arabic'):
        x1,y1,x2,y2=b
        b=[max(0,x1),max(0,y1),min(w,x2),min(h,y2)]
        if b[2]-b[0]>8 and b[3]-b[1]>7:regions.append((key,b,language))
    if kind=='national_id' and side=='front':
        rows=[l for l in lines if bounds(l) and bounds(l)[0]>.38*w and bounds(l)[3]-bounds(l)[1]<.16*h]
        anchors=[find(x) for x in ['الاسم','الأب','اللقب','الأم','الجنس']]
        if sum(bool(a) for a in anchors)<3:return []
        # Require labels in the right-hand data column, not a page quoting labels.
        anchor_rows=[a[0] for a in anchors if a]
        if not all(bounds(l)[2]>.82*w and .30*h<bounds(l)[1]<.94*h for l in anchor_rows):return []
        def value_box(label):
            # OCR may return the label alone or merged with its value. Extend the
            # crop to value boxes on the same row, or to the whole value column.
            b=bounds(label);cy=(b[1]+b[3])/2;height=b[3]-b[1]
            values=[bounds(l) for l in lines if bounds(l) and bounds(l)[2]<=b[0]+2 and bounds(l)[0]>.36*w
                    and abs((bounds(l)[1]+bounds(l)[3])/2-cy)<.6*height]
            left=min([v[0] for v in values]+[b[0]])
            if left>.70*w:left=.38*w
            top=min([v[1] for v in values]+[b[1]]);bottom=max([v[3] for v in values]+[b[3]])
            return [max(.36*w,left-5),top-1,.757*w,bottom+1]
        for key,alias in [('first_name','الاسم'),('father_name','الأب'),('surname','اللقب'),('mother_name','الأم'),('sex','الجنس')]:
            matches=find(alias)
            if matches:add(key,value_box(matches[0]))
        grand=find('الجد')
        mother=find('الأم')
        divider=(bounds(mother[0])[1]+bounds(mother[0])[3])/2 if mother else .70*h
        assigned=set()
        for row in grand[:2]:
            b=bounds(row);key='grandfather_name' if (b[1]+b[3])/2<divider else 'maternal_grandfather'
            if key not in assigned:add(key,value_box(row));assigned.add(key)
        blood=find('الدم')
        if blood:
            b=bounds(blood[0]);add('blood_group',[.565*w,b[1]-1,.650*w,b[3]+1],'en')
        # Infer a missing label from a verified, regularly spaced data column.
        indices={'first_name':0,'father_name':1,'grandfather_name':2,'surname':3,'mother_name':4,'maternal_grandfather':5,'sex':6}
        observed=[(indices[k],(b[1]+b[3])/2) for k,b,_ in regions if k in indices]
        slopes=[(b[1]-a[1])/(b[0]-a[0]) for i,a in enumerate(observed) for b in observed[i+1:] if b[0]!=a[0]]
        if len(observed)>=3 and slopes:
            step=float(np.median(slopes));start=float(np.median([y-step*i for i,y in observed]))
            if .045*h<step<.11*h and all(abs(y-start-step*i)<.4*step for i,y in observed):
                existing={r[0] for r in regions}
                for key,index in dict(indices,blood_group=7).items():
                    if key in existing:continue
                    cy=start+index*step
                    nearby=min(rows,key=lambda l:abs((bounds(l)[1]+bounds(l)[3])/2-cy),default=None)
                    nb=bounds(nearby) if nearby else None
                    if nb and abs((nb[1]+nb[3])/2-cy)<.45*step:
                        b=[max(.36*w,nb[0]-.012*w),nb[1]-.004*h,.757*w,nb[3]+.004*h]
                    else:b=[.38*w,cy-.6*step,.757*w,cy+.6*step]
                    if key=='blood_group':b[0]=.565*w;b[2]=.650*w
                    add(key,b,'en' if key=='blood_group' else 'arabic')
    elif kind=='national_id' and side=='back':
        if sum(bool(find(a)) for a in ['جهة','الولادة','الرقم','الاصدار'])<3:return []
        if not (find('جهة') and bounds(find('جهة')[0])[1]<.15*h):return []
        # Relative rows are used only with the front-of-back header and data anchors.
        for key,b,lang in [
          ('issuing_authority',(.07,.025,.535,.142),'arabic'),
          ('issue_date',(.30,.115,.535,.215),'en'),('expiry_date',(.30,.195,.535,.292),'en'),
          ('birth_place',(.34,.270,.535,.368),'arabic'),('birth_date',(.30,.348,.535,.448),'en'),
          ('family_number',(.11,.427,.535,.53),'en')]:
            add(key,[b[0]*w,b[1]*h,b[2]*w,b[3]*h],lang)
    elif kind=='housing' and side=='front':
        if not (find('رب') and find('السكن')):return []
        for key,alias in [('name','رب'),('address','السكن'),('form_number','الاستمارة'),('information_office','مكتب معلومات')]:
            matches=find(alias)
            if not matches:continue
            row=matches[0];b=bounds(row)
            # Locate the printed label and read only the space to its left.
            parts=[p for p in row.get('parts',[]) if any(norm(a) in norm(p['text']) for a in {
                'name':['الاسرة','اسم رب'],'address':['عنوان','السكن'],
                'form_number':['رقم','الاستمارة'],'information_office':['مكتب','معلومات']}[key])]
            if not parts:continue
            edge=min(bounds(p)[0] for p in parts)
            if edge<.55*w:continue
            add(key,[0,max(0,b[1]-2),edge-2,min(h,b[3]+2)])
    return regions

def read_regions(image,regions,kind):
    result={}
    for language in ['arabic','en']:
        selected=[r for r in regions if r[2]==language]
        crops=[];records=[]
        for key,b,_ in selected:
            x1,y1,x2,y2=map(int,b);crop=image[y1:y2,x1:x2]
            if crop.size==0:continue
            crop=cv2.resize(crop,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
            gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
            for mode,c in [('color',crop),('gray',cv2.cvtColor(gray,cv2.COLOR_GRAY2RGB))]:
                records.append((key,b,mode));crops.append(c)
        reads=arabic_ocr.recognize_crops(crops,language)
        grouped={}
        for (key,b,mode),r in zip(records,reads):
            value=valid_value(key,r['text'])
            if value:grouped.setdefault(key,[]).append({'value':value,'confidence':r['confidence'],'engine':'ppocr_v5_'+language,'variant':mode})
        for key,b,_ in selected:
            candidates=sorted(grouped.get(key,[]),key=lambda c:c['confidence'],reverse=True)
            unique=[]
            for c in candidates:
                if not any(norm(x['value'])==norm(c['value']) for x in unique):unique.append(c)
            handwritten=kind=='housing' and key in ['name','address','information_office','form_number']
            if not candidates:
                result[key]=field(key,box=quad(b),method='field_crop',status='unreadable')
                continue
            best=candidates[0]
            # Handwriting on old housing cards is never promoted automatically.
            value='' if handwritten or best['confidence']<.65 else best['value']
            status='unreadable' if not value else 'conflict' if len(unique)>1 else 'read' if best['confidence']>=.94 else 'uncertain'
            result[key]=field(key,value,best['confidence'],quad(b),'field_crop',status,candidates=unique[:4],
                              note='خط يدوي؛ القراءة المقترحة تحتاج تحققًا من الصورة.' if handwritten else '')
    return result

def compare_ambiguous_names(image,fields):
    """Batch an independent recognizer; high OCR scores alone cannot prove a name."""
    from . import vision
    keys=['first_name','father_name','grandfather_name','surname','mother_name','maternal_grandfather','sex']
    targets=[fields[k] for k in keys if k in fields and fields[k].get('box')]
    if not targets or not vision.ocr_available():return
    crops=[];records=[]
    for f in targets:
        b=bounds(f)
        if not b:continue
        x1,y1,x2,y2=map(int,b)
        variants=[(0,0),(max(3,int(image.shape[1]*.009)),-max(1,int(image.shape[0]*.009)))]
        if (f.get('confidence') or 0)<.94:variants.append((max(3,int(image.shape[1]*.009)),max(1,int(image.shape[0]*.009))))
        for inset,shift in variants:
            crop=image[max(0,y1+shift):min(image.shape[0],y2+shift),x1+inset:x2]
            if not crop.size:continue
            gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
            scale=min(3,96/max(1,gray.shape[0]));gray=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            records.append(f);crops.append(gray)
    if not crops:return
    canvas=np.full((sum(c.shape[0]+12 for c in crops),max(c.shape[1] for c in crops)+12),255,np.uint8)
    boxes=[];offset=0
    for c in crops:
        ch,cw=c.shape;canvas[offset:offset+ch,:cw]=c;boxes.append([0,cw,offset,offset+ch]);offset+=ch+12
    with vision._lock:
        outputs=vision.reader().recognize(canvas,horizontal_list=boxes,free_list=[],detail=1,batch_size=8)
    for f,output in zip(records,outputs):
        _,text,score=output;text=valid_value(f['key'],text)
        if not text or score<.35:continue
        if f['key']=='sex' and not f.get('value'):
            f.update(value=text,confidence=round(float(score),3),status='uncertain',method='field_crop_easyocr')
        elif f.get('value') and norm(text)!=norm(f['value']):
            f['status']='conflict'
            if not any(norm(c['value'])==norm(text) for c in f.setdefault('candidates',[])):
                f['candidates'].append({'value':text,'confidence':round(float(score),3),'engine':'easyocr_arabic'})
            f['note']='اختلف محركا القراءة في الحروف؛ قارن الاقتراحات بالصورة.'

def extract(image,lines,kind,side,base_fields):
    fields={f['key']:dict(f,status='uncertain',method='text_pattern') for f in base_fields}
    # Link old numeric extraction to the line that actually contains the value.
    for f in fields.values():
        matching=next((l for l in lines if norm(str(f['value'])) in norm(l['text'])),None)
        if matching:f.update(box=matching.get('box'),confidence=matching.get('confidence'),status='read' if matching.get('confidence',0)>=.94 else 'uncertain')
    generic=generic_fields(lines,kind)
    if kind=='housing':
        generic={k:v for k,v in generic.items() if k in SCHEMAS.get((kind,side),[])}
    if kind=='national_id':
        # Bilingual labels can be mistaken for values; use explicit crops instead.
        generic={k:v for k,v in generic.items() if k in ['sex','blood_group'] or (v['method']=='label_neighbors' and ':' in next((l['text'] for l in lines if l.get('box')==v['box']),''))}
    fields.update(generic)
    if kind=='national_id' and side=='back':
        fields.pop('sex',None)  # The printed gender field belongs to the front.
    if image is not None and arabic_ocr.available():
        regions=template_regions(image,lines,kind,side)
        from . import focused_fields
        targeted=focused_fields.extract(image,lines,kind,side)
        regions=[r for r in regions if r[0] not in targeted]
        found=read_regions(image,regions,kind)
        for key,f in found.items():
            # A valid sex/blood label reading survives an unsuccessful crop pass.
            if key in ['sex','blood_group'] and not f['value'] and fields.get(key,{}).get('value'):continue
            fields[key]=f
        if kind=='national_id' and side=='front':compare_ambiguous_names(image,fields)
    if kind=='housing':
        for key in ['name','address','information_office']:
            if key in fields and fields[key].get('method')!='field_crop':
                f=fields[key];f['candidates']=[{'value':f['value'],'confidence':f.get('confidence'),'engine':'label_neighbors'}] if f['value'] else []
                f.update(value='',status='unreadable',note='قراءة خط اليد تحتاج مراجعة.')
    if image is not None and arabic_ocr.available():
        fields={f['key']:f for f in focused_fields.merge_refined(list(fields.values()),targeted)}
    if kind=='national_id' and side=='front':
        parts=[fields.get(k) for k in ['first_name','father_name','grandfather_name','surname']]
        if all(p and p.get('value') for p in parts):
            status='conflict' if any(p['status']=='conflict' for p in parts) else 'uncertain' if any(p['status']!='read' for p in parts) else 'read'
            fields['name']=field('name',' '.join(p['value'] for p in parts),min(p['confidence'] for p in parts),method='assembled_visible_names',status=status,
                                note='مجمّع من الاسم والأب والجد واللقب؛ راجع مكوّناته.')
    if kind=='housing' and side=='back' and image is not None and arabic_ocr.available():
        from .housing_back import serial_field
        serial=serial_field(image,lines)
        if serial:fields['card_serial']=serial
    if kind=='national_id' and side in ['front','back']:
        from .national_serial import extract as extract_serial
        fields['document_number']=extract_serial(lines,side,image)
    # Attach missing schema fields, so absence is visible rather than fabricated.
    schema=SCHEMAS.get((kind,side),['name','document_number'] if kind not in ['unknown','housing','national_id'] else [])
    for key in schema:
        if key not in fields:fields[key]=field(key)
    if kind=='housing' and 'name' in fields:fields['name']['label']='اسم رب الأسرة'
    known_dates={f['value'] for k,f in fields.items() if k.endswith('_date') and f.get('value')}
    if 'dates_found' in fields and all(valid_value('birth_date',v) in known_dates for v in fields['dates_found']['value'].split(' | ')):fields.pop('dates_found')
    ordered=[fields.pop(k) for k in schema if k in fields]
    return ordered+list(fields.values())
