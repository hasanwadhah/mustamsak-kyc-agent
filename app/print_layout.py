"""A4 print geometry shared by the PDF renderer and the browser board."""
from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel, Field


class PrintOptions(BaseModel):
    layout: Literal['pairs', 'single', 'grid4', 'grid6'] = 'pairs'
    size: Literal['fit', 'card'] = 'fit'
    pages: list[list[str | None]] | None = Field(default=None, min_length=1, max_length=200)


def grid_spec(layout):
    if layout not in ('grid4', 'grid6'):
        raise ValueError('اختر قالب الأربع أو الست خانات للترتيب اليدوي.')
    count = 4 if layout == 'grid4' else 6
    return {'width': 210, 'height': 297, 'slots': [
        {'x': 109 if i % 2 == 0 else 11, 'y': 24 + (i // 2) * 76, 'width': 90, 'height': 64}
        for i in range(count)
    ]}


def grouped_documents(documents):
    groups = OrderedDict()
    for d in documents:
        groups.setdefault(d.get('group') or d['id'], []).append(d)
    return [sorted(ds, key=lambda d: ({'front': 0, 'back': 1}.get(d.get('side'), 2), d.get('order', 0)))
            for ds in groups.values()]


def automatic_sheets(documents, layout):
    if layout == 'single':
        return [[d] for d in documents]
    rows = [ds[i:i + 2] for ds in grouped_documents(documents) for i in range(0, len(ds), 2)]
    if layout == 'pairs':
        return rows
    count = len(grid_spec(layout)['slots'])
    slots = [d for row in rows for d in (row + [None] * (2 - len(row)))]
    return [slots[i:i + count] + [None] * max(0, count - len(slots[i:i + count]))
            for i in range(0, len(slots), count)]


def manual_sheets(pages, layout, by_key):
    """Resolve only documents selected by the caller; never silently omit one."""
    if pages is None:
        return None
    count = len(grid_spec(layout)['slots'])
    if not pages or len(pages) > 200 or any(len(page) != count for page in pages):
        raise ValueError('عدد الخانات لا يطابق القالب المحدد.')
    if any(not any(key is not None for key in page) for page in pages):
        raise ValueError('توجد صفحة فارغة؛ أزلها من لوحة الترتيب قبل الطباعة.')
    keys = [key for page in pages for key in page if key is not None]
    if len(keys) != len(set(keys)):
        raise ValueError('المستمسك مكرر في أكثر من خانة.')
    if set(keys) != set(by_key):
        raise ValueError('مستمسكات اللوحة لا تطابق الاختيار؛ أعد فتح لوحة الترتيب.')
    return [[by_key[key] if key is not None else None for key in page] for page in pages]


def person_print_group(entry):
    from .national_serial import pairing_number
    d=entry['document']
    serial=pairing_number(d) if d['kind']=='national_id' else None
    return f'national:{serial}' if serial else f'{entry["batch_id"]}:{d.get("group") or d["id"]}'
