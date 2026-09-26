# KYC evaluation — heldout split

Generated 2026-09-26. 64 images, threshold 0.90, calibration applied. Synthetic, fictional documents only.

## Fields

| scope | fields | read | accuracy when read | misread | auto-accepted | accuracy of auto-accepted | routed to human |
|---|---|---|---|---|---|---|---|
| all | 400 | 82.2% | 91.2% | 7.2% | 41.8% | 98.8% | 58.2% |
| critical | 192 | 82.8% | 86.8% | 10.9% | 48.4% | 97.9% | 51.6% |
| level: clean | 120 | 100.0% | 92.5% | 7.5% | 62.5% | 98.7% | 37.5% |
| level: poor | 215 | 91.6% | 92.4% | 7.0% | 41.9% | 100.0% | 58.1% |
| level: worst | 65 | 18.5% | 58.3% | 7.7% | 3.1% | 50.0% | 96.9% |
| kind: business_license | 96 | 90.6% | 80.5% | 17.7% | 35.4% | 100.0% | 64.6% |
| kind: national_id | 224 | 79.5% | 96.6% | 2.7% | 45.5% | 99.0% | 54.5% |
| kind: tax_card | 80 | 80.0% | 90.6% | 7.5% | 38.8% | 96.8% | 61.3% |

### By field

| field | fields | read | accuracy when read | auto-accepted | accuracy of auto-accepted |
|---|---|---|---|---|---|
| activity | 16 | 100.0% | 81.2% | 62.5% | 100.0% |
| birth_date | 16 | 100.0% | 100.0% | 56.2% | 100.0% |
| birth_place | 16 | 100.0% | 93.8% | 62.5% | 100.0% |
| business_name | 32 | 90.6% | 89.7% | 81.2% | 100.0% |
| document_number | 32 | 78.1% | 100.0% | 68.8% | 100.0% |
| expiry_date | 48 | 83.3% | 100.0% | 29.2% | 100.0% |
| father_name | 16 | 75.0% | 100.0% | 31.2% | 100.0% |
| first_name | 16 | 75.0% | 83.3% | 12.5% | 100.0% |
| grandfather_name | 16 | 68.8% | 100.0% | 18.8% | 100.0% |
| issue_date | 48 | 93.8% | 97.8% | 35.4% | 100.0% |
| license_number | 16 | 75.0% | 91.7% | 18.8% | 100.0% |
| mother_name | 16 | 68.8% | 100.0% | 31.2% | 100.0% |
| name | 48 | 83.3% | 65.0% | 39.6% | 100.0% |
| national_number | 16 | 81.2% | 84.6% | 62.5% | 90.0% |
| sex | 16 | 68.8% | 100.0% | 6.2% | 100.0% |
| surname | 16 | 62.5% | 100.0% | 37.5% | 100.0% |
| tax_number | 16 | 62.5% | 80.0% | 31.2% | 80.0% |

## Calibration

Expected calibration error: raw 0.0819, calibrated 0.0549 (lower is better; 0 means stated confidence equals observed accuracy).

| confidence bin | fields | mean confidence | observed accuracy |
|---|---|---|---|
| 0.6-0.7 | 63 | 66.8% | 82.5% |
| 0.7-0.8 | 37 | 78.3% | 81.1% |
| 0.8-0.9 | 62 | 82.4% | 85.5% |
| 0.9-1.0 | 167 | 95.7% | 98.8% |

## Capture guidance

| measure | value |
|---|---|
| retake_rate_clean | 0.0% |
| retake_rate_poor | 28.6% |
| retake_rate_worst | 55.6% |
| cut_off_recall | 100.0% |
| cut_off_images | 1 |
| cut_off_false_alarm_rate | 0.0% |
| glare_detected_rate | 35.7% |
| classification_accuracy | 87.5% |

## KYC decisions

- Cases: 16 (8 with a planted inconsistency)
- False passes on flawed cases: **0**
- Planted flaw named in the reviewer summary: 75.0%
- Automatic pass rate on consistent cases: 0.0%
- Consistent cases where every critical field was read correctly: 0 (automatic pass rate among them: —)
- Passed cases containing a wrong critical field: **0**

| case | planted problem | photo levels | decision | problem named | wrong critical fields |
|---|---|---|---|---|---|
| heldout-000 | — | worst, poor, poor, clean | review | — | 4 |
| heldout-001 | — | clean, clean, clean, poor | review | — | 2 |
| heldout-002 | name_mismatch | poor, poor, poor, clean | review | no | 3 |
| heldout-003 | serial_mismatch | poor, poor, poor, poor | review | yes | 6 |
| heldout-004 | name_mismatch | clean, poor, clean, poor | review | yes | 2 |
| heldout-005 | serial_mismatch | poor, clean, poor, poor | review | yes | 2 |
| heldout-006 | — | clean, clean, clean, poor | review | — | 1 |
| heldout-007 | — | poor, poor, clean, worst | review | — | 3 |
| heldout-008 | expired_license | poor, worst, poor, worst | review | no | 7 |
| heldout-009 | — | worst, clean, poor, poor | review | — | 5 |
| heldout-010 | — | worst, poor, clean, poor | review | — | 4 |
| heldout-011 | serial_mismatch | worst, poor, clean, poor | review | yes | 3 |
| heldout-012 | serial_mismatch | poor, clean, poor, poor | review | yes | 2 |
| heldout-013 | — | poor, clean, clean, poor | review | — | 1 |
| heldout-014 | name_mismatch | poor, poor, poor, worst | review | yes | 4 |
| heldout-015 | — | worst, poor, clean, clean | review | — | 5 |

### Example reviewer summary

```
Needs human review — 3 item(s):
1. not identified: national ID card (front). 1 document(s) have an unknown type or side — set it manually or retake the photo
2. licence number (business licence): "BL-29272" at 79% confidence, below the 90% threshold — compare with the image
3. expiry date (business licence): "2027/03/14" at 79% confidence, below the 90% threshold — compare with the image
Ask for a new photo: national ID card (unknown side): The lighting is too dark; photograph near a light source without shadows on the document.
```

Average processing time: 5.18 s per image (CPU).
