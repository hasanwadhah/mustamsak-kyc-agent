"""Explainable local address suggestions, separated from observed document text."""
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
import json
import re


@lru_cache(maxsize=1)
def reference():
    return json.loads((Path(__file__).resolve().parents[1]/'research'/'iraqi_address_reference.json').read_text(encoding='utf-8'))


def compact(text):
    from .focused_fields import normalize
    return re.sub(r'[^\u0621-\u064a]', '', normalize(text))


def enrich_housing(fields):
    from .focused_fields import normalize
    from .understanding import field
    address=fields.get('address',{})
    text=normalize(address.get('value',''))
    provinces=[name for name in reference()['governorates']
               if re.search(r'(?<![\u0621-\u064a])'+re.escape(normalize(name))+r'(?![\u0621-\u064a])',text)]
    if len(provinces)==1:
        fields['governorate']=field('governorate',provinces[0],address.get('confidence'),address.get('box'),
                                    'address_text','approximate',approximate=True,raw_text=address.get('raw_text',text),
                                    note='اسم محافظة مذكور في سطر العنوان؛ راجع سياقه قبل الاعتماد.')
    office=fields.get('information_office',{})
    mahalla=fields.get('mahalla_number',{})
    raw=office.get('raw_text',office.get('value',''))
    # Every reading of the office handwriting, whole and word by word.
    readings=[raw,office.get('value','')]+[c.get('value','') for c in office.get('candidates',[]) if c.get('engine')!='local_geography']
    pieces={compact(r) for r in readings if r}|{compact(w) for r in readings if r for w in str(r).split()}
    pieces={p for p in pieces if len(p)>=5}
    matches=[]
    for area in reference()['areas']:
        similarity=max((SequenceMatcher(None,p,compact(area['name'])).ratio() for p in pieces),default=0)
        if (mahalla.get('value') in area['mahallas'] and similarity>=.72
                and mahalla.get('status')!='conflict'
                and (not provinces or provinces==[area['governorate']])):
            matches.append((area,similarity))
    if len(matches)==1 and office.get('status')!='manual' and not office.get('verified'):
        area,similarity=matches[0]
        evidence={'title':area['source_title'],'url':area['source_url'],'observation_year':area['observation_year']}
        candidate={'value':area['name'],'confidence':None,'engine':'local_geography','source':evidence,
                   'similarity':round(similarity,3),'note':'اقتراح من تشابه اسم المكتب واتفاق رقم المحلة؛ ليس قراءة حرفية جديدة.'}
        office.setdefault('candidates',[]).insert(0,candidate)
        office['note']=office.get('note','')+' اقتراح اسم المكتب: '+area['name']+'؛ تؤيده المحلة المقروءة في المرجع المحلي. راجع الاقتراح قبل استخدامه.'
        for key,value in [('neighborhood',area['name']),('governorate',area['governorate'])]:
            if fields.get(key,{}).get('value'):continue
            fields[key]=field(key,value,None,method='local_geography',status='approximate',approximate=True,
                              source=evidence,raw_text=raw,
                              note='استدلال تقريبي من اسم مكتب المعلومات ورقم المحلة مع مرجع منشور؛ لا يثبت الإقامة الحالية ولا يُعتمد تلقائيًا.')
    check_baghdad_side(fields)
    suggest_mahalla_area(fields)
    components=[fields.get(k,{}) for k in ('mahalla_number','street','house_number')]
    if all(f.get('value') for f in components) and any(f.get('method') in ('housing_ink_components','eastern_digit_model','address_layout') or f.get('agreement') for f in components):
        value=' — '.join(label+' '+f['value'] for label,f in zip(('م','ز','د'),components))
        status='conflict' if any(f.get('status')=='conflict' for f in components) else 'approximate'
        fields['address']=field('address',value,None,address.get('box'),'assembled_address_symbols',status,
                                approximate=True,raw_text=address.get('raw_text',address.get('value','')),
                                note='مجمّع من الرموز المرئية: م = محلة، ز = زقاق، د = دار. راجع البدائل في كل رقم، خاصة الصفر المكتوب كنقطة.')


def office_side(fields):
    """The Baghdad side named by the information-office reading, when exactly one side matches.

    Only readings of the handwriting count; a geography suggestion made from the mahalla
    itself would make the check circular.
    """
    sides=reference().get('baghdad_sides')
    office=fields.get('information_office') or {}
    readings=[office.get('value','')]+[c.get('value','') for c in office.get('candidates',[]) if c.get('engine')!='local_geography']
    readings=[compact(r) for r in readings if r]
    found={side for side,names in (sides or {}).get('offices',{}).items()
           for name in names if compact(name) and any(compact(name) in r for r in readings)}
    return found.pop() if len(found)==1 else None


def check_baghdad_side(fields):
    """Flag a mahalla whose even/odd number contradicts the office's side of Baghdad.

    In Baghdad even mahallas are Rusafa and odd ones Karkh (reference: baghdad_sides).
    A contradiction means one of the two readings is wrong; the digit is never changed,
    but readings that fit the office are listed first as suggestions.
    """
    sides=reference().get('baghdad_sides')
    mahalla=fields.get('mahalla_number') or {}
    value=str(mahalla.get('value') or '')
    side=office_side(fields) if sides else None
    if not side or not value.isdigit() or mahalla.get('verified') or 'manual' in (mahalla.get('method'),mahalla.get('status')):
        return
    parity=lambda number:sides['even'] if int(number)%2==0 else sides['odd']
    expected=parity(value)
    mahalla['baghdad_side']={'office':side,'mahalla':expected,'consistent':side==expected}
    if side==expected:
        return
    mahalla.update(status='conflict',approximate=True,
                   note=(mahalla.get('note','')+f' رقم المحلة {value} {"زوجي" if int(value)%2==0 else "فردي"} أي في جانب {expected}، '
                         f'لكن مكتب المعلومات في جانب {side}. إحدى القراءتين خطأ؛ راجع الرقم الأخير مع الصورة.').strip())
    fits=lambda c:str(c.get('value','')).isdigit() and parity(c['value'])==side
    mahalla['candidates']=sorted(mahalla.get('candidates') or [],key=lambda c:not fits(c))


def mahalla_area(number):
    """The row of the owner's Baghdad mahalla table that lists this mahalla, or None."""
    for row in (reference().get('baghdad_mahallas') or {}).get('rows',[]):
        if str(number) in row['mahallas']:return row
    return None


def suggest_mahalla_area(fields):
    """Offer the area of a read mahalla as a one-click suggestion; the field stays empty.

    The table is owner-provided and incomplete, so an unlisted mahalla means nothing,
    and a listed one is only as reliable as the digits that were read.
    """
    from .understanding import field
    mahalla=fields.get('mahalla_number') or {}
    value=str(mahalla.get('value') or '')
    row=mahalla_area(value) if value.isdigit() else None
    if not row:return
    mahalla['area_hint']={k:row[k] for k in ('area','municipality','side')}
    hood=fields.get('neighborhood') or {}
    if hood.get('value') or hood.get('verified') or 'manual' in (hood.get('method'),hood.get('status')):return
    note=(f'المحلة المقروءة {value} تقع حسب جدول المحلات المحلي في: {row["area"]} — {row["municipality"]}، جانب {row["side"]}. '
          'اقتراح فقط، وهو صحيح بقدر صحة رقم المحلة؛ تأكد من الرقم أولًا.')
    fields['neighborhood']=field('neighborhood','',None,mahalla.get('box'),'owner_mahalla_table','missing',note=note,
                                 candidates=[{'value':row['area'],'confidence':None,'engine':'owner_mahalla_table','note':note}])
