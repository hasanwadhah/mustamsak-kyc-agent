from copy import deepcopy
import io
import zipfile

import pytest
import pypdfium2 as pdfium
from PIL import Image
from fastapi.testclient import TestClient

from app import main, pipeline, storage
from app.print_layout import automatic_sheets, grid_spec, manual_sheets


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    for name in ('batches', 'images', 'exports'):
        (tmp_path / name).mkdir()
    with TestClient(main.app) as c:
        yield c


def seed(count=7):
    b = pipeline.new_batch('Print layout test')
    b['status'] = 'ready'
    for i in range(count):
        iid = storage.uid()
        color = [(180, 30, 30), (20, 120, 40), (30, 60, 180)][i % 3]
        Image.new('RGB', (300, 180), color).save(storage.image_path(iid))
        d = dict(id=storage.uid(), image_id=iid, original_id=iid, source_id=iid,
                 source_name='synthetic.png', page=1, kind='housing', side='front' if i % 2 == 0 else 'back',
                 group=str(i // 2), order=i, reviewed=True, fields=[], ocr=[], evidence=[], notices=[], width=300, height=180)
        b['documents'].append(d)
    storage.save_batch(b)
    return b


def render(data, index=0):
    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[index]
        try:
            bitmap = page.render(scale=2)
            try:
                return bitmap.to_pil().convert('RGB').copy(), len(pdf)
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        pdf.close()


def at_mm(image, x, y):
    return image.getpixel((int(x / 210 * image.width), int(y / 297 * image.height)))


@pytest.mark.parametrize('layout,count,pages', [('grid4', 7, 2), ('grid6', 7, 2), ('grid6', 6, 1)])
def test_grid_overflow_and_clean_a4(client, layout, count, pages):
    b = seed(count)
    response = client.post(f'/api/batches/{b["id"]}/export', json={'ids': [d['id'] for d in b['documents']], 'layout': layout})
    assert response.status_code == 200
    im, n = render(response.content)
    assert n == pages
    assert abs(im.width / im.height - 210 / 297) < .002
    assert at_mm(im, 154, 56) == (180, 30, 30)  # front right
    assert at_mm(im, 56, 56) == (20, 120, 40)   # back left
    assert at_mm(im, 105, 56) == (255, 255, 255)  # column gap
    assert at_mm(im, 11, 24) == (255, 255, 255)   # no printed guide frame
    assert at_mm(im, 105, 288) == (255, 255, 255) # no footer in grid templates


def test_manual_blanks_swaps_and_zip_pdf_agree(client):
    b = seed(3)
    ids = [d['id'] for d in b['documents']]
    pages = [[None, ids[2], ids[1], None], [ids[0], None, None, None]]
    body = {'ids': ids, 'layout': 'grid4', 'pages': pages}
    endpoint = f'/api/batches/{b["id"]}/export'
    response = client.post(endpoint, json=body)
    assert response.status_code == 200
    im, n = render(response.content)
    assert n == 2
    assert at_mm(im, 154, 56) == (255, 255, 255)
    assert at_mm(im, 56, 56) == (30, 60, 180)
    assert at_mm(im, 154, 132) == (20, 120, 40)
    second, _ = render(response.content, 1)
    assert at_mm(second, 154, 56) == (180, 30, 30)
    response = client.post(endpoint, json=body | {'format': 'zip'})
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        zipped, _ = render(archive.read('print.pdf'))
        assert zipped.tobytes() == im.tobytes()


@pytest.mark.parametrize('case', ['unknown', 'duplicate', 'omitted', 'wrong_count', 'blank_page', 'non_grid', 'empty', 'too_many'])
def test_invalid_manual_plan_rejected(client, case):
    b = seed(2)
    a, z = [d['id'] for d in b['documents']]
    pages = [[a, z, None, None]]
    layout = 'grid4'
    if case == 'unknown': pages[0][1] = 'foreign-document'
    if case == 'duplicate': pages[0][2] = a
    if case == 'omitted': pages[0][1] = None
    if case == 'wrong_count': pages[0].append(None)
    if case == 'blank_page': pages.append([None] * 4)
    if case == 'non_grid': layout = 'single'
    if case == 'empty': pages = []
    if case == 'too_many': pages *= 201
    response = client.post(f'/api/batches/{b["id"]}/export', json={'ids': [a, z], 'layout': layout, 'pages': pages})
    assert response.status_code == 422


def test_manual_review_guard_and_existing_layouts(client):
    b = seed(2)
    b['documents'][0]['reviewed'] = False
    storage.save_batch(b)
    ids = [d['id'] for d in b['documents']]
    endpoint = f'/api/batches/{b["id"]}/export'
    body = {'ids': ids, 'layout': 'grid4', 'pages': [[ids[0], ids[1], None, None]]}
    assert client.post(endpoint, json=body).status_code == 409
    assert client.post(endpoint, json=body | {'allow_unreviewed': True}).status_code == 200
    for layout, expected in [('pairs', 1), ('single', 2)]:
        response = client.post(endpoint, json={'ids': ids, 'layout': layout, 'allow_unreviewed': True})
        assert response.status_code == 200
        assert render(response.content)[1] == expected


def test_card_size_and_portrait_aspect(client):
    b = seed(2)
    a, z = b['documents']
    a['kind'] = 'national_id'
    # A tall document must be contained, without stretching or cropping.
    Image.new('RGB', (100, 300), (20, 120, 40)).save(storage.image_path(z['image_id']))
    storage.save_batch(b)
    body = {'ids': [a['id'], z['id']], 'layout': 'grid4', 'size': 'card', 'pages': [[a['id'], z['id'], None, None]]}
    response = client.post(f'/api/batches/{b["id"]}/export', json=body)
    im, _ = render(response.content)
    assert at_mm(im, 110, 56) == (255, 255, 255)  # inset for 85.6 mm width
    assert at_mm(im, 112, 56) == (180, 30, 30)
    assert at_mm(im, 56, 25) == (20, 120, 40)     # tall image fills slot height
    assert at_mm(im, 35, 56) == (255, 255, 255)  # empty sides retain aspect


def test_singleton_groups_start_new_row(client):
    b = seed(3)
    for i, d in enumerate(b['documents']): d['group'] = str(i)
    sheets = automatic_sheets(b['documents'], 'grid4')
    assert [[d['id'] if d else None for d in s] for s in sheets] == [
        [b['documents'][0]['id'], None, b['documents'][1]['id'], None],
        [b['documents'][2]['id'], None, None, None]]
    assert client.get('/api/print-layouts').json()['grid6'] == grid_spec('grid6')


def test_person_manual_refs_across_batches_and_revision_guard(client):
    b = seed(1)
    d = b['documents'][0]
    d.update(kind='national_id', side='front', fields=[{'key':'name','value':'Test Person'}, {'key':'document_number','value':'AB1234567','method':'manual','verified':True}])
    storage.save_batch(b)
    back_batch = deepcopy(b)
    back_batch['id'] = storage.uid()
    # Deliberately reuse the document id in another batch: refs must disambiguate.
    back_batch['documents'][0]['side'] = 'back'
    storage.save_batch(back_batch)
    pid = client.get('/api/people').json()['people'][0]['id']
    detail = client.get(f'/api/people/{pid}').json()
    refs = [e['ref'] for e in detail['documents']]
    assert len(refs) == 2
    body = {'revision': detail['revision'], 'refs': refs, 'layout': 'grid6', 'allow_unreviewed': True,
            'pages': [[None, refs[1], None, None, refs[0], None]]}
    endpoint = f'/api/people/{pid}/export'
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text[:300]
    im, _ = render(response.content)
    assert at_mm(im, 154, 56) == (255, 255, 255)
    assert at_mm(im, 56, 56) == (180, 30, 30)
    assert at_mm(im, 154, 208) == (180, 30, 30)
    assert client.post(endpoint, json=body | {'pages': [[refs[0], 'other:ref', None, None, None, None]]}).status_code == 422
    assert client.post(endpoint, json=body | {'revision': '0' * 64}).status_code == 409
