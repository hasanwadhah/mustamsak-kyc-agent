"""Tolerant matching of printed labels and document keywords in OCR text.

OCR on phone photos confuses dotted Arabic letters (رقم→رفم, تاريخ→ناريخ), drops
letters (النشاط→الشاط) and glues a value to its label (الاسم التجاريشركة).
These helpers locate *labels and keywords only*. They are never used to change
or complete a field value.
"""
import re


def edit_distance(a, b, limit=None):
    """Levenshtein distance; stops early once every path exceeds `limit`."""
    if abs(len(a) - len(b)) > (limit if limit is not None else len(a) + len(b)):
        return (limit or 0) + 1
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        if limit is not None and min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def tolerance(phrase):
    """Allowed typos: none for short labels (الأب/الأم differ by one letter)."""
    n = len(phrase.replace(' ', ''))
    return 0 if n < 6 else 1 if n < 11 else 2


def find_label(text, label):
    """Return (start, end, typos) of `label` in normalized `text`, or None.

    Exact, word-bounded matches win. Multi-word or long labels may be glued to
    the following value. Otherwise allow a small number of OCR slips, only at a
    word start, so a label is never found inside another word.
    """
    exact = re.search(r'(?<![\w])' + re.escape(label) + r'(?![\w])', text)
    if exact:
        return exact.start(), exact.end(), 0
    if ' ' in label or len(label) >= 6:
        glued = re.search(r'(?<![\w])' + re.escape(label), text)
        if glued:
            return glued.start(), glued.end(), 0
    limit = tolerance(label)
    if not limit:
        return None
    best = None
    starts = [0] + [m.end() for m in re.finditer(r'\s+', text)]
    for start in starts:
        for size in range(len(label) - limit, len(label) + limit + 1):
            window = text[start:start + size]
            if len(window) < size or len(window) < 3:
                continue
            distance = edit_distance(window, label, limit)
            if distance <= limit and (best is None or distance < best[2]):
                best = (start, start + size, distance)
        if best and best[2] == 0:
            break
    return best


def contains_phrase(text, phrase, limit=None):
    """Keyword presence for classification: ignores spacing, tolerates slips.

    `limit` overrides the default typo allowance for long, distinctive phrases.
    """
    compact_text, compact_phrase = text.replace(' ', ''), phrase.replace(' ', '')
    if compact_phrase in compact_text:
        return True
    limit = tolerance(phrase) if limit is None else limit
    if not limit:
        return False
    words = text.split()
    count = len(phrase.split())
    for size in range(max(1, count - 1), count + 2):
        for i in range(len(words) - size + 1):
            window = ''.join(words[i:i + size])
            if edit_distance(window, compact_phrase, limit) <= limit:
                return True
    return False
