"""Conservative spelling suggestions for compound Arabic names, never replacements."""
import re
from functools import lru_cache
from .focused_fields import normalize

# Common name vocabulary, not a register of people. Unknown names are retained.
FIRST = set('محمد احمد محمود مصطفى علي حسن حسين حيدر سعيد سعد سامر سيف عمر عثمان خالد وليد ياسر قاسم جاسم كريم هادي هاشم زيد زيدان عباس فاضل فالح طارق ناظم ناصر سمير سليم عادل عدنان مهدي ماجد حاتم حازم سالم صباح فؤاد نبيل نزار جمال كمال لطيف حميد رشيد رائد غسان لؤي ثامر جواد عمار نجم باسم باسل سجاد منتظر مرتضى مريم فاطمة زينب خديجة زهراء نور هدى دعاء سارة ندى'.split())
FIRST = {normalize(n):n for n in FIRST}
TAILS = ['الله','الرحمن','الرحيم','الكريم','الأمير','الأمين','الحسين','الحسن','الهادي','القادر','اللطيف','الملك','الواحد','الجبار','الرزاق','الحميد','الستار','السلام','العزيز','المجيد']


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def split_exact_names(value):
    if not value:return []
    if value in FIRST:return [FIRST[value]]
    for i in range(3,len(value)-2):
        if value[:i] in FIRST and value[i:] in FIRST:return [FIRST[value[:i]],FIRST[value[i:]]]
    return None


def split_near_names(value):
    """Suggest one uniquely closest misspelling next to an exact known name.

    A word already in the vocabulary is not changed. Short/ambiguous matches
    are left alone; this function only contributes an unverified alternative.
    """
    options=set()
    for i in range(3,len(value)-2):
        a,b=value[:i],value[i:]
        for fixed,unknown,reverse in ((a,b,False),(b,a,True)):
            if fixed not in FIRST or unknown in FIRST or len(unknown)<4:continue
            close=[word for word in FIRST if edit_distance(unknown,word)==1]
            if len(close)!=1:continue
            pair=(FIRST[fixed],FIRST[close[0]])
            options.add(pair[::-1] if reverse else pair)
    return list(next(iter(options))) if len(options)==1 else None


def add_name_suggestions(result):
    if not result or result.get('verified') or result.get('method')=='manual':return
    suggestions=[]
    for reading in result.get('candidates',[]):
        raw=re.sub(r'[^\u0621-\u064a]', '', normalize(reading.get('value','')))
        if not 8<=len(raw)<=45:continue
        # OCR frequently joins adjacent names and splits الأمير as الأ فير.
        # Require known names, allowing one uniquely closest single-letter
        # prefix repair. Keep every compound-name correction as a choice.
        for length in range(4,min(10,len(raw)-5)):
            prefix,tail=raw[:-length],raw[-length:]
            ranked=sorted((edit_distance(tail,normalize(n)),n) for n in TAILS)
            if ranked[0][0]>1 or ranked[0][0]==ranked[1][0]:continue
            for size in (3,2,4):
                if len(prefix)<size+6 or edit_distance(prefix[-size:],'عبد')>1:continue
                words=split_exact_names(prefix[:-size]) or split_near_names(prefix[:-size])
                if not words:continue
                value=' '.join(words+['عبد',ranked[0][1]])
                if normalize(value).replace(' ','')!=raw and value not in suggestions:suggestions.append(value)
    readings=result.get('readings') or [{'value':c.get('value',''),'variant':c.get('variant'),'engine':c.get('engine')}
                                        for c in [{'value':result.get('value','')}]+result.get('candidates',[]) if c.get('value')]
    for value in lexicon_suggestions(readings,value=result.get('value','')):
        if value not in suggestions:suggestions.append(value)
    if suggestions:
        result['candidates']=[{'value':v,'confidence':None,'engine':'name_spelling_suggestion',
                               'note':'اقتراح تهجئة لاسم مركب؛ يحتاج مقارنة بالصورة.'} for v in suggestions[:3]]+result.get('candidates',[])
        result['note']=result.get('note','')+' توجد اقتراحات تهجئة للاسم المركب؛ لا تغيّر الاسم ولا تربطه بملف شخص قبل مراجعتها.'


# ---------------------------------------------------------------- whole-name lexicon suggestions
# Common Iraqi given names and name parts (a vocabulary, not a register of people).
NAME_WORDS = set('''
محمد احمد محمود مصطفى علي حسن حسين حيدر سعيد سعد سامر سيف عمر عثمان خالد وليد ياسر قاسم جاسم كريم هادي هاشم زيد
زيدان عباس فاضل فالح طارق ناظم ناصر سمير سليم عادل عدنان مهدي ماجد حاتم حازم سالم صباح فؤاد نبيل نزار جمال كمال
لطيف حميد رشيد رائد غسان لؤي ثامر جواد عمار نجم باسم باسل سجاد منتظر مرتضى عبيد عبود جبار ستار كاظم جعفر صادق
باقر رضا موسى عيسى يوسف ابراهيم اسماعيل يعقوب يونس زكي زكريا شاكر صالح صلاح فلاح نجاح حمزة حمود مجيد رحيم نور
ضياء علاء بهاء صفاء وسام حسام هشام عصام قيس اياد اسعد ماهر مازن معن منير نعمان رعد برهان جليل خليل عقيل فيصل منذر
مالك مهند محسن مؤيد لقمان سلمان عدي قصي ليث مثنى عماد غانم شهاب فراس نصير ثائر غازي ضرغام جبر عودة كامل عامر
عمران عزيز حبيب نجيب رياض فارس سلام جميل حمدي نوري شوقي فوزي مجبل مطر كاطع جاسب عبدالله زين زينب مريم فاطمة
خديجة زهراء هدى دعاء سارة ندى رقية آمنة ليلى سعاد نادية رنا سهام بتول سجى هبة ايمان اسراء شيماء رشا ريم منى
وفاء سناء هناء حنان كوثر نرجس زهرة
'''.split())
COMPOUNDS = ['زين العابدين', 'نور الدين', 'صلاح الدين', 'عز الدين', 'علاء الدين', 'ضياء الدين', 'بهاء الدين', 'سيف الدين',
             'شمس الدين', 'حسام الدين', 'عماد الدين', 'نجم الدين', 'محي الدين'] + ['عبد ' + t for t in TAILS] + \
            ['عبد الزهرة', 'عبد الرضا', 'عبد العباس', 'عبد الجليل', 'عبد الغني', 'عبد الوهاب', 'عبد الرسول', 'عبد علي']
# Letters that differ only by dots are the typical handwriting/OCR confusion.
CONFUSABLE = [set('بتثنيئ'), set('جحخ'), set('دذ'), set('رز'), set('سش'), set('صض'), set('طظ'), set('عغ'), set('فق'), set('هة')]


def weighted_distance(a, b):
    """Edit distance where swapping letters that differ only by dots costs half."""
    def cost(x, y):
        return 0 if x == y else .5 if any(x in g and y in g for g in CONFUSABLE) else 1
    previous = [float(j) for j in range(len(b) + 1)]
    for i, x in enumerate(a, 1):
        current = [float(i)]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + cost(x, y)))
        previous = current
    return previous[-1]


def _entries():
    words = [(normalize(w), w) for w in NAME_WORDS]
    compounds = [(normalize(c).replace(' ', ''), c) for c in COMPOUNDS]
    return words, compounds


def segmentations(tokens, limit=3):
    """Best ways to read a token list as known name parts. Returns [(cost, [names])]."""
    words, compounds = _entries()
    beams = {0: [(0.0, [])]}
    for i in range(len(tokens)):
        for cost, names in beams.get(i, []):
            for span in (1, 2):
                if i + span > len(tokens):
                    continue
                text = ''.join(tokens[i:i + span])
                pool = compounds if span == 2 else words + compounds
                allowed = max(1.0, .4 * len(text))
                for key, name in pool:
                    if abs(len(key) - len(text)) > allowed:
                        continue
                    d = weighted_distance(text, key)
                    if d <= allowed:
                        beams.setdefault(i + span, []).append((cost + d, names + [(name, d)]))
            beams[i + 1] = sorted(beams.get(i + 1, []), key=lambda b: b[0])[:limit * 4]
            if i + 2 in beams:
                beams[i + 2] = sorted(beams[i + 2], key=lambda b: b[0])[:limit * 4]
    return sorted(beams.get(len(tokens), []), key=lambda b: b[0])[:limit]


MORE_NAMES = set("""
سعدي سعدون سامي ياسين نصر سليمان امير انور ايمن بشير بكر بلال توفيق ثابت جابر جلال جمعة حارث حافظ حامد حسنين
حكيم حليم حمادي حمدان خضر خضير خميس داود دريد ذياب راضي رافع راشد رامي ربيع رزاق رسول رشاد رمضان زاهد زهير زياد
ساجد ساهر سرمد سعود سلوان سنان سهيل شاهين شريف شعلان صبري طالب طاهر طه ظافر عارف عاصم عاطف عايد عزام عزت عطية
علوان عون غالب غيث فائز فاروق فرحان فرقد فريد فهد قحطان كرار مروان مسلم مشتاق معتز مقداد منصور منعم موفق مؤمل ميثم
ناجي نادر نشأت نصار نعيم نمير هاني هيثم وائل واثق وحيد وعد يحيى يعرب مناف حسون مكي عيدان حمادة عبد عبدو عبيس
اسيل الاء امل انوار بشرى تبارك حوراء دنيا رحاب رغد رفل زهور سلمى سميرة شهد صبا ضحى عبير غفران فرح لمياء لينا مروة
ملاك نورا نوال هالة هيفاء وجدان ياسمين
""".split())
MORE_COMPOUNDS = ['عبد الحسين', 'عبد الكاظم', 'عبد المهدي', 'عبد الصاحب', 'عبد النبي', 'عبد الحمزة', 'عبد السادة',
                  'عبد الهادي', 'عبد الجبار', 'عبد الستار', 'عبد الكريم', 'عبد الله']
# Handwriting shape confusions seen in OCR of development cards, beyond dots: حمير/حميد, كبيد/عبيد,
# سليع/سليم, ملافى/مصطفى. Cheaper than a free substitution, dearer than a dot slip.
SHAPE_ALIKE = [set('ردزذو'), set('عغك'), set('عم'), set('الطك'), set('صل'), set('ىيئ'), set('هةو')]
# Letters OCR often drops or adds in joined handwriting: the teeth, and the small و/ع/ه.
EASY_GAP = set('سشبتثنيىئعهو')


def _cost(x, y):
    if x == y:
        return 0.0
    if any(x in g and y in g for g in CONFUSABLE):
        return .4
    if any(x in g and y in g for g in SHAPE_ALIKE):
        return .6
    return 1.0


def _gap(x):
    return .6 if x in EASY_GAP else 1.0


@lru_cache(maxsize=200000)
def shape_distance(a, b):
    """Edit distance for handwritten Arabic read by OCR: dot and shape slips and lost teeth are cheap."""
    previous = [0.0]
    for y in b:
        previous.append(previous[-1] + _gap(y))
    for x in a:
        current = [previous[0] + _gap(x)]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + _gap(y), previous[j] + _gap(x), previous[j - 1] + _cost(x, y)))
        previous = current
    return previous[-1]


def learned_names():
    """Name words the reviewer typed or confirmed on this computer (app/learning.py)."""
    try:
        from .learning import known_name_words
        return known_name_words()
    except Exception:
        return set()


def _lexicon():
    words = {normalize(w): w for w in NAME_WORDS | MORE_NAMES | learned_names()}
    compounds = {}
    for c in COMPOUNDS + MORE_COMPOUNDS:  # first spelling wins (keeps the hamza of «عبد الأمير»)
        compounds.setdefault(normalize(c).replace(' ', ''), c)
    return words, compounds


def _options(text, words, compounds, k=4):
    """Closest name parts for one piece of OCR text: [(normalized cost, name)]."""
    return _cached_options(text, tuple(sorted(words.items())), tuple(sorted(compounds.items())))[:k]


@lru_cache(maxsize=20000)
def _cached_options(text, words, compounds):
    words, compounds = dict(words), dict(compounds)
    ranked = []
    for key, name in list(words.items()) + list(compounds.items()):
        if abs(len(key) - len(text)) > max(2, len(key) // 2):
            continue
        d = shape_distance(text, key) / max(len(key), len(text))
        if d <= .5:
            ranked.append((d, name))
    return tuple(sorted(ranked)[:8])


def _sequences(tokens, words, compounds, beam=12):
    """Read OCR tokens as name parts, allowing OCR's joined (محمدسليم) and split (رين الماندين) words."""
    beams = {0: [(0.0, [])]}
    for i in range(len(tokens)):
        token = tokens[i]
        # Every way to read token i, computed once for all beams: alone, joined with the next
        # token, split into two names, or skipped when it is a short fragment.
        moves = []
        pieces = [(1, token)] + [(span, ''.join(tokens[i:i + span])) for span in (2, 3) if i + span <= len(tokens)]
        for span, text in pieces:
            for d, name in _options(text, words, compounds, 6 if len(text) <= 3 else 4):
                if span > 1 and not _parts_match(token, ''.join(tokens[i + 1:i + span]), name):
                    continue
                moves.append((span, d, [name]))
        if len(token) <= 3:
            # A short fragment (the cut-off end of a name, or letters under a stamp) may
            # match nothing; skipping it must not lose the rest of the reading.
            moves.append((1, .45, []))
        for cut in range(3, len(token) - 2):  # two names written or read as one word
            for d1, n1 in _options(token[:cut], words, compounds, 4):
                for d2, n2 in _options(token[cut:], words, compounds, 4):
                    moves.append((1, d1 + d2 + .15, [n1, n2]))
        for cut in range(3, len(token) - 1):
            # The start of a two-word name glued to the previous name and cut off from its
            # second word: «جاسمعبد الافير» → جاسم + عبد الأمير.
            for extra in (1, 2):
                if i + extra >= len(tokens):
                    break
                rest = ''.join(tokens[i + 1:i + 1 + extra])
                for d2, n2 in _options(token[cut:] + rest, words, compounds, 4):
                    if ' ' not in n2 or not _parts_match(token[cut:], rest, n2):
                        continue
                    for d1, n1 in _options(token[:cut], words, compounds, 3):
                        moves.append((1 + extra, d1 + d2 + .15, [n1, n2]))
        for cost, names in beams.get(i, []):
            for span, d, add in moves:
                beams.setdefault(i + span, []).append((cost + d, names + add))
        for key in (i + 1, i + 2):
            if key in beams:
                beams[key] = sorted(beams[key], key=lambda b: b[0])[:beam]
    return beams.get(len(tokens), [])


def _parts_match(first, second, name):
    """Two OCR words read as one two-word name only if each word is close to its own part
    («رين الماندين» → «زين العابدين»; not «غريب الأفير» → «عبد الأمير»)."""
    parts = normalize(name).split()
    if len(parts) != 2:
        return True
    return all(shape_distance(t, p) / max(len(t), len(p)) <= .5 for t, p in zip((first, second), parts))


def _tokens(text):
    return [t for t in re.sub(r'[^ء-ي ]', ' ', normalize(text)).split() if len(t) >= 2]


# Female given names: never a father's or grandfather's name in an Iraqi triple name.
FEMALE = set("""
مريم فاطمة خديجة زهراء هدى دعاء سارة ندى رقية آمنة ليلى سعاد نادية رنا سهام بتول سجى هبة ايمان اسراء شيماء رشا ريم منى
وفاء سناء هناء حنان كوثر نرجس زهرة زينب اسيل الاء امل انوار بشرى تبارك حوراء دنيا رحاب رغد رفل زهور سلمى سميرة شهد صبا
ضحى عبير غفران فرح لمياء لينا مروة ملاك نورا نوال هالة هيفاء وجدان ياسمين
""".split())


def reading_texts(readings):
    """Arabic letters of each reading, grouped by image-processing family (near-copies count once)."""
    families = {}
    for i, r in enumerate(readings):
        if isinstance(r, str):
            text, family = r, f'reading{i}'
        else:
            text = r.get('value', '')
            family = VARIANT_FAMILY.get(r.get('variant'), r.get('engine') or f'reading{i}')
        tokens = _tokens(text)
        if tokens and sum(map(len, tokens)) >= 4:
            families.setdefault(family, []).append(''.join(tokens))
    return [list(dict.fromkeys(v)) for v in families.values()]


def consensus_distance(groups, names):
    """How badly a name explains the readings (0 = perfectly), ignoring the worst family."""
    joined = normalize(''.join(names)).replace(' ', '')
    fits = sorted(min(shape_distance(t, joined) / max(len(joined), len(t)) for t in group) for group in groups)
    if not fits:
        return 1.0
    kept = fits[:-1] if len(fits) >= 3 else fits
    return sum(kept) / len(kept)


# Highest consensus distance still offered (tuned on scripts/evaluate_names.py).
SCORE_LIMIT = .24  # .35: 12.5% of non-name lines got a suggestion; .24: 0.8%, recall unchanged
VARIANT_FAMILY = {'color': 'plain', 'gray': 'plain', 'contrast': 'plain', 'name_margin': 'plain', 'tight': 'plain',
                  'normalized': 'normalized', 'ink': 'binary', 'pen_layer': 'pen_layer'}


def consensus_suggestions(readings, limit=3, parts=False, score_limit=None):
    """Whole-name suggestions that best fit ALL readings of the same handwritten name.

    Each reading (image variant / engine) holds part of the truth (card 2: «سليم حميلا رعي» and
    «ريم سعيدجواد» for «كريم سعيد جواد»). Candidates come from every reading and are rebuilt
    slot by slot (first, father, grandfather) from all of them. A candidate is scored by
    how well it explains each image-processing family (near-copies of one image count once),
    ignoring the worst family. The suggestions differ from each other in at least two
    names when possible. Returns [(value, score)] best first; never applied automatically.
    """
    from itertools import product
    words, compounds = _lexicon()
    families = {}
    for i, r in enumerate(readings):
        if isinstance(r, str):
            text, family = r, f'reading{i}'
        else:
            text = r.get('value', '')
            family = VARIANT_FAMILY.get(r.get('variant'), r.get('engine') or f'reading{i}')
        tokens = _tokens(text)
        if tokens and sum(map(len, tokens)) >= 4:
            families.setdefault(family, []).append(''.join(tokens))
            families[family + ':tokens'] = families.get(family + ':tokens', []) + [tokens]
    token_lists = [t for k, v in families.items() if k.endswith(':tokens') for t in v]
    groups = [list(dict.fromkeys(v)) for k, v in families.items() if not k.endswith(':tokens')]
    if not token_lists:
        return []
    sequences = []
    for tokens in token_lists:
        for cost, names in _sequences(tokens, words, compounds):
            if 2 <= len(names) <= 5 and cost / len(names) <= .38:
                sequences.append((cost / len(names), tuple(names)))
    candidates = {names for _, names in sequences}
    # Rebuild the name slot by slot from all readings: one reading may hold the right first
    # name and another the right father's name (card 2). Options ranked by their best sequence.
    by_length = {}
    for cost, names in sorted(sequences):
        by_length.setdefault(len(names), []).append(names)
    for length, group in by_length.items():
        slots = []
        for pos in range(length):
            seen = []
            for names in group:
                if names[pos] not in seen:
                    seen.append(names[pos])
            slots.append(seen[:5])
        candidates.update(product(*slots))
    # Merge candidates that overlap (one reading saw the start of the name, another the end).
    for a in list(candidates):
        for b in list(candidates):
            for k in (2, 1):
                if a != b and len(a) >= k and a[-k:] == b[:k] and len(a) + len(b) - k <= 4:
                    candidates.add(a + b[k:])
    scored = []
    for names in candidates:
        joined = normalize(''.join(names)).replace(' ', '')
        fits = sorted(min(shape_distance(text, joined) / max(len(joined), len(text)) for text in group) for group in groups)
        kept = fits[:-1] if len(fits) >= 3 else fits  # every family but the worst one
        scored.append((sum(kept) / len(kept) - .01 * len(names), names))
    scored.sort()
    score_limit = SCORE_LIMIT if score_limit is None else score_limit
    picked = []
    for score, names in scored:
        if score > score_limit:
            break
        if any(len(p) == len(names) and sum(a != b for a, b in zip(p, names)) < 2 for p, _ in picked) and len(picked) < limit - 1:
            continue  # nearly the same as a better suggestion: leave room for a different one
        picked.append((names, score))
        if len(picked) == limit:
            break
    for score, names in scored:  # fill up with the next best if diversity left places empty
        if len(picked) >= limit or score > score_limit:
            break
        if names not in [p for p, _ in picked]:
            picked.append((names, score))
    picked.sort(key=lambda p: p[1])
    return [(names if parts else ' '.join(names), round(score, 3)) for names, score in picked[:limit]]


def lexicon_suggestions(readings, limit=3, value=None):
    """Whole-name spelling suggestions (consensus_suggestions). Nothing when the field value (by
    default the first reading) is already a sequence of known names, or when the name is not
    made of known name parts."""
    words, compounds = _lexicon()
    first = value if value is not None else (readings[0] if readings else '')
    tokens = _tokens(first if isinstance(first, str) else first.get('value', ''))
    if len(tokens) >= 2 and all(t in words or t in compounds for t in tokens):
        return []
    # Hide only a suggestion identical to the field value; one image variant reading the right
    # name exactly (e.g. «علي كريم حميد» from the contrast view) is strong support, not a reason to hide it.
    shown = normalize(first if isinstance(first, str) else first.get('value', '')).replace(' ', '')
    return [v for v, _ in consensus_suggestions(readings, limit + 2) if normalize(v).replace(' ', '') != shown][:limit]


def _old_lexicon_suggestions(readings, limit=3):
    """Whole-name spelling suggestions from several OCR readings of the same name.

    Every word must match a known name part (with handwriting-typical letter
    confusions); otherwise nothing is suggested. Suggestions never replace the
    reading and never link a person automatically.
    """
    found = {}
    for reading in readings:
        tokens = [t for t in re.sub(r'[^ء-ي ]', ' ', normalize(reading)).split() if len(t) >= 2]
        if not 2 <= len(tokens) <= 6:
            continue
        options = segmentations(tokens)
        if options and options[0][0] == 0:
            continue  # already a sequence of known names: nothing to suggest
        for cost, parts in options:
            if not any(d <= .5 for _, d in parts):
                continue  # no word anchors the suggestion (e.g. an unknown name)
            value = ' '.join(name for name, _ in parts)
            if normalize(value).replace(' ', '') == ''.join(tokens):
                continue  # identical to what was read: not a suggestion
            if value not in found or cost < found[value]:
                found[value] = cost
    return [v for v, _ in sorted(found.items(), key=lambda kv: kv[1])[:limit]]
