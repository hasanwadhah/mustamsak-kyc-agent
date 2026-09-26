# KYC evaluation — tune split

Generated 2026-09-26. 64 images, threshold 0.90, calibration applied. Synthetic, fictional documents only.

## Fields

| scope | fields | read | accuracy when read | misread | auto-accepted | accuracy of auto-accepted | routed to human |
|---|---|---|---|---|---|---|---|
| all | 400 | 70.8% | 86.9% | 9.2% | 32.8% | 100.0% | 67.2% |
| critical | 192 | 69.3% | 82.0% | 12.5% | 39.6% | 100.0% | 60.4% |
| level: clean | 86 | 96.5% | 96.4% | 3.5% | 65.1% | 100.0% | 34.9% |
| level: poor | 182 | 91.2% | 89.8% | 9.3% | 36.3% | 100.0% | 63.7% |
| level: worst | 132 | 25.8% | 50.0% | 12.9% | 6.8% | 100.0% | 93.2% |
| kind: business_license | 96 | 58.3% | 67.9% | 18.8% | 17.7% | 100.0% | 82.3% |
| kind: national_id | 224 | 76.3% | 93.6% | 4.9% | 42.9% | 100.0% | 57.1% |
| kind: tax_card | 80 | 70.0% | 85.7% | 10.0% | 22.5% | 100.0% | 77.5% |

### By field

| field | fields | read | accuracy when read | auto-accepted | accuracy of auto-accepted |
|---|---|---|---|---|---|
| activity | 16 | 62.5% | 80.0% | 37.5% | 100.0% |
| birth_date | 16 | 81.2% | 92.3% | 37.5% | 100.0% |
| birth_place | 16 | 75.0% | 91.7% | 56.2% | 100.0% |
| business_name | 32 | 81.2% | 69.2% | 37.5% | 100.0% |
| document_number | 32 | 78.1% | 100.0% | 75.0% | 100.0% |
| expiry_date | 48 | 58.3% | 96.4% | 20.8% | 100.0% |
| father_name | 16 | 81.2% | 100.0% | 37.5% | 100.0% |
| first_name | 16 | 81.2% | 92.3% | 31.2% | 100.0% |
| grandfather_name | 16 | 68.8% | 90.9% | 18.8% | 100.0% |
| issue_date | 48 | 66.7% | 93.8% | 18.8% | 100.0% |
| license_number | 16 | 56.2% | 88.9% | 12.5% | 100.0% |
| mother_name | 16 | 75.0% | 100.0% | 18.8% | 100.0% |
| name | 48 | 70.8% | 58.8% | 31.2% | 100.0% |
| national_number | 16 | 87.5% | 100.0% | 81.2% | 100.0% |
| sex | 16 | 68.8% | 100.0% | 6.2% | 100.0% |
| surname | 16 | 75.0% | 75.0% | 37.5% | 100.0% |
| tax_number | 16 | 50.0% | 75.0% | 6.2% | 100.0% |

## Calibration

Expected calibration error: raw 0.05, calibrated 0.035 (lower is better; 0 means stated confidence equals observed accuracy).

| confidence bin | fields | mean confidence | observed accuracy |
|---|---|---|---|
| 0.6-0.7 | 63 | 67.0% | 68.3% |
| 0.7-0.8 | 45 | 78.1% | 82.2% |
| 0.8-0.9 | 44 | 82.7% | 79.5% |
| 0.9-1.0 | 131 | 95.5% | 100.0% |

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
- Planted flaw named in the reviewer summary: 60.0%
- Automatic pass rate on consistent cases: 0.0%
- Consistent cases where every critical field was read correctly: 0 (automatic pass rate among them: —)
- Passed cases containing a wrong critical field: **0**

| case | planted problem | photo levels | decision | problem named | wrong critical fields |
|---|---|---|---|---|---|
| tune-000 | name_mismatch | poor, worst, worst, worst | review | yes | 8 |
| tune-001 | — | poor, clean, poor, poor | review | — | 5 |
| tune-002 | — | worst, clean, clean, worst | review | — | 5 |
| tune-003 | — | poor, clean, worst, poor | review | — | 5 |
| tune-004 | expired_license | poor, poor, poor, worst | review | no | 4 |
| tune-005 | — | clean, worst, worst, poor | review | — | 8 |
| tune-006 | — | clean, clean, poor, poor | review | — | 2 |
| tune-007 | — | worst, poor, clean, poor | review | — | 3 |
| tune-008 | expired_license | worst, poor, clean, clean | review | no | 2 |
| tune-009 | name_mismatch | poor, poor, poor, clean | review | yes | 3 |
| tune-010 | serial_mismatch | worst, clean, worst, poor | review | yes | 6 |
| tune-011 | — | poor, clean, worst, worst | review | — | 6 |
| tune-012 | — | poor, worst, poor, clean | review | — | 6 |
| tune-013 | — | poor, poor, worst, poor | review | — | 5 |
| tune-014 | — | worst, clean, poor, worst | review | — | 8 |
| tune-015 | — | poor, worst, worst, poor | review | — | 7 |

### Example reviewer summary

```
Needs human review — 6 item(s):
1. not identified: national ID card (back). 2 document(s) have an unknown type or side — set it manually or retake the photo
2. not identified: business licence. 2 document(s) have an unknown type or side — set it manually or retake the photo
3. full name (national ID card (front)): "ليلى قاسم يوسف الزبيدي" at 83% confidence, below the 90% threshold (conflicting readings) — compare with the image
4. full name (tax card): "ليلى قاسم يوسف الزبيدي" at 83% confidence, below the 90% threshold — compare with the image
5. tax number (tax card): not read — left blank, never filled in
6. Name: national ID card (front) vs tax card: appear to match but reading confidence is below threshold ("ليلى قاسم يوسف الزبيدي" / "ليلى قاسم يوسف الزبيدي")
Ask for a new photo: unidentified document: Part of the document is outside the frame (left); retake with a margin around all four edges. | unidentified document: The lighting is too dark; photograph near a light source without shadows on the document.
```

Average processing time: 8.24 s per image (CPU).
