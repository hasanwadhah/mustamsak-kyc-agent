from copy import deepcopy

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main, pipeline, storage, vision


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for name in ('batches', 'images', 'exports'):
        (tmp_path / name).mkdir()
    with TestClient(main.app) as client:
        yield client


def make_image():
    iid = storage.uid()
    vision.save_image(storage.image_path(iid), np.full((100, 200, 3), 200, np.uint8))
    return iid


def make_batch():
    batch = pipeline.new_batch('delete-test')
    batch['status'] = 'ready'
    source = {'id': make_image(), 'name': 'synthetic.png', 'page': 1, 'width': 200, 'height': 100}
    batch['sources'] = [source]
    for side in ('front', 'back'):
        iid = make_image()
        batch['documents'].append({
            'id': storage.uid(), 'source_id': source['id'], 'source_name': source['name'],
            'page': 1, 'image_id': iid, 'original_id': iid, 'field_image_id': iid,
            'kind': 'national_id', 'side': side, 'group': 'test', 'group_reason': '',
            'fields': [], 'ocr': [], 'notices': [], 'evidence': [], 'reviewed': False,
            'order': len(batch['documents']), 'width': 200, 'height': 100,
        })
    storage.save_batch(batch)
    return batch


def endpoint(batch):
    return f'/api/batches/{batch["id"]}'


def test_delete_batch_removes_records_and_its_images_only(client):
    b = make_batch()
    other = make_batch()
    original = storage.DATA / 'original-upload.png'
    original.write_bytes(b'outside app image store')
    response = client.delete(endpoint(b))
    assert response.status_code == 200 and response.json()['cleanup_warning'] is None
    assert client.get(endpoint(b)).status_code == 404
    assert client.delete(endpoint(b)).status_code == 404
    assert not storage.image_path(b['sources'][0]['id']).exists()
    assert all(not storage.image_path(d['image_id']).exists() for d in b['documents'])
    assert client.get(endpoint(other)).status_code == 200
    assert storage.image_path(other['sources'][0]['id']).exists()
    assert original.read_bytes() == b'outside app image store'


def test_shared_images_survive_until_last_batch_is_removed(client):
    b = make_batch()
    copy = deepcopy(b)
    copy['id'] = storage.uid()
    storage.save_batch(copy)
    assert client.delete(endpoint(b)).status_code == 200
    assert all(storage.image_path(d['image_id']).exists() for d in copy['documents'])
    assert client.delete(endpoint(copy)).status_code == 200
    assert not storage.image_path(copy['sources'][0]['id']).exists()
    assert all(not storage.image_path(d['image_id']).exists() for d in copy['documents'])


def test_selected_delete_keeps_source_and_unselected_face(client):
    b = make_batch()
    first, second = b['documents']
    response = client.request('DELETE', endpoint(b)+'/documents', json={'ids': [first['id'], first['id']]})
    assert response.status_code == 200 and response.json()['deleted_count'] == 1
    assert [d['id'] for d in response.json()['batch']['documents']] == [second['id']]
    assert not storage.image_path(first['image_id']).exists()
    assert storage.image_path(second['image_id']).exists()
    assert storage.image_path(b['sources'][0]['id']).exists()
    response = client.request('DELETE', endpoint(b)+'/documents', json={'ids': [second['id']]})
    assert response.json()['batch']['documents'] == []
    assert response.json()['batch']['sources'] == b['sources']


def test_all_ids_must_exist_before_any_deletion(client):
    b = make_batch()
    before = storage.get_batch(b['id'])
    response = client.request('DELETE', endpoint(b)+'/documents', json={'ids': [b['documents'][0]['id'], storage.uid()]})
    assert response.status_code == 404
    assert storage.get_batch(b['id']) == before
    assert all(storage.image_path(d['image_id']).exists() for d in b['documents'])
    assert client.request('DELETE', endpoint(b)+'/documents', json={'ids': []}).status_code == 422


@pytest.mark.parametrize('status', ['queued', 'processing'])
def test_processing_batches_cannot_be_deleted(client, status):
    b = make_batch()
    b['status'] = status
    storage.save_batch(b)
    assert client.delete(endpoint(b)).status_code == 409
    assert client.request('DELETE', endpoint(b)+'/documents', json={'ids': [b['documents'][0]['id']]}).status_code == 409
    assert storage.get_batch(b['id'])['documents'] == b['documents']


def test_deleting_counterpart_invalidates_match_and_linked_fields(client):
    b = make_batch()
    front, back = b['documents']
    pairing = {'status': 'matched', 'number': 'AB1234567', 'front_id': front['id'], 'back_id': back['id']}
    front.update(pairing=pairing, reviewed=True)
    front['fields'] = [dict(key='sex', label='sex', value='M', method='paired_mrz', verified=False,
                            source_document_id=back['id'], source_image_id=back['image_id']),
                       dict(key='approved', label='approved', value='kept', verified=True,
                            source_document_id=back['id'], source_image_id=back['image_id'])]
    storage.save_batch(b)
    response = client.request('DELETE', endpoint(b)+'/documents', json={'ids': [back['id']]})
    remaining = response.json()['batch']['documents'][0]
    assert remaining['pairing']['status'] == 'unmatched' and not remaining['reviewed']
    assert remaining['fields'][0]['value'] == ''
    assert remaining['fields'][1]['value'] == 'kept'
    assert all('source_document_id' not in f and 'source_image_id' not in f for f in remaining['fields'])
    assert not storage.image_path(back['image_id']).exists()


def test_other_batch_field_evidence_protects_image(client):
    b = make_batch()
    other = make_batch()
    iid = b['documents'][0]['image_id']
    other['documents'][0]['fields'] = [{'key': 'sex', 'value': 'M', 'source_image_id': iid}]
    storage.save_batch(other)
    assert client.delete(endpoint(b)).status_code == 200
    assert storage.image_path(iid).exists()
    assert client.delete(endpoint(other)).status_code == 200
    assert not storage.image_path(iid).exists()


def test_corrupt_record_prevents_unsafe_cleanup(client):
    b = make_batch()
    (storage.DATA/'batches'/f'{storage.uid()}.json').write_text('{broken', encoding='utf-8')
    assert client.delete(endpoint(b)).status_code == 409
    assert storage.get_batch(b['id']) == b
    assert storage.image_path(b['sources'][0]['id']).exists()


def test_image_path_cannot_escape_storage(client, monkeypatch):
    b = make_batch()
    outside = storage.DATA / 'keep.png'
    outside.write_bytes(b'keep')
    monkeypatch.setattr(storage, 'image_path', lambda iid: outside)
    assert client.delete(endpoint(b)).status_code == 409
    assert outside.read_bytes() == b'keep'
    assert storage.get_batch(b['id']) == b


def test_external_origin_cannot_delete(client):
    b = make_batch()
    assert client.delete(endpoint(b), headers={'Origin': 'https://other.example'}).status_code == 403
    assert storage.get_batch(b['id']) == b


def test_edit_versions_are_removed_with_batch(client):
    b = make_batch()
    did = b['documents'][0]['id']
    versions = []
    for _ in range(2):
        response = client.post(endpoint(b)+f'/documents/{did}/edit', json={'operation': 'rotate'})
        assert response.status_code == 200
        versions.append(response.json()['image_id'])
    assert client.delete(endpoint(b)).status_code == 200
    assert all(not storage.image_path(iid).exists() for iid in versions)


def test_inflight_ocr_cannot_restore_deleted_document(client, monkeypatch):
    b = make_batch()
    did = b['documents'][0]['id']
    def ocr(image):
        main.delete_documents(b['id'], main.DeleteDocuments(ids=[did]))
        return []
    monkeypatch.setattr(vision, 'ocr', ocr)
    monkeypatch.setattr(vision, 'extract_fields', lambda *args: [])
    assert client.post(endpoint(b)+f'/documents/{did}/ocr').status_code == 404
    assert all(d['id'] != did for d in storage.get_batch(b['id'])['documents'])
