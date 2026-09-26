"""Conservative grouping of multiple documents, independent of upload order."""
from .national_serial import pairing_number

def group_documents(documents):
    used={d.get('group') for d in documents if d.get('group')};counter=0
    def assign(ds,reason,method='auto',name=None,pairing=None):
        nonlocal counter
        if name is None or name in used:
            while True:
                counter+=1;name=f'مجموعة {counter:02}'
                if name not in used:break
        used.add(name)
        for d in ds:
            d.update(group=name,group_reason=reason,group_method=method)
            if pairing:d['pairing']=dict(pairing)
    national={}
    for d in documents:
        if d.get('kind')=='national_id':
            serial=pairing_number(d)
            if serial:national.setdefault(serial,[]).append(d)
    for serial,ds in national.items():
        if len(ds)==2 and {d['side'] for d in ds}=={'front','back'} and not any(d.get('group') for d in ds):
            front=next(d for d in ds if d['side']=='front');back=next(d for d in ds if d['side']=='back')
            reason=f'تطابق رقم البطاقة {serial} أسفل الصورة مع الرقم في السطر الآلي الخلفي. راجع الوجهين قبل الاعتماد.'
            assign(ds,reason,'national_serial',f'موحدة · {serial}',{'status':'matched','number':serial,'front_id':front['id'],'back_id':back['id']})
    # Other document types keep their existing same-page or exact-number rules.
    def number(d):
        v=next((str(f.get('value','')).strip().upper() for f in d.get('fields',[]) if f.get('key')=='document_number'),'')
        return v if len(v)>=6 else None
    def buckets(key):
        result={}
        for d in documents:
            if d.get('group') or d.get('kind') in ['unknown','national_id']:continue
            k=key(d)
            if k is not None:result.setdefault(k,[]).append(d)
        return result.values()
    for ds in buckets(lambda d:(d['kind'],number(d)) if number(d) else None):
        if len(ds)==2 and {d['side'] for d in ds}=={'front','back'}:assign(ds,'اقتراح لتطابق رقم البطاقة المقروء على الوجهين؛ يحتاج مراجعة.')
    for ds in buckets(lambda d:(d['source_id'],d['kind'])):
        numbers={number(d) for d in ds if number(d)}
        if len(ds)==2 and {d['side'] for d in ds}=={'front','back'} and len(numbers)<=1:assign(ds,'اقتراح وجهين من المصدر نفسه؛ راجع أنهما يعودان للمستمسك نفسه.')
    for d in documents:
        if d.get('group'):continue
        if d.get('kind')=='national_id':
            serial=pairing_number(d);count=len(national.get(serial,[])) if serial else 0
            status='ambiguous' if count>1 else 'unmatched' if serial else 'unreadable'
            reason={'ambiguous':'الرقم مكرر بين عدة أوجه؛ يلزم تحديد الزوج يدويًا.',
                    'unmatched':'لا يوجد وجه مقابل يحمل رقم البطاقة نفسه.',
                    'unreadable':'رقم البطاقة أو رقم التحقق غير مقروء بثقة؛ أعد القراءة أو راجع الرقم.'}[status]
            assign([d],reason,'national_serial',pairing={'status':status,'number':serial})
        else:assign([d],'مجموعة مستقلة؛ يمكن دمجها بعد المراجعة.')

def regroup_national(documents):
    protected={d.get('group') for d in documents if d.get('reviewed') or d.get('group_method')=='manual'}
    for d in documents:
        if d.get('kind')=='national_id' and not d.get('reviewed') and d.get('group') not in protected:
            d['group']='';d.pop('pairing',None)
    group_documents(documents)


def invalidate_pairing(documents,changed_id):
    for d in documents:
        p=d.get('pairing',{})
        if p and (d['id']==changed_id or changed_id in [p.get('front_id'),p.get('back_id')]):
            d['pairing']={'status':'needs_recheck','number':None}
            d['group_reason']='تغيّر رقم البطاقة أو نوع الوجه؛ أعد مطابقة الأوجه لتحديث الربط.'
