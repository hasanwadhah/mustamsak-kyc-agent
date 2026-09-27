# KYC evaluation — heldout split

Generated 2026-09-27. 64 images, threshold 0.90, calibration applied. Synthetic, fictional documents only.

## Fields

| scope | fields | read | accuracy when read | misread | auto-accepted | accuracy of auto-accepted | routed to human |
|---|---|---|---|---|---|---|---|
| all | 400 | 83.2% | 91.3% | 7.2% | 58.5% | 99.2% | 41.5% |
| critical | 192 | 84.9% | 87.1% | 10.9% | 63.0% | 98.4% | 37.0% |
| level: clean | 120 | 100.0% | 92.5% | 7.5% | 89.2% | 99.1% | 10.8% |
| level: poor | 215 | 93.0% | 92.5% | 7.0% | 58.1% | 100.0% | 41.9% |
| level: worst | 65 | 20.0% | 61.5% | 7.7% | 3.1% | 50.0% | 96.9% |
| kind: business_license | 96 | 90.6% | 80.5% | 17.7% | 61.5% | 100.0% | 38.5% |
| kind: national_id | 224 | 79.5% | 96.6% | 2.7% | 56.2% | 99.2% | 43.8% |
| kind: tax_card | 80 | 85.0% | 91.2% | 7.5% | 61.3% | 98.0% | 38.8% |

### By field

| field | fields | read | accuracy when read | auto-accepted | accuracy of auto-accepted |
|---|---|---|---|---|---|
| activity | 16 | 100.0% | 81.2% | 62.5% | 100.0% |
| birth_date | 16 | 100.0% | 100.0% | 75.0% | 100.0% |
| birth_place | 16 | 100.0% | 93.8% | 62.5% | 100.0% |
| business_name | 32 | 90.6% | 89.7% | 81.2% | 100.0% |
| document_number | 32 | 78.1% | 100.0% | 68.8% | 100.0% |
| expiry_date | 48 | 83.3% | 100.0% | 72.9% | 100.0% |
| father_name | 16 | 75.0% | 100.0% | 56.2% | 100.0% |
| first_name | 16 | 75.0% | 83.3% | 56.2% | 100.0% |
| grandfather_name | 16 | 68.8% | 100.0% | 43.8% | 100.0% |
| issue_date | 48 | 93.8% | 97.8% | 66.7% | 100.0% |
| license_number | 16 | 75.0% | 91.7% | 56.2% | 100.0% |
| mother_name | 16 | 68.8% | 100.0% | 37.5% | 100.0% |
| name | 48 | 83.3% | 65.0% | 41.7% | 100.0% |
| national_number | 16 | 81.2% | 84.6% | 62.5% | 90.0% |
| sex | 16 | 68.8% | 100.0% | 6.2% | 100.0% |
| surname | 16 | 62.5% | 100.0% | 43.8% | 100.0% |
| tax_number | 16 | 87.5% | 85.7% | 56.2% | 88.9% |

## Calibration

Expected calibration error: raw 0.077, calibrated 0.0704 (lower is better; 0 means stated confidence equals observed accuracy).

| confidence bin | fields | mean confidence | observed accuracy |
|---|---|---|---|
| 0.5-0.6 | 35 | 53.5% | 82.9% |
| 0.6-0.7 | 17 | 65.7% | 41.2% |
| 0.7-0.8 | 35 | 75.8% | 68.6% |
| 0.8-0.9 | 12 | 84.6% | 100.0% |
| 0.9-1.0 | 234 | 97.2% | 99.1% |

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
| heldout-003 | serial_mismatch | poor, poor, poor, poor | review | yes | 5 |
| heldout-004 | name_mismatch | clean, poor, clean, poor | review | yes | 2 |
| heldout-005 | serial_mismatch | poor, clean, poor, poor | review | yes | 2 |
| heldout-006 | — | clean, clean, clean, poor | review | — | 1 |
| heldout-007 | — | poor, poor, clean, worst | review | — | 3 |
| heldout-008 | expired_license | poor, worst, poor, worst | review | no | 7 |
| heldout-009 | — | worst, clean, poor, poor | review | — | 4 |
| heldout-010 | — | worst, poor, clean, poor | review | — | 4 |
| heldout-011 | serial_mismatch | worst, poor, clean, poor | review | yes | 2 |
| heldout-012 | serial_mismatch | poor, clean, poor, poor | review | yes | 2 |
| heldout-013 | — | poor, clean, clean, poor | review | — | 1 |
| heldout-014 | name_mismatch | poor, poor, poor, worst | review | yes | 3 |
| heldout-015 | — | worst, poor, clean, clean | review | — | 5 |

### Example reviewer summary

```
Needs human review — 1 item(s):
1. not identified: national ID card (front). 1 document(s) have an unknown type or side — set it manually or retake the photo
Ask for a new photo: national ID card (unknown side): The lighting is too dark; photograph near a light source without shadows on the document.
```

Average processing time: 6.85 s per image (CPU).
