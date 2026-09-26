"""Synthetic stress test for handwritten-name suggestions (app/housing_names.consensus_suggestions).

No real person's data: names are drawn from the app's vocabulary of common name parts and
corrupted the way OCR corrupts handwritten Arabic (lost teeth, dot and shape slips, joined or
split words, stray letters). Each name gets several readings, like the image variants the app
reads. Reports, per noise level, how often the true name is the first suggestion and how often
it is among the three offered; and how often a non-name line (form text, random letters)
wrongly gets a suggestion.

  python scripts/evaluate_names.py [--names 200] [--seed 7]
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.focused_fields import normalize  # noqa: E402
from app.housing_names import CONFUSABLE, COMPOUNDS, MORE_COMPOUNDS, MORE_NAMES, NAME_WORDS, SHAPE_ALIKE, EASY_GAP, consensus_suggestions  # noqa: E402

LEVELS = {  # probability per letter of: lost tooth/small letter, dot slip, shape slip, other deletion, stray letter
    'light': (.06, .05, .03, .01, .01),
    'medium': (.14, .10, .07, .03, .03),
    'heavy': (.25, .16, .12, .06, .05),
}
LETTERS = 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي'
NON_NAMES = ['جمهورية العراق', 'وزارة الداخلية', 'مديرية الجنسية العامة', 'مكتب المعلومات المركزي', 'عنوان السكن',
             'رقم الاستمارة', 'اسم رب الاسرة', 'مديرية شؤون', 'تاريخ تنظيم الاستمارة', 'ضابط المكتب']


def corrupt(name, level, rng):
    lost, dot, shape, delete, stray = LEVELS[level]
    out = []
    for ch in normalize(name):
        if ch == ' ':
            out.append('' if rng.random() < .35 else ' ')  # OCR joins neighbouring names
            continue
        r = rng.random()
        if ch in EASY_GAP and r < lost:
            continue
        r = rng.random()
        group = next((g for g in CONFUSABLE if ch in g), None)
        if group and r < dot:
            ch = rng.choice(sorted(group))
        elif rng.random() < shape:
            group = next((g for g in SHAPE_ALIKE if ch in g), None)
            if group:
                ch = rng.choice(sorted(group))
        if rng.random() < delete:
            continue
        out.append(ch)
        if rng.random() < stray:
            out.append(rng.choice(LETTERS))
        if rng.random() < .04:
            out.append(' ')  # OCR splits a name
    return ''.join(out)


def random_name(rng, parts):
    pool = sorted(NAME_WORDS | MORE_NAMES)
    names = [rng.choice(pool) for _ in range(parts)]
    if rng.random() < .2:
        names[rng.randrange(parts)] = rng.choice(COMPOUNDS + MORE_COMPOUNDS)
    return ' '.join(names)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--names', type=int, default=200)
    parser.add_argument('--readings', type=int, default=3)
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    for level in LEVELS:
        top1 = top3 = offered = 0
        started = time.time()
        for _ in range(args.names):
            truth = random_name(rng, rng.choice((3, 3, 4)))
            readings = [corrupt(truth, level, rng) for _ in range(args.readings)]
            found = [v for v, _ in consensus_suggestions(readings)]
            want = normalize(truth)
            offered += bool(found)
            top1 += bool(found) and normalize(found[0]) == want
            top3 += want in [normalize(v) for v in found]
        n = args.names
        print(f'{level:7} true name first: {top1 / n:6.1%}   in the 3 offered: {top3 / n:6.1%}   '
              f'any suggestion: {offered / n:6.1%}   ({(time.time() - started) / n:.2f} s/name)')
    wrong = 0
    trials = 0
    for text in NON_NAMES:
        for level in ('light', 'medium'):
            trials += 1
            wrong += bool(consensus_suggestions([corrupt(text, level, rng) for _ in range(args.readings)]))
    for _ in range(100):
        trials += 1
        junk = ' '.join(''.join(rng.choice(LETTERS) for _ in range(rng.randint(3, 6))) for _ in range(3))
        wrong += bool(consensus_suggestions([junk]))
    print(f'non-names given a suggestion: {wrong}/{trials} ({wrong / trials:.1%})')


if __name__ == '__main__':
    main()
