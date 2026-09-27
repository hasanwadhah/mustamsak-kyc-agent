# KYC evaluation — tune split

Generated 2026-09-27. 64 images, threshold 0.90, calibration applied. Synthetic, fictional documents only.

## Fields

| scope | fields | read | accuracy when read | misread | auto-accepted | accuracy of auto-accepted | routed to human |
|---|---|---|---|---|---|---|---|
| all | 400 | 72.2% | 88.2% | 8.5% | 47.2% | 99.5% | 52.8% |
| critical | 192 | 70.3% | 85.2% | 10.4% | 50.0% | 99.0% | 50.0% |
| level: clean | 86 | 100.0% | 98.8% | 1.2% | 91.9% | 100.0% | 8.1% |
| level: poor | 182 | 91.8% | 90.4% | 8.8% | 55.5% | 99.0% | 44.5% |
| level: worst | 132 | 27.3% | 52.8% | 12.9% | 6.8% | 100.0% | 93.2% |
| kind: business_license | 96 | 59.4% | 71.9% | 16.7% | 34.4% | 97.0% | 65.6% |
| kind: national_id | 224 | 76.3% | 93.6% | 4.9% | 54.0% | 100.0% | 46.0% |
| kind: tax_card | 80 | 76.2% | 88.5% | 8.8% | 43.8% | 100.0% | 56.2% |

### By field

| field | fields | read | accuracy when read | auto-accepted | accuracy of auto-accepted |
|---|---|---|---|---|---|
| activity | 16 | 62.5% | 80.0% | 43.8% | 100.0% |
| birth_date | 16 | 81.2% | 92.3% | 62.5% | 100.0% |
| birth_place | 16 | 75.0% | 91.7% | 56.2% | 100.0% |
| business_name | 32 | 81.2% | 69.2% | 37.5% | 100.0% |
| document_number | 32 | 78.1% | 100.0% | 75.0% | 100.0% |
| expiry_date | 48 | 58.3% | 100.0% | 47.9% | 100.0% |
| father_name | 16 | 81.2% | 100.0% | 62.5% | 100.0% |
| first_name | 16 | 81.2% | 92.3% | 43.8% | 100.0% |
| grandfather_name | 16 | 68.8% | 90.9% | 56.2% | 100.0% |
| issue_date | 48 | 75.0% | 91.7% | 43.8% | 100.0% |
| license_number | 16 | 56.2% | 100.0% | 18.8% | 100.0% |
| mother_name | 16 | 75.0% | 100.0% | 37.5% | 100.0% |
| name | 48 | 70.8% | 58.8% | 35.4% | 94.1% |
| national_number | 16 | 87.5% | 100.0% | 81.2% | 100.0% |
| sex | 16 | 68.8% | 100.0% | 18.8% | 100.0% |
| surname | 16 | 75.0% | 75.0% | 50.0% | 100.0% |
| tax_number | 16 | 62.5% | 100.0% | 43.8% | 100.0% |

## Calibration

Expected calibration error: raw 0.0689, calibrated 0.0533 (lower is better; 0 means stated confidence equals observed accuracy).

| confidence bin | fields | mean confidence | observed accuracy |
|---|---|---|---|
| 0.5-0.6 | 34 | 53.4% | 67.6% |
| 0.6-0.7 | 32 | 66.5% | 50.0% |
| 0.7-0.8 | 15 | 75.9% | 80.0% |
| 0.8-0.9 | 19 | 84.6% | 84.2% |
| 0.9-1.0 | 189 | 97.0% | 99.5% |

## Capture guidance

| measure | value |
|---|---|
| retake_rate_clean | 0.0% |
| retake_rate_poor | 21.4% |
| retake_rate_worst | 61.9% |
| cut_off_recall | 85.7% |
| cut_off_images | 7 |
| cut_off_false_alarm_rate | 3.5% |
| glare_detected_rate | 56.2% |
| classification_accuracy | 85.9% |

## KYC decisions

- Cases: 16 (5 with a planted inconsistency)
- False passes on flawed cases: **0**
- Planted flaw named in the reviewer summary: 100.0%
- Automatic pass rate on consistent cases: 0.0%
- Consistent cases where every critical field was read correctly: 0 (automatic pass rate among them: —)
- Passed cases containing a wrong critical field: **0**

| case | planted problem | photo levels | decision | problem named | wrong critical fields |
|---|---|---|---|---|---|
| tune-000 | name_mismatch | poor, worst, worst, worst | review | yes | 8 |
| tune-001 | — | poor, clean, poor, poor | review | — | 4 |
| tune-002 | — | worst, clean, clean, worst | review | — | 4 |
| tune-003 | — | poor, clean, worst, poor | review | — | 4 |
| tune-004 | expired_license | poor, poor, poor, worst | review | yes | 4 |
| tune-005 | — | clean, worst, worst, poor | review | — | 8 |
| tune-006 | — | clean, clean, poor, poor | review | — | 2 |
| tune-007 | — | worst, poor, clean, poor | review | — | 3 |
| tune-008 | expired_license | worst, poor, clean, clean | review | yes | 1 |
| tune-009 | name_mismatch | poor, poor, poor, clean | review | yes | 3 |
| tune-010 | serial_mismatch | worst, clean, worst, poor | review | yes | 6 |
| tune-011 | — | poor, clean, worst, worst | review | — | 6 |
| tune-012 | — | poor, worst, poor, clean | review | — | 5 |
| tune-013 | — | poor, poor, worst, poor | review | — | 5 |
| tune-014 | — | worst, clean, poor, worst | review | — | 7 |
| tune-015 | — | poor, worst, worst, poor | review | — | 7 |

### Example reviewer summary

```
Needs human review — 6 item(s):
1. not identified: national ID card (back). 2 document(s) have an unknown type or side — set it manually or retake the photo
2. not identified: business licence. 2 document(s) have an unknown type or side — set it manually or retake the photo
3. full name (national ID card (front)): "ليلى قاسم يوسف الزبيدي" at 86% confidence, below the 90% threshold (conflicting readings) — compare with the image
4. full name (tax card): "ليلى قاسم يوسف الزبيدي" at 86% confidence, below the 90% threshold — compare with the image
5. tax number (tax card): not read — left blank, never filled in
6. Name: national ID card (front) vs tax card: appear to match but reading confidence is below threshold ("ليلى قاسم يوسف الزبيدي" / "ليلى قاسم يوسف الزبيدي")
Ask for a new photo: unidentified document: Part of the document is outside the frame (left); retake with a margin around all four edges. | unidentified document: The lighting is too dark; photograph near a light source without shadows on the document.
```

Average processing time: 5.06 s per image (CPU).
