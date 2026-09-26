"""Delete app-owned records, preserving images referenced by other records."""
from copy import deepcopy
import json

from . import storage


def image_ids(batch):
    ids = {s['id'] for s in batch.get('sources', [])}
    for doc in batch.get('documents', []):
        for key in ('source_id', 'image_id', 'original_id', 'field_image_id'):
            if doc.get(key):
                ids.add(doc[key])
        ids.update(doc.get('image_history', []))
        for field in doc.get('fields', []):
            if field.get('source_image_id'):
                ids.add(field['source_image_id'])
    return ids


def cleanup_plan(before, after=None):
    """Called under storage.LOCK, before changing any persisted record.

    Never sweep the entire images directory: an OCR worker may have written
    images that are not yet in its batch. Only consider this record's images.
    Fail closed if another batch cannot be read or a path escapes app storage.
    """
    retained = image_ids(after) if after is not None else set()
    for path in (storage.DATA / 'batches').glob('*.json'):
        if path.name != f'{before["id"]}.json':
            retained.update(image_ids(json.loads(path.read_text(encoding='utf-8'))))
    candidates = image_ids(before) - retained
    image_dir = (storage.DATA / 'images').resolve()
    paths = []
    for iid in candidates:
        path = storage.image_path(iid)
        if path.resolve().parent != image_dir:
            raise ValueError('Image path outside storage')
        paths.append(path)
    return paths


def cleanup_images(paths):
    # The record has already been committed. Report cleanup failures instead
    # of making a successful delete appear to have failed (and be retried).
    failed = 0
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            failed += 1
    return failed


def without_documents(batch, ids):
    result = deepcopy(batch)
    removed = set(ids)
    result['documents'] = [d for d in result['documents'] if d['id'] not in removed]
    for doc in result['documents']:
        pairing = doc.get('pairing') or {}
        if removed.intersection({pairing.get('front_id'), pairing.get('back_id')}):
            doc['pairing'] = {'status': 'unmatched', 'number': pairing.get('number')}
            doc['group_reason'] = 'حُذف الوجه المقابل؛ أعد رفعه ثم طابق وجوه الموحدة.'
            doc['reviewed'] = False
        for field in doc.get('fields', []):
            if field.get('source_document_id') not in removed:
                continue
            # Keep a human-approved value, but remove its now-deleted evidence.
            approved = field.get('verified') or field.get('method') == 'manual'
            clean = {k: field[k] for k in ('key', 'label', 'value') if k in field}
            if not approved:
                clean['value'] = ''
            clean.update(method='manual' if approved else 'missing',
                         status='manual' if approved else 'missing',
                         verified=bool(approved), confidence=None, box=None,
                         note='حُذف الوجه الذي استُخرجت منه هذه القيمة؛ راجع الحقل.')
            field.clear()
            field.update(clean)
            doc['reviewed'] = False
    # Original pages remain available for recropping until the batch is deleted.
    return result
