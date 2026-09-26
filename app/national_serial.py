"""Read the national-card serial from its two physical locations, offline.

TD1 positions 6..14 contain the serial; position 15 is its check digit.
Names, the 12-digit national number, and upload order are never pairing keys.
"""
import re
import cv2
import numpy as np
from .mrz import check_digit

TRANSLATE=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')

def compact(text):
    return re.sub(r'\s','',str(text).translate(TRANSLATE).upper())

def valid_serial(text):
    text=compact(text)
    return text if len(text)==9 and re.fullmatch(r'[A-Z]{1,2}\d{7,8}',text) else ''

def mrz_serial(text):
    text=compact(text)
    if not re.fullmatch(r'(?:IDIRQ|I<IRQ)[A-Z0-9<]{9}\d[A-Z0-9<]{0,15}',text):return None
    number=valid_serial(text[5:14])
    if not number:return None
    return {'value':number,'check_digit':text[14],'checksum_valid':check_digit(number)==text[14]}

def rect(box):
    a=np.asarray(box)
    if a.shape!=(4,2) or not np.isfinite(a).all():return None
    return [float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())]

def quad(b):
    x1,y1,x2,y2=b
    return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]

def extract(lines,side,image=None,width=None,height=None):
    if image is not None:height,width=image.shape[:2]
    location='below_portrait' if side=='front' else 'mrz_first_line'
    result={'key':'document_number','label':'رقم البطاقة','value':'','confidence':None,'verified':False,
            'method':'national_serial_position','serial_location':location,'pairing_eligible':False,
            'status':'unreadable','box':None,'candidates':[]}
    if side not in ['front','back'] or not width or not height or not 1.25<width/height<2.25:return result
    candidates=[];regions=[]
    def take(text,score,box,engine):
        parsed=mrz_serial(text) if side=='back' else None
        value=parsed['value'] if parsed else valid_serial(text) if side=='front' else ''
        if not value:return
        candidates.append({'value':value,'confidence':float(score),'box':box,'engine':engine,
                           'checksum_valid':parsed['checksum_valid'] if parsed else None,
                           'check_digit':parsed['check_digit'] if parsed else None})
    for line in lines:
        b=rect(line.get('box',[]))
        if not b:continue
        cy=(b[1]+b[3])/2
        if side=='front':
            fits=b[2]<.49*width and b[0]<.25*width and .70*height<cy<height
        else:
            fits=cy>.48*height and b[2]-b[0]>.40*width and (compact(line['text']).startswith(('ID','I<')) or line['text'].count('<')>=2)
        if not fits:continue
        take(line['text'],line.get('confidence',0),line['box'],line.get('engine','ocr'))
        # Only the first MRZ row contains the document serial.
        if side=='front' or compact(line['text']).startswith(('ID','I<')):regions.append(b)
    if image is not None:
        from . import arabic_ocr
        if arabic_ocr.available():
            if not regions:
                regions=[[.01*width,.83*height,.40*width,.985*height]] if side=='front' else [[.025*width,.69*height,.97*width,.81*height]]
            crops=[];boxes=[]
            for b in regions[:3]:
                pad=max(1,int(height*.005));x1,y1,x2,y2=[int(n) for n in b]
                x1=max(0,x1-pad);y1=max(0,y1-pad);x2=min(width,x2+pad);y2=min(height,y2+pad)
                crop=image[y1:y2,x1:x2]
                if not crop.size:continue
                scale=min(3,80/max(1,crop.shape[0]));crop=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                gray=cv2.cvtColor(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),cv2.COLOR_GRAY2RGB)
                for c in [crop,gray]:crops.append(c);boxes.append(quad([x1,y1,x2,y2]))
            for read,box in zip(arabic_ocr.recognize_crops(crops,'en'),boxes):
                take(read['text'],read['confidence'],box,'ppocr_v5_en_serial')
    reliable=[c for c in candidates if c['confidence']>=.70 and (side=='front' or c['checksum_valid'])]
    chosen=sorted(reliable or candidates,key=lambda c:c['confidence'],reverse=True)
    if not chosen:
        result['note']='لم يُقرأ الرقم أسفل الصورة.' if side=='front' else 'لم يُقرأ رقم البطاقة في أول سطر MRZ.'
        return result
    best=chosen[0];values={c['value'] for c in reliable}
    eligible=len(values)==1 and best['confidence']>=.80
    result.update(value=best['value'],confidence=best['confidence'],box=best['box'],
                  pairing_eligible=eligible,status='conflict' if len(values)>1 else 'read' if eligible else 'uncertain')
    if side=='back':result.update(mrz_checksum=bool(best['checksum_valid']),mrz_check_digit=best['check_digit'])
    for c in chosen:
        if not any(x['value']==c['value'] for x in result['candidates']):
            result['candidates'].append({k:c[k] for k in ['value','confidence','engine']})
    result['note']='رقم البطاقة أسفل الصورة؛ يُطابق مع الرقم في خلف البطاقة.' if side=='front' else 'الرقم بعد IDIRQ أو I<IRQ؛ رقم التحقق التالي له ليس جزءًا من رقم البطاقة.'
    if not eligible:result['note']+=' القراءة غير كافية للتجميع التلقائي.'
    return result

def pairing_number(document):
    f=next((f for f in document.get('fields',[]) if f.get('key')=='document_number'),{})
    value=valid_serial(f.get('value',''))
    if not value:return None
    if f.get('method')=='manual':return value if f.get('verified') else None
    expected='below_portrait' if document.get('side')=='front' else 'mrz_first_line'
    if f.get('pairing_eligible') and f.get('serial_location')==expected:
        if document.get('side')=='back' and not f.get('mrz_checksum'):return None
        return value
    return None

def refresh_document(document,image=None):
    """Upgrade the serial only; keep other fields and reviewed manual corrections."""
    old=next((f for f in document.get('fields',[]) if f.get('key')=='document_number'),None)
    if old and old.get('method')=='manual':return
    f=extract(document.get('ocr',[]),document.get('side'),image,document.get('width'),document.get('height'))
    f['source_image_id']=document['image_id'] if image is not None else document.get('field_image_id',document['image_id'])
    if old:old.clear();old.update(f)
    else:document.setdefault('fields',[]).append(f)
