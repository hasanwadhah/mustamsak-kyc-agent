"""Use matching faces to compare evidence, never replace printed front gender."""
from .national_serial import pairing_number
from .mrz import parse


def back_gender(back):
    # Cached OCR is not evidence for an edited image.
    if back.get('field_image_id',back['image_id'])!=back['image_id']:return None
    machine=parse([line['text'] for line in back.get('ocr',[])])
    if machine and machine['valid'] and machine['lines'][1][7] in 'MF':
        return {'value':'ذكر' if machine['lines'][1][7]=='M' else 'أنثى','confidence':.8}
    # Compatibility with previously saved, explicitly checked MRZ evidence.
    return next((f for f in back.get('fields',[]) if f.get('key')=='sex' and f.get('method')=='mrz_checked_syntax'
                 and f.get('value') in ['ذكر','أنثى']),None)


def reconcile(documents):
    buckets={}
    for d in documents:
        if d.get('kind')!='national_id' or d.get('side') not in ['front','back']:continue
        number=pairing_number(d)
        if number:buckets.setdefault(number,[]).append(d)
    for docs in buckets.values():
        if len(docs)!=2 or {d['side'] for d in docs}!={'front','back'}:continue
        front=next(d for d in docs if d['side']=='front');back=next(d for d in docs if d['side']=='back')
        if front.get('reviewed'):continue
        source=back_gender(back)
        if not source:continue
        target=next((f for f in front['fields'] if f.get('key')=='sex'),None)
        if target is None:
            from .understanding import field
            target=field('sex');front['fields'].append(target)
        if target.get('verified') or target.get('method')=='manual' or target.get('status')=='manual':continue
        if target.get('value')==source['value']:continue
        candidates=target.setdefault('candidates',[])
        candidate={'value':source['value'],'engine':'paired_mrz','confidence':source['confidence']}
        if candidate not in candidates:candidates.append(candidate)
        if target.get('value'):
            target['status']='conflict'
            target['note']='اختلفت قراءة الجنس المطبوع في الأمام عن الشريط الآلي للوجه المطابق؛ راجع الوجهين.'
        else:
            target['note']='الجنس يُقرأ من الوجه الأمامي. يعرض الشريط الخلفي اقتراحًا للمقارنة فقط؛ لم يُملأ الحقل منه.'
