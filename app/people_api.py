from .print_layout import PrintOptions, manual_sheets, person_print_group
from copy import deepcopy
import io
import json
from typing import Literal
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import people, storage, export

router = APIRouter(prefix='/api/people')


def state_for(pid=None, revision=None):
    try:
        index, docs, current = people.world()
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'تعذرت قراءة ملفات الأشخاص. تحقق من ملفات الحفظ المحلية.')
    if revision is not None and revision != current:
        raise HTTPException(409, 'تغيّرت البيانات أو المستمسكات. حدّث ملف الشخص وراجع الاختيار قبل المحاولة مجددًا.')
    person = people.find_person(index, pid) if pid else None
    if pid and person is None:
        raise HTTPException(404, 'ملف الشخص غير موجود.')
    return index, docs, current, person


@router.get('')
def list_people():
    with storage.LOCK:
        index, docs, revision, _ = state_for()
        proposals = people.proposals(index, docs)
        results = []
        for p in index['people']:
            v = people.view(p, index, docs, revision, proposals)
            results.append({k: v[k] for k in ('id', 'name', 'extracted_name', 'created', 'needs_review')} |
                           {'document_count': len(v['documents']), 'suggestion_count': len(v['suggestions']),
                            'batch_ids': list({e['batch_id'] for e in v['documents']}),
                            'national_number': next((f['value'] for f in v['fields'] if f['key'] == 'national_number'), '')})
        missing = sum(d['document']['kind'] == 'national_id' and d['document']['side'] == 'front' and not people.can_seed(d) for d in docs.values())
        return {'people': results, 'mode': index['mode'], 'revision': revision, 'missing_names': missing}


class Mode(BaseModel):
    mode: Literal['manual', 'auto']


@router.patch('/settings')
def mode(body: Mode):
    with storage.LOCK:
        index, _, _, _ = state_for()
        index['mode'] = body.mode
        people.save_index(index)
        return {'mode': index['mode']}


@router.get('/{pid}')
def detail(pid: str):
    with storage.LOCK:
        index, docs, revision, p = state_for(pid)
        return people.view(p, index, docs, revision)


@router.get('/{pid}/kyc')
def person_kyc(pid: str, profile: Literal['auto', 'individual', 'merchant'] = 'auto'):
    from . import kyc
    with storage.LOCK:
        index, docs, revision, p = state_for(pid)
        v = people.view(p, index, docs, revision)
        result = kyc.assess_documents([e['document'] for e in v['documents'] if not e['needs_review'] or e['relationship'] == 'owner'], profile)
        return result | {'person_id': pid, 'revision': revision}


@router.get('/{pid}/available')
def available(pid: str):
    with storage.LOCK:
        index, docs, revision, p = state_for(pid)
        v = people.view(p, index, docs, revision)
        existing = {e['ref'] for e in v['documents']}
        # ID fronts are already anchors of their own folder. Do not silently
        # move one person's identity into another folder through attachments.
        return {'revision': revision, 'documents': [d for r, d in docs.items() if r not in existing and not people.can_seed(d)]}


class Revision(BaseModel):
    revision: str = Field(min_length=64, max_length=64)


class PersonUpdate(Revision):
    display_name: str = Field(default='', max_length=160)
    notes: str = Field(default='', max_length=3000)


@router.patch('/{pid}')
def update(pid: str, body: PersonUpdate):
    with storage.LOCK:
        index, docs, _, p = state_for(pid, body.revision)
        p['display_name'], p['notes'] = body.display_name.strip(), body.notes.strip()
        people.save_index(index)
        index, docs, revision, p = state_for(pid)
        return people.view(p, index, docs, revision)


class Links(Revision):
    refs: list[str] = Field(min_length=1, max_length=100)
    relationship: Literal['owner', 'father_household', 'household', 'supporting'] = 'supporting'


@router.post('/{pid}/links')
def attach(pid: str, body: Links):
    with storage.LOCK:
        index, docs, _, p = state_for(pid, body.revision)
        refs = set(body.refs)
        for ref in refs:
            if ref not in docs:
                raise HTTPException(404, 'أحد المستمسكات لم يعد موجودًا.')
            if people.can_seed(docs[ref]) and ref not in p['seeds']:
                raise HTTPException(409, 'لهذا الوجه الأمامي ملف شخص مستقل؛ راجعه من قائمة ملفات الأشخاص.')
            if body.relationship == 'father_household' and docs[ref]['document']['kind'] != 'housing':
                raise HTTPException(422, 'اختر علاقة السكن باسم الأب لبطاقة سكن فقط.')
        for ref in refs:
            if ref in p['seeds']:
                continue
            p['links'] = [l for l in p['links'] if l['ref'] != ref]
            p['links'].append({'ref': ref, 'relationship': body.relationship, 'signature': people.signature(p, docs[ref], docs)})
            p['ignored'].pop(ref, None)
        people.save_index(index)
        index, docs, revision, p = state_for(pid)
        return people.view(p, index, docs, revision)


@router.delete('/{pid}/links')
def detach(pid: str, body: Links):
    with storage.LOCK:
        index, docs, _, p = state_for(pid, body.revision)
        for ref in body.refs:
            if ref not in docs:
                raise HTTPException(404, 'المستمسك لم يعد موجودًا.')
            if ref in p['seeds']:
                raise HTTPException(409, 'هذه الموحدة هي أساس الملف. يمكنك حذف المستمسك من دفعته عند الحاجة.')
        for ref in body.refs:
            p['links'] = [l for l in p['links'] if l['ref'] != ref]
            p['ignored'][ref] = people.signature(p, docs[ref], docs)
        people.save_index(index)
        index, docs, revision, p = state_for(pid)
        return people.view(p, index, docs, revision)


class PersonExport(Revision, PrintOptions):
    refs: list[str] | None = Field(default=None, max_length=800)
    format: Literal['pdf', 'zip', 'json'] = 'pdf'
    allow_unreviewed: bool = False


@router.post('/{pid}/export')
def export_person(pid: str, body: PersonExport):
    with storage.LOCK:
        index, docs, revision, p = state_for(pid, body.revision)
        v = people.view(p, index, docs, revision)
        by_ref = {e['ref']: e for e in v['documents']}
        refs = list(dict.fromkeys(body.refs)) if body.refs is not None else v['recommended_refs']
        if not refs:
            raise HTTPException(422, 'اختر مستمسكًا واحدًا على الأقل للتصدير.')
        if any(r not in by_ref for r in refs):
            raise HTTPException(409, 'تغيّر محتوى الملف؛ حدّث الاختيار قبل التصدير.')
        entries = [by_ref[r] for r in refs]
        if not body.allow_unreviewed and (v['conflicts'] or any(e['needs_review'] or not e['document'].get('reviewed') for e in entries)):
            raise HTTPException(409, 'راجع المستمسكات والروابط أولًا، أو فعّل تصدير المسودة صراحةً.')
        documents = []
        print_documents = {}
        for e in sorted(entries, key=lambda e: (e['document']['kind'] != 'national_id', e['document']['kind'] != 'housing', e['document'].get('order', 0))):
            d = deepcopy(e['document'])
            # Group the national card across uploads by its serial. Other
            # group names are only unique within a batch.
            d['group'] = person_print_group(e)
            documents.append(d)
            print_documents[e['ref']] = d
        try:
            sheets = manual_sheets(body.pages, body.layout, print_documents)
        except ValueError as error:
            raise HTTPException(422, str(error))
        profile = {k: v[k] for k in ('id', 'name', 'extracted_name', 'notes')}
        profile['relationships'] = [{k: e[k] for k in ('ref', 'relationship', 'confirmed', 'needs_review')} for e in entries]
        profile['note'] = 'ارتباط بطاقة السكن بالملف لا يثبت القرابة أو الإقامة الحالية.'
        if body.format == 'pdf':
            data, mime = export.export_pdf(documents, body.layout, body.size, sheets), 'application/pdf'
        elif body.format == 'zip':
            stream = io.BytesIO(export.export_zip(documents, body.layout, body.size, sheets))
            with zipfile.ZipFile(stream, 'a', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('person.json', json.dumps(profile, ensure_ascii=False, indent=2))
            data, mime = stream.getvalue(), 'application/zip'
        else:
            data = json.dumps({'person': profile, 'documents': documents}, ensure_ascii=False, indent=2).encode('utf-8')
            mime = 'application/json'
        return Response(data, media_type=mime, headers={'Content-Disposition': f'attachment; filename="person-{pid[:8]}.{body.format}"'})
