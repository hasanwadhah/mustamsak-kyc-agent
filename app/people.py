"""Local person folders and auditable, provisional household suggestions.

The index stores document references and user decisions. Extracted identity and
address values are always read from the current document, never copied into a
second stale record. A name match is not proof of kinship or co-residence.
"""
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import re

from . import storage
from .national_serial import pairing_number

RELATIONS = {'owner': 'مستمسك الشخص', 'father_household': 'سكن باسم الأب / الأسرة',
             'household': 'مستمسك الأسرة', 'supporting': 'مستمسك مرفق'}
ADDRESS_KEYS = {'address', 'governorate', 'district', 'neighborhood', 'mahalla_number', 'street', 'house_number'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalize_name(value):
    value = str(value).translate(str.maketrans('أإآٱى', 'ااااي')).lower()
    value = re.sub('[\u064b-\u065f\u0670\u0640]', '', value)
    value = re.sub(r'[^\w\s]', ' ', value, flags=re.UNICODE)
    # Treat the common spaced/unspaced spelling as one name component.
    value = re.sub(r'\bعبد\s+(الله|الرحمن|الرحيم|الكريم|الحسين|الحسن|الامير|الرزاق|القادر|الوهاب)\b', r'عبد\1', value)
    return ' '.join(value.split())


def fields(doc):
    return {f['key']: f for f in doc.get('fields', [])}


def readable(field):
    return bool(field.get('value')) and (field.get('verified') or field.get('status') == 'read')


def full_name(doc):
    fs = fields(doc)
    direct = fs.get('name', {})
    if direct.get('value') and direct.get('method') != 'assembled_visible_names':
        return direct
    parts = [fs.get(k, {}) for k in ('first_name', 'father_name', 'grandfather_name', 'surname')]
    if all(p.get('value') for p in parts):
        return {'key': 'name', 'label': 'الاسم الكامل', 'value': ' '.join(p['value'] for p in parts),
                'verified': all(p.get('verified') for p in parts),
                'status': 'read' if all(readable(p) for p in parts) else 'uncertain'}
    return {}


def identity_keys(doc):
    result = set()
    serial = pairing_number(doc)
    if serial:
        result.add('serial:' + serial)
    national = fields(doc).get('national_number', {})
    digits = str(national.get('value', '')).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    if readable(national) and re.fullmatch(r'\d{12}', digits):
        result.add('national:' + digits)
    return result


def ref_of(bid, did):
    return f'{bid}:{did}'


def load_index():
    path = storage.DATA / 'people.json'
    if not path.exists():
        return {'version': 1, 'mode': 'manual', 'people': []}
    return json.loads(path.read_text(encoding='utf-8'))


def save_index(index):
    storage.atomic_write(storage.DATA / 'people.json', json.dumps(index, ensure_ascii=False, indent=2))


def catalog():
    documents = {}
    for summary in reversed(storage.list_batches()):
        if summary['status'] in ('queued', 'processing'):
            continue
        batch = storage.get_batch(summary['id'])
        for doc in batch['documents']:
            ref = ref_of(batch['id'], doc['id'])
            documents[ref] = {'ref': ref, 'batch_id': batch['id'], 'batch_name': batch['name'], 'batch_created': batch['created'], 'document': doc,
                              'fingerprint': digest([doc.get('kind'), doc.get('side'), doc.get('fields'), doc.get('image_id')])}
    return documents


def can_seed(item):
    d = item['document']
    name = full_name(d).get('value', '')
    return d['kind'] == 'national_id' and d['side'] == 'front' and len(normalize_name(name).split()) >= 2


def compatible_keys(a, b):
    ka, kb = identity_keys(a), identity_keys(b)
    if not ka.intersection(kb):
        return False
    for prefix in ('national:', 'serial:'):
        left, right = {k for k in ka if k.startswith(prefix)}, {k for k in kb if k.startswith(prefix)}
        if left and right and left != right:
            return False
    return True


def same_identity(a, b):
    if not identity_keys(a).intersection(identity_keys(b)):
        return False
    # Equal numbers with conflicting names or national numbers are not merged.
    na, nb = normalize_name(full_name(a).get('value', '')), normalize_name(full_name(b).get('value', ''))
    if not na or na != nb:
        return False
    for prefix in ('national:', 'serial:'):
        ka = {k for k in identity_keys(a) if k.startswith(prefix)}
        kb = {k for k in identity_keys(b) if k.startswith(prefix)}
        if ka and kb and ka != kb:
            return False
    ba, bb = fields(a).get('birth_date', {}), fields(b).get('birth_date', {})
    return not (readable(ba) and readable(bb) and ba['value'] != bb['value'])


def synchronize(index, docs):
    previous = digest(index)
    # Preserve a folder's ID while its primary ID document still exists.
    kept = []
    assigned = set()
    for person in index['people']:
        seeds = [r for r in person['seeds'] if r in docs and docs[r]['document']['kind'] == 'national_id' and docs[r]['document']['side'] == 'front']
        if seeds:
            seeds = [r for r in seeds if r == seeds[0] or same_identity(docs[seeds[0]]['document'], docs[r]['document'])]
        person['seeds'] = seeds
        person['links'] = [l for l in person.get('links', []) if l['ref'] in docs]
        person['ignored'] = {r: v for r, v in person.get('ignored', {}).items() if r in docs}
        if seeds or person['links'] or person.get('notes') or person.get('display_name'):
            kept.append(person)
            assigned.update(seeds)
    index['people'] = kept
    for ref, item in docs.items():
        if ref in assigned or not can_seed(item):
            continue
        matches = [p for p in kept if p['seeds'] and same_identity(docs[p['seeds'][0]]['document'], item['document'])]
        if len(matches) == 1:
            matches[0]['seeds'].append(ref)
        else:
            kept.append({'id': storage.uid(), 'created': datetime.now(timezone.utc).isoformat(),
                         'seeds': [ref], 'links': [], 'ignored': {}, 'notes': '', 'display_name': ''})
        assigned.add(ref)
    if digest(index) != previous:
        save_index(index)


def name_match(identity, housing):
    person_name, head = full_name(identity), fields(housing).get('name', {})
    target = normalize_name(head.get('value', ''))
    if len(target.split()) < 3:
        return None
    fs = fields(identity)
    candidates = [(normalize_name(person_name.get('value', '')), 'owner', 'الاسم الكامل في الموحدة يشابه اسم رب الأسرة')]
    father_parts = [fs.get(k, {}) for k in ('father_name', 'grandfather_name', 'surname')]
    if all(p.get('value') for p in father_parts):
        candidates.append((normalize_name(' '.join(p['value'] for p in father_parts)), 'father_household', 'اسم الأب والجد واللقب في الموحدة يشابه اسم رب الأسرة'))
    tokens = normalize_name(person_name.get('value', '')).split()
    if len(tokens) >= 4:
        candidates.append((' '.join(tokens[1:]), 'father_household', 'اسم رب الأسرة يطابق تسلسل الأسماء بعد الاسم الأول في الموحدة'))
    matches = []
    for expected, relation, reason in candidates:
        a, b = expected.split(), target.split()
        if len(a) < 3 or len(a) != len(b):
            continue
        exact = expected == target
        # Only a single near-spelling difference qualifies as a suggestion.
        differences = [(x, y) for x, y in zip(a, b) if x != y]
        near = len(differences) == 1 and SequenceMatcher(None, *differences[0]).ratio() >= .75 and SequenceMatcher(None, expected, target).ratio() >= .92
        if exact or near:
            reliable = readable(person_name) and readable(head)
            if relation == 'father_household' and all(p.get('value') for p in father_parts):
                reliable = reliable and all(readable(p) for p in father_parts)
            matches.append({'relationship': relation, 'exact': exact, 'reliable': bool(reliable),
                            'expected_name': expected, 'head_name': head['value'],
                            'reason': reason if exact else 'تشابه جزئي في تهجئة الأسماء؛ يحتاج اختيارًا يدويًا'})
    return sorted(matches, key=lambda m: (m['exact'], m['reliable'], m['relationship'] == 'owner'), reverse=True)[0] if matches else None


def world():
    # Caller holds storage.LOCK through reads and any resulting mutation.
    index, docs = load_index(), catalog()
    synchronize(index, docs)
    revision = digest([index, {r: d['fingerprint'] for r, d in docs.items()}])
    return index, docs, revision


def signature(person, item, docs):
    return digest([[docs[r]['fingerprint'] for r in person['seeds']], item['fingerprint']])


def proposals(index, docs):
    result = {p['id']: [] for p in index['people']}
    for ref, item in docs.items():
        housing = item['document']
        if housing['kind'] != 'housing' or housing['side'] not in ('front', 'page', 'unknown'):
            continue
        matches = []
        for p in index['people']:
            if not p['seeds']:
                continue
            match = name_match(docs[p['seeds'][0]]['document'], housing)
            if match:
                matches.append((p, match))
        for p, match in matches:
            sig = signature(p, item, docs)
            if p.get('ignored', {}).get(ref) == sig:
                continue
            if any(l['ref'] == ref for l in p.get('links', [])):
                continue
            result[p['id']].append(dict(match, ref=ref, signature=sig,
                candidate_count=len(matches), automatic_eligible=match['exact'] and match['reliable'] and len(matches) == 1,
                batch_id=item['batch_id'], batch_name=item['batch_name'], document=deepcopy(housing)))
    return result


def members(person, index, docs, suggestions):
    entries = {}
    def add(ref, relationship, method, confirmed, stale=False):
        if ref in docs:
            entries[ref] = dict(deepcopy(docs[ref]), relationship=relationship, relationship_label=RELATIONS[relationship],
                                method=method, confirmed=confirmed, needs_review=bool(stale or not confirmed))
    for ref in person['seeds']:
        add(ref, 'owner', 'national_id', True)
    for ref, item in docs.items():
        d = item['document']
        if d['kind'] != 'national_id' or d['side'] != 'back' or not any(compatible_keys(docs[r]['document'], d) for r in person['seeds']):
            continue
        owners = [p for p in index['people'] if any(compatible_keys(docs[r]['document'], d) for r in p['seeds'])]
        if len(owners) == 1 and person.get('ignored', {}).get(ref) != signature(person, item, docs):
            add(ref, 'owner', 'national_serial', True)
    if index['mode'] == 'auto':
        for proposal in suggestions:
            if proposal['automatic_eligible']:
                add(proposal['ref'], proposal['relationship'], 'auto_name', False)
    for link in person.get('links', []):
        stale = link['signature'] != signature(person, docs[link['ref']], docs)
        add(link['ref'], link['relationship'], 'manual', not stale, stale)
    return list(entries.values())


def recommended_documents(linked):
    # Repeated uploads remain visible. Prefer one copy per exact national-card
    # serial and side for printing, never deduplicate by a person's name.
    groups = {}
    for item in linked:
        d = item['document']
        serial = pairing_number(d) if d['kind'] == 'national_id' else None
        key = (d['kind'], d['side'], serial or d['image_id'])
        groups.setdefault(key, []).append(item)
    selected = []
    for items in groups.values():
        preferred = max(items, key=lambda e: (bool(e['document'].get('reviewed')),
            sum(bool(f.get('value')) and readable(f) for f in e['document'].get('fields', [])), e['batch_created']))
        selected.append(preferred['ref'])
    return selected


def view(person, index, docs, revision, all_proposals=None):
    suggested = (all_proposals or proposals(index, docs))[person['id']]
    linked = members(person, index, docs, suggested)
    from .print_layout import person_print_group
    linked=[dict(e,print_group=person_print_group(e)) for e in linked]
    identity = docs[person['seeds'][0]]['document'] if person['seeds'] else None
    name = full_name(identity).get('value', '') if identity else ''
    identity_fields = []
    seen = {}
    conflicts = []
    for item in linked:
        if item['document']['kind'] != 'national_id' or item['relationship'] != 'owner' or item['needs_review']:
            continue
        for f in item['document'].get('fields', []):
            if f['key'] == 'name':
                f = full_name(item['document'])
            if not f.get('value'):
                continue
            field = dict(deepcopy(f), source_ref=item['ref'], batch_id=item['batch_id'], document_id=item['document']['id'])
            if f['key'] not in seen:
                seen[f['key']] = field
                identity_fields.append(field)
            elif str(seen[f['key']]['value']) != str(f['value']):
                conflicts.append({'key': f['key'], 'label': f['label'], 'values': [seen[f['key']], field]})
    housing = []
    for item in linked:
        if item['document']['kind'] == 'housing' and item['document']['side'] != 'back':
            fs = fields(item['document'])
            housing.append({'ref': item['ref'], 'head_name': fs.get('name', {}).get('value', ''),
                            'relationship': item['relationship'], 'relationship_label': item['relationship_label'],
                            'confirmed': item['confirmed'], 'needs_review': item['needs_review'],
                            'fields': [deepcopy(f) for f in fs.values() if f['key'] in ADDRESS_KEYS and f.get('value')]})
    return {'id': person['id'], 'created': person['created'], 'name': person.get('display_name') or name or 'ملف بحاجة إلى بطاقة موحدة',
            'extracted_name': name, 'display_name': person.get('display_name', ''), 'notes': person.get('notes', ''),
            'revision': revision, 'mode': index['mode'], 'fields': identity_fields, 'conflicts': conflicts,
            'documents': linked, 'housing': housing, 'suggestions': suggested,
            'needs_review': not identity or not readable(full_name(identity)) or bool(conflicts) or any(e['needs_review'] or not e['document'].get('reviewed') for e in linked),
            'seed_refs': person['seeds'], 'recommended_refs': recommended_documents(linked),
            'duplicate_count': len(linked) - len(recommended_documents(linked))}


def find_person(index, pid):
    return next((p for p in index['people'] if p['id'] == pid), None)
