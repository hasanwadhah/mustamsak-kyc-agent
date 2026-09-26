"""Lexicon-constrained reading of a handwritten name line (suggestions only).

The line recognizer (PP-OCR) is trained on print; on handwriting its best single guess
drops most of what it saw (a garbled three-letter string for a full three-part name). Its full per-frame letter
probabilities keep more: the probability of a *known* name can still be the highest among
names. This module scores candidate names directly on those probabilities (CTC), summed
over several views of the line (tight crop, horizontally stretched, contrast-enhanced), and
improves the best candidates slot by slot (first name, father, grandfather).

It only ranks suggestions; the field value is never changed, and a name made of words
outside the vocabulary gets no suggestion from here.
"""
import cv2
import numpy as np

from . import arabic_ocr


def _recognizer():
    return arabic_ocr.engine('arabic').text_rec


def _probabilities(rgb):
    rec = _recognizer()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    norm = rec.resize_norm_img(bgr, max(w / max(1, h), rec.rec_image_shape[2] / rec.rec_image_shape[1]))
    with arabic_ocr.LOCK:
        return rec.session(norm[np.newaxis].astype(np.float32))[0]


def views(crop):
    """Views of the handwritten line: tight around its ink, stretched, and contrast-enhanced."""
    from . import handwritten_digits as hd
    mask, _ = hd.local_mask(crop)
    rows = np.nonzero((mask > 0).sum(1) > .03 * mask.shape[1])[0]
    tight = crop[max(0, rows.min() - 3):min(crop.shape[0], rows.max() + 4)] if len(rows) else crop
    gray = cv2.cvtColor(tight, cv2.COLOR_RGB2GRAY)
    contrast = cv2.cvtColor(cv2.createCLAHE(2.5, (8, 8)).apply(gray), cv2.COLOR_GRAY2RGB)
    stretch = lambda image: cv2.resize(image, None, fx=1.5, fy=1, interpolation=cv2.INTER_CUBIC)
    stretch2 = lambda image: cv2.resize(image, None, fx=2, fy=1, interpolation=cv2.INTER_CUBIC)
    return [tight, stretch(tight), stretch2(tight), stretch(contrast)]


def _label(text, index):
    # The recognizer emits the line left to right; Arabic is written right to left.
    return [index[c] for c in text[::-1] if c in index]


def ctc_log_probability(probabilities, label):
    """log P(label | per-frame probabilities), CTC forward algorithm (blank = class 0)."""
    log_p = np.log(np.maximum(probabilities, 1e-12))
    extended = [0]
    for c in label:
        extended += [c, 0]
    extended = np.asarray(extended)
    size = len(extended)
    can_skip = np.zeros(size, bool)
    can_skip[2:] = (extended[2:] != 0) & (extended[2:] != extended[:-2])
    alpha = np.full(size, -np.inf)
    alpha[0] = log_p[0, 0]
    if size > 1:
        alpha[1] = log_p[0, extended[1]]
    frame = log_p[:, extended]
    for t in range(1, len(log_p)):
        one = np.concatenate([[-np.inf], alpha[:-1]])
        two = np.where(can_skip, np.concatenate([[-np.inf, -np.inf], alpha[:-2]]), -np.inf)
        alpha = np.logaddexp(np.logaddexp(alpha, one), two) + frame[t]
    return float(np.logaddexp(alpha[-1], alpha[-2]) if size > 1 else alpha[-1])


def ctc_batch(probabilities, labels):
    """ctc_log_probability for many labels at once (padded), for searching the whole name list."""
    log_p = np.log(np.maximum(probabilities, 1e-12))
    size = 2 * max(len(l) for l in labels) + 1
    extended = np.zeros((len(labels), size), int)
    valid = np.zeros((len(labels), size), bool)
    for i, label in enumerate(labels):
        ext = [0]
        for c in label:
            ext += [c, 0]
        extended[i, :len(ext)] = ext
        valid[i, :len(ext)] = True
    ends = np.array([2 * len(l) for l in labels])
    can_skip = np.zeros_like(valid)
    can_skip[:, 2:] = (extended[:, 2:] != 0) & (extended[:, 2:] != extended[:, :-2]) & valid[:, 2:]
    frame = log_p[:, extended]  # (T, N, S)
    alpha = np.full((len(labels), size), -np.inf)
    alpha[:, 0] = frame[0, :, 0]
    alpha[:, 1] = np.where(ends > 0, frame[0, :, 1], -np.inf)
    blocked = np.full((len(labels), 1), -np.inf)
    for t in range(1, len(log_p)):
        one = np.concatenate([blocked, alpha[:, :-1]], axis=1)
        two = np.where(can_skip, np.concatenate([blocked, blocked, alpha[:, :-2]], axis=1), -np.inf)
        alpha = np.where(valid, np.logaddexp(np.logaddexp(alpha, one), two) + frame[t], -np.inf)
    rows = np.arange(len(labels))
    last = alpha[rows, ends]
    before = np.where(ends > 0, alpha[rows, np.maximum(ends - 1, 0)], -np.inf)
    return np.logaddexp(last, before)


class LineScorer:
    """Scores names against one handwritten line (cached per name)."""

    def __init__(self, crop):
        from .focused_fields import normalize
        self.normalize = normalize
        rec = _recognizer()
        self.index = {c: i for i, c in enumerate(rec.postprocess_op.character)}
        self.probabilities = [_probabilities(v) for v in views(crop)]
        self.cache = {}

    def __call__(self, name):
        """Mean over the views of the per-letter log-probability of the name (higher is better)."""
        text = self.normalize(name)
        if text not in self.cache:
            label = _label(text, self.index)
            letters = max(1, len(text.replace(' ', '')))
            self.cache[text] = float(np.mean([ctc_log_probability(p, label) / letters for p in self.probabilities]))
        return self.cache[text]

    def many(self, names):
        """Scores for many names at once (same scale as __call__)."""
        texts = [self.normalize(n) for n in names]
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if todo:
            labels = [_label(t, self.index) for t in todo]
            letters = np.array([max(1, len(t.replace(' ', ''))) for t in todo])
            total = np.mean([ctc_batch(p, labels) / letters for p in self.probabilities], axis=0)
            self.cache.update(zip(todo, map(float, total)))
        return [self.cache[t] for t in texts]

    def greedy(self):
        """The recognizer's own best reading of each view (for the plausibility margin)."""
        rec = _recognizer()
        chars = rec.postprocess_op.character
        out = []
        for p in self.probabilities:
            idx, prev, text = p.argmax(1), -1, []
            for i in idx:
                if i != prev and i != 0:
                    text.append(chars[i])
                prev = i
            out.append(''.join(text)[::-1])
        return out


# Weight of the readings' agreement against the image evidence (tuned on 6 development
# name lines: true name first 4/6 and in the top 3 5/6, vs 3/6 and 5/6 on image evidence alone).
READINGS_WEIGHT = 4.0
# A suggestion needs either readings that agree with it or strong image evidence.
MAX_READING_DISTANCE = .30
MIN_IMAGE_SCORE = -1.2
# A household head is usually a man: a female first name needs a little more evidence.
FEMALE_FIRST_PENALTY = .15
# Also offered: readings reasonably close AND image evidence reasonably strong (blurred photos).
SOFT_READING_DISTANCE, SOFT_IMAGE_SCORE = .36, -2.3
# Names typed or confirmed on this computer (families and neighbours share names) count a little
# more: per name part, small next to the gaps clear evidence leaves (≈ .4 on the development cards).
LEARNED_BONUS = .06


def rank_names(crop, seeds, pool, readings=(), limit=3, rounds=2):
    """Best names for the line: [(name, score)], best first; [] when nothing is convincing.

    seeds: candidate name tuples (housing_names.consensus_suggestions(..., parts=True));
    pool: name parts to try in every slot. Each seed is improved slot by slot: every pool
    name is tried in one slot with the others fixed and the best is kept. A candidate's
    score is its image evidence (per-letter CTC log-probability over the line views) minus
    READINGS_WEIGHT x how badly it explains the OCR readings. Father's and grandfather's
    names are never female (Iraqi triple names).
    """
    from .housing_names import FEMALE, consensus_distance, reading_texts, learned_names
    from .focused_fields import normalize
    if not seeds:
        return []
    learned = {normalize(w) for w in learned_names()}
    image = LineScorer(crop)
    groups = reading_texts(readings)
    distance = {}
    found = {}

    def score(names_list):
        evidence = image.many([' '.join(n) for n in names_list])
        for names, e in zip(names_list, evidence):
            key = tuple(names)
            if key not in distance:
                distance[key] = consensus_distance(groups, key) if groups else 0.0
            penalty = FEMALE_FIRST_PENALTY if key and key[0] in FEMALE else 0.0
            bonus = LEARNED_BONUS * sum(normalize(part) in learned for part in key)
            found[key] = (e, distance[key], e - READINGS_WEIGHT * distance[key] - penalty + bonus)

    for seed in seeds:
        current = list(seed)
        score([current])
        for _ in range(rounds):
            changed = False
            for slot in range(len(current)):
                options = [n for n in pool if slot == 0 or n not in FEMALE]
                trials = [current[:slot] + [name] + current[slot + 1:] for name in options]
                score(trials)
                best = max(trials, key=lambda t: found[tuple(t)][2])
                if found[tuple(best)][2] > found[tuple(current)][2]:
                    current = best
                    changed = True
            if not changed:
                break
    ranked = sorted(found.items(), key=lambda kv: -kv[1][2])
    soft = lambda v: SOFT_READING_DISTANCE is not None and v[1] <= SOFT_READING_DISTANCE and v[0] >= SOFT_IMAGE_SCORE
    accepted = [(names, v[2]) for names, v in ranked
                if v[1] <= MAX_READING_DISTANCE or v[0] >= MIN_IMAGE_SCORE or soft(v)]
    # Offer genuinely different alternatives: skip a name that differs from a better one in a
    # single slot while places remain (a blurred card's top three were all «صباح …»).
    picked = []
    for names, value in accepted:
        close = any(len(p) == len(names) and sum(a != b for a, b in zip(p, names)) < 2 for p, _ in picked)
        if close and len(picked) < limit - 1:
            continue
        picked.append((names, value))
        if len(picked) == limit:
            break
    for names, value in accepted:
        if len(picked) >= limit:
            break
        if names not in [p for p, _ in picked]:
            picked.append((names, value))
    picked.sort(key=lambda p: -p[1])
    return [(' '.join(names), round(value, 3)) for names, value in picked[:limit]]


def suggest(crop, readings):
    """Name suggestions for a handwritten line, from its image and its OCR readings."""
    from .housing_names import _lexicon, consensus_suggestions
    # Starting points only: loose, because what is finally offered is decided here on the image
    # and the readings together (a blurred card's readings were all past the text threshold).
    seeds = [tuple(names) for names, _ in consensus_suggestions(readings, 6, parts=True, score_limit=.45)]
    if not seeds:
        return []
    words, compounds = _lexicon()
    pool = sorted(set(words.values()) | set(compounds.values()))
    return rank_names(crop, seeds, pool, readings)
