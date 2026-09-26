from copy import deepcopy
import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main, pipeline, storage, vision


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for folder in ('batches', 'images', 'exports'):
        (tmp_path / folder).mkdir()
    with TestClient(main.app) as c:
        yield c


def field(key, value, verified=True):
    return {'key': key, 'label': key, 'value': value, 'verified': verified,
            'status': 'manual' if verified else 'uncertain', 'method': 'manual', 'confidence': None}


def add_doc(kind, side, values, batch=None):
    b = batch or pipeline.new_batch('ملفات تجريبية')
    b['status'] = 'ready'
    iid = storage.uid()
    vision.save_image(storage.image_path(iid), np.full((100, 200, 3), 220, np.uint8))
    b['sources'].append({'id': iid, 'name': 'synthetic.png', 'page': 1, 'width': 200, 'height': 100})
    d = {'id': storage.uid(), 'source_id': iid, 'image_id': iid, 'original_id': iid,
         'kind': kind, 'side': side, 'fields': [field(k, v) for k, v in values.items()],
         'group': 'test', 'group_reason': '', 'reviewed': True, 'source_name': 'synthetic.png',
         'page': 1, 'order': len(b['documents']), 'width': 200, 'height': 100, 'ocr': [], 'notices': [], 'evidence': []}
    b['documents'].append(d)
    storage.save_batch(b)
    return b, d, f'{b["id"]}:{d["id"]}'


def sample(client):
    b, d, ref = add_doc('national_id', 'front', {'name': 'محمد حسين حسن علي', 'document_number': 'AB1234567', 'national_number': '123456789012'})
    h, hd, hr = add_doc('housing', 'front', {'name': 'حسين حسن علي', 'address': 'بغداد - المنصور', 'neighborhood': 'المنصور'})
    pid = client.get('/api/people').json()['people'][0]['id']
    return b, d, ref, h, hd, hr, pid


def detail(client, pid):
    response = client.get('/api/people/'+pid)
    assert response.status_code == 200
    return response.json()


def test_person_created_once_and_back_linked_across_batches(client):
    b, d, ref, _, _, _, pid = sample(client)
    _, _, back = add_doc('national_id', 'back', {'document_number': 'AB1234567', 'birth_date': '1998/09/23', 'sex': 'ذكر'})
    p = detail(client, pid)
    assert {e['ref'] for e in p['documents']} == {ref, back}
    assert any(f['key'] == 'birth_date' and f['value'] == '1998/09/23' for f in p['fields'])
    assert client.get('/api/people').json()['people'][0]['id'] == pid
    duplicate = deepcopy(b)
    duplicate['id'] = storage.uid()
    storage.save_batch(duplicate)
    assert len(client.get('/api/people').json()['people']) == 1
    # Names are not persistent duplicate identity records in people.json.
    assert 'محمد' not in (storage.DATA/'people.json').read_text(encoding='utf-8')


def test_father_household_suggested_then_manually_added(client):
    _, _, _, _, _, hr, pid = sample(client)
    p = detail(client, pid)
    proposal = p['suggestions'][0]
    assert proposal['relationship'] == 'father_household' and proposal['automatic_eligible']
    assert not p['housing']
    response = client.post(f'/api/people/{pid}/links', json={'revision': p['revision'], 'refs': [hr], 'relationship': 'father_household'})
    assert response.status_code == 200
    p = response.json()
    assert p['housing'][0]['confirmed']
    assert p['housing'][0]['head_name'] == 'حسين حسن علي'
    assert p['extracted_name'] == 'محمد حسين حسن علي'
    assert not any(f['key'] == 'address' for f in p['fields'])
    assert p['suggestions'] == []


def test_automatic_mode_is_provisional_and_can_be_dismissed(client):
    _, _, _, _, _, hr, pid = sample(client)
    assert client.patch('/api/people/settings', json={'mode': 'auto'}).status_code == 200
    p = detail(client, pid)
    link = next(e for e in p['documents'] if e['ref'] == hr)
    assert link['method'] == 'auto_name' and link['needs_review'] and not link['confirmed']
    assert client.post(f'/api/people/{pid}/export', json={'revision': p['revision']}).status_code == 409
    response = client.request('DELETE', f'/api/people/{pid}/links', json={'refs': [hr], 'revision': p['revision']})
    assert response.status_code == 200
    assert not detail(client, pid)['housing']
    assert not detail(client, pid)['suggestions']


def test_siblings_and_duplicate_names_require_manual_choice(client):
    _, _, _, _, _, _, pid = sample(client)
    add_doc('national_id', 'front', {'name': 'احمد حسين حسن علي', 'document_number': 'AC1234567'})
    client.patch('/api/people/settings', json={'mode': 'auto'})
    p = detail(client, pid)
    assert p['suggestions'][0]['candidate_count'] == 2
    assert not p['suggestions'][0]['automatic_eligible'] and not p['housing']


def test_same_name_with_different_numbers_is_not_one_person(client):
    sample(client)
    add_doc('national_id', 'front', {'name': 'محمد حسين حسن علي', 'document_number': 'AC1234567', 'national_number': '333333333333'})
    assert len(client.get('/api/people').json()['people']) == 2


@pytest.mark.parametrize('head,expected', [('حسين حسن', False), ('حُسَين حَسَن عَلِي', True), ('حسين حسن عليه', False)])
def test_name_normalization_and_minimum_components(client, head, expected):
    _, _, _, h, hd, _, pid = sample(client)
    hd['fields'][0] = field('name', head)
    storage.save_batch(h)
    client.patch('/api/people/settings', json={'mode': 'auto'})
    assert bool(detail(client, pid)['housing']) == expected


def test_uncertain_ocr_does_not_auto_link_and_candidates_are_not_values(client):
    _, _, _, h, hd, _, pid = sample(client)
    hd['fields'][0] = field('name', 'حسين حسن علي', verified=False)
    storage.save_batch(h)
    client.patch('/api/people/settings', json={'mode': 'auto'})
    p = detail(client, pid)
    assert p['suggestions'] and not p['housing']
    hd['fields'][0].update(value='', candidates=[{'value': 'حسين حسن علي', 'confidence': .99}])
    storage.save_batch(h)
    assert not detail(client, pid)['suggestions']


def test_stale_confirmation_rejected_and_old_links_need_review(client):
    _, _, _, h, hd, hr, pid = sample(client)
    p = detail(client, pid)
    payload = {'revision': p['revision'], 'refs': [hr], 'relationship': 'father_household'}
    hd['fields'][0]['value'] = 'شخص اخر مختلف تماما'
    storage.save_batch(h)
    assert client.post(f'/api/people/{pid}/links', json=payload).status_code == 409
    hd['fields'][0]['value'] = 'حسين حسن علي'
    storage.save_batch(h)
    p = detail(client, pid)
    payload['revision'] = p['revision']
    assert client.post(f'/api/people/{pid}/links', json=payload).status_code == 200
    hd['fields'][1]['value'] = 'عنوان جديد'
    storage.save_batch(h)
    p = detail(client, pid)
    assert p['housing'][0]['needs_review'] and not p['housing'][0]['confirmed']


def test_manual_attachments_atomic_and_unlink_preserves_documents(client):
    _, _, _, _, _, hr, pid = sample(client)
    p = detail(client, pid)
    bad = client.post(f'/api/people/{pid}/links', json={'revision': p['revision'], 'refs': [hr, 'missing']})
    assert bad.status_code == 404 and not detail(client, pid)['housing']
    p = client.post(f'/api/people/{pid}/links', json={'revision': p['revision'], 'refs': [hr]}).json()
    assert client.request('DELETE', f'/api/people/{pid}/links', json={'revision': p['revision'], 'refs': [hr]}).status_code == 200
    assert storage.get_batch(hr.split(':')[0])['documents']


def test_deleted_sources_disappear_and_export_checks_membership(client):
    b, _, ref, h, _, hr, pid = sample(client)
    p = detail(client, pid)
    p = client.post(f'/api/people/{pid}/links', json={'revision': p['revision'], 'refs': [hr], 'relationship': 'father_household'}).json()
    pdf = client.post(f'/api/people/{pid}/export', json={'revision': p['revision']})
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    archive = client.post(f'/api/people/{pid}/export', json={'revision': p['revision'], 'format': 'zip'})
    assert 'person.json' in zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    single = client.post(f'/api/people/{pid}/export', json={'revision': p['revision'], 'format': 'zip', 'layout': 'single'})
    import pypdfium2 as pdfium
    with zipfile.ZipFile(io.BytesIO(single.content)) as z, pdfium.PdfDocument(z.read('print.pdf')) as pdf:
        assert len(pdf) == 2
    assert client.delete('/api/batches/'+h['id']).status_code == 200
    fresh = detail(client, pid)
    assert not fresh['housing'] and len(fresh['documents']) == 1
    assert client.post(f'/api/people/{pid}/export', json={'revision': fresh['revision'], 'refs': [hr]}).status_code == 409
    assert client.delete('/api/batches/'+b['id']).status_code == 200
    assert client.get('/api/people').json()['people'] == []


def test_missing_name_waits_for_reading_and_manual_update_is_kept(client):
    add_doc('national_id', 'front', {'document_number': 'AB1234567'})
    result = client.get('/api/people').json()
    assert not result['people'] and result['missing_names'] == 1
    _, _, _, _, _, _, pid = sample(client)
    p = detail(client, pid)
    response = client.patch('/api/people/'+pid, json={'revision': p['revision'], 'display_name': 'ملف العائلة', 'notes': 'للمراجعة'})
    assert response.status_code == 200
    assert detail(client, pid)['notes'] == 'للمراجعة'
    assert detail(client, pid)['extracted_name'] == 'محمد حسين حسن علي'


def test_no_network_and_cross_site_denied(client, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network used'))
    _, _, _, _, _, _, pid = sample(client)
    assert detail(client, pid)['suggestions']
    assert client.patch('/api/people/settings', json={'mode': 'auto'}, headers={'Origin': 'https://outside.example'}).status_code == 403


def test_conflicting_numbers_do_not_attach_back(client):
    _, _, ref, _, _, _, pid = sample(client)
    add_doc('national_id', 'back', {'document_number': 'AB1234567', 'national_number': '999999999999'})
    assert [e['ref'] for e in detail(client, pid)['documents']] == [ref]


def test_folder_survives_temporarily_unreadable_name(client):
    b, d, _, _, _, _, pid = sample(client)
    d['fields'][0]['value'] = ''
    storage.save_batch(b)
    assert detail(client, pid)['needs_review']
    d['fields'][0]['value'] = 'محمد حسين حسن علي'
    storage.save_batch(b)
    assert detail(client, pid)['extracted_name'] == 'محمد حسين حسن علي'


def test_assembled_name_uses_current_components(client):
    b, d, _, _, _, _, pid = sample(client)
    d['fields'][0]['method'] = 'assembled_visible_names'
    d['fields'].extend([field('first_name','محمد'),field('father_name','حسين'),field('grandfather_name','حسن'),field('surname','علي')])
    storage.save_batch(b)
    assert detail(client, pid)['suggestions']
    next(f for f in d['fields'] if f['key']=='father_name')['value'] = 'كريم'
    storage.save_batch(b)
    p = detail(client, pid)
    assert p['extracted_name'] == 'محمد كريم حسن علي'
    assert next(f for f in p['fields'] if f['key']=='name')['value'] == p['extracted_name']
    assert not p['suggestions']


def test_print_recommends_one_copy_per_exact_card_side(client):
    b, d, ref, _, _, _, pid = sample(client)
    add_doc('national_id','front',{'name':'محمد حسين حسن علي','document_number':'AB1234567','national_number':'123456789012'})
    add_doc('national_id','back',{'document_number':'AB1234567','birth_date':'1998/09/23'})
    add_doc('national_id','back',{'document_number':'AB1234567','birth_date':'1998/09/23'})
    p = detail(client, pid)
    assert len(p['documents']) == 4 and p['duplicate_count'] == 2
    assert len(p['recommended_refs']) == 2
    import pypdfium2 as pdfium
    default = client.post(f'/api/people/{pid}/export',json={'revision':p['revision']})
    with pdfium.PdfDocument(default.content) as pdf:
        assert len(pdf) == 1
    all_copies = client.post(f'/api/people/{pid}/export',json={'revision':p['revision'],'refs':[e['ref'] for e in p['documents']]})
    with pdfium.PdfDocument(all_copies.content) as pdf:
        assert len(pdf) == 2
