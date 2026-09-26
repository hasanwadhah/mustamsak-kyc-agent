# Architecture

How Mustamsak turns document photos into a pass / hand-over decision.

## System map

```
Browser
  static/agent.html + agent.js (+ agent-i18n.js)   KYC agent screen, English / Arabic
  static/index.html + *.js  (served at /workspace) full reviewer workspace: edit fields, crop, pair, print
        │  POST /api/capture-check   photo quality before reading (no OCR, nothing stored)
        │  POST /api/batches         upload (images / PDF), or POST /api/demo/cases/{id}
        │  GET  /api/batches/{id}    live progress
        │  GET  /api/batches/{id}/kyc?threshold=&profile=   decision
        ▼
app/main.py — FastAPI on 127.0.0.1 only (TrustedHost, Origin check, CSP), one worker thread
        │
app/pipeline.py  per page:
        vision.detect_regions   find every document quad in the photo (several per photo allowed)
        vision.warp             cut out and straighten
        capture.assess          cut-off, glare, blur, dark, bright, contrast, tilt, too small
        arabic_ocr.read         PP-OCRv5: detect once, recognise every box in Arabic and English
        vision.classify         type + side from printed keywords and layout
        understanding / focused_fields   label-anchored field reading, dates, MRZ, card serials
        handwritten_digits + number_reader   handwritten Arabic-Indic numbers (models trained here)
        grouping / paired_fields             ID front ↔ back pairing
        │
app/kyc.py  (read-only decision layer)
        validate_field   formats, dates, expiry, MRZ check digits
        corroborate      the same fact on two documents = independent evidence
        calibrated       isotonic curve fitted on the tune split
        cross_checks     name ID ↔ licence ↔ tax card, card number front ↔ back, …
        decision         pass | review, with reasons and a bilingual summary
```

## Rules the code never breaks

1. **Blank and flagged beats invented.** No code path fills in, completes, "corrects" or guesses a field
   value. Tolerant matching (`textmatch`) locates *labels*, never values. OCR merging only combines text
   that one of the recognizers actually produced.
2. **`kyc.py` is read-only.** It never changes a document (tested).
3. **Human decisions win.** Manual or verified fields are never overwritten by automation, and they count
   as confidence 1.0.
4. **Local first.** There are no network calls while reading. The optional Gemini reader is off by default,
   needs the user's own key and consent for each image, and only ever suggests (`docs/EXTERNAL_API.md`).
5. **Only fictional documents** in `eval/`. `scripts/check_no_real_data.py` enforces this.
6. **Calibration is fitted on the tune split only.** The held-out split is only reported.
7. **Out of scope:** face matching, liveness, forgery detection.

## Confidence model

1. **Own evidence** (`kyc.raw_confidence`). The OCR score is capped by the reading status: read 1.0 ·
   uncertain .80 · approximate .60 · conflict .45 · partial date .30. Checksums (MRZ check digits, a paired
   card serial) raise it to at least .97. Plausibility caps apply: a one-digit date part (.80), a one- or
   two-letter name part (.60), Latin letters or digits inside an Arabic name (.40). Photo problems
   multiply it: ×.85 when a retake is advised, ×.95 for a warning. A human-approved field is 1.0; a
   missing or unreadable one is 0.
2. **Corroboration** (`kyc.corroborate`). The same fact read identically on two documents combines as
   independent evidence: `1 − (1−a)(1−b)`, at most .99.
3. **Calibration** (`models/kyc_calibration.json`). A monotone isotonic curve fitted on the tune split
   by `scripts/evaluate_kyc.py --fit`.
4. **Threshold** (default .90, adjustable on the decision screen). The file goes to a person if any of
   these holds:
   - a critical field is below the threshold or blank;
   - a validation or cross-check failed;
   - a required document is missing or unidentified.

   Otherwise it **passes**.
5. **Summary.** One reason per problem, each linked to its document and field, in English and Arabic.

## Critical fields

| Document | Critical fields |
|---|---|
| National ID, front | name, national number, card number |
| National ID, back | card number, birth date, expiry date |
| Passport | name, document number, birth date, expiry date |
| Business licence | owner name, business name, licence number, expiry date |
| Tax card | taxpayer name, tax number |

Profiles: `individual` (identity only) or `merchant` (identity + business licence + tax card). The
default `auto` picks merchant when a licence or tax card is present.

## Data model (stored in `data/`, git-ignored)

- **Batch** `{id, status: queued|processing|ready|failed|interrupted, progress, message, sources[], documents[]}`
- **Document** `{id, image_id, points, segmentation, capture[], kind, side, fields[], ocr[], reviewed, …}`
- **Field** `{key, label, value, confidence, status: read|uncertain|approximate|conflict|unreadable|missing|manual, method, box, candidates?, note?}`
- **KYC result** `{decision, threshold, calibration, requirements[], documents[{fields[{confidence, below_threshold, checks[], corroborated_by?}]}], cross_checks[], reasons[], summary, summary_en}`

## Evaluation protocol

```
python scripts/synthetic_kyc.py --split tune --cases 16      # seed 11, even name pools
python scripts/synthetic_kyc.py --split heldout --cases 16   # seed 907, odd name pools (disjoint)
python scripts/evaluate_kyc.py --split tune --fit            # fit calibration on tune only
python scripts/evaluate_kyc.py --split heldout               # report → eval/reports/kyc-heldout.md
```

- Each case is ID front + back, business licence and tax card for one fictional person.
- About a third of the cases carry a planted problem: another person's licence, an expired licence, or an
  ID back from another card.
- Photo quality: 30% clean, 40% poor, 30% worst. The degradations are angle, perspective, dim or dark
  light, glare, a thumb or paper over the text, a cut-off corner, blur or motion, noise and JPEG.
- Metrics that matter most: **false passes on files with a problem** (must be 0), **passed files with a
  wrong critical field** (must be 0), accuracy of auto-accepted fields, ECE, and the share of worst-photo
  fields routed to a person.
