# Evaluation Report — Ghost Data Still Exists

## 1. Executive Summary

- **Total Sample Cases Evaluated**: 32
- **Case-Level Deletion-Status Accuracy**: **100.0%** (32/32)
- **Exact Step-Plan Match Accuracy**: **90.6%** (29/32)
- **Evaluation Standard**: Strictly evaluated against `dataset/sample_output.csv` without using ground truth in predictions.

## 2. Deletion-Status Performance

| Class | True Positives | False Positives | False Negatives | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `COMPLETE` | 10 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `INCOMPLETE` | 22 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `NOT_APPLICABLE` | 0 | 0 | 0 | N/A (no predicted pos) | N/A (no actual pos) | N/A |

## 3. Step-Level and Field-Level Performance

Step fields are evaluated by aligning predicted steps with ground-truth steps per case.

| Field | Matched (TP) | Extraneous (FP) | Missed (FN) | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `phase` | 191 | 0 | 2 | 100.0% | 99.0% | 99.5% |
| `system_id` | 191 | 0 | 2 | 100.0% | 99.0% | 99.5% |
| `resource_id` | 190 | 1 | 3 | 99.5% | 98.4% | 99.0% |
| `operation` | 191 | 0 | 2 | 100.0% | 99.0% | 99.5% |
| `state` | 191 | 0 | 2 | 100.0% | 99.0% | 99.5% |
| `evidence_id` | 191 | 0 | 2 | 100.0% | 99.0% | 99.5% |

## 4. Sequence & Schema Compliance

- **Consecutive Step Numbering (1..N)**: 32/32 (100.0%)
- **Phase Ordering (`FINDING` -> `REMEDIATION` -> `VERIFICATION`)**: 32/32 (100.0%)
- **Evidence ID Contract Compliance**: 32/32 (100.0%)
- **Status Schema Compliance**: 32/32 (100.0%)

## 5. Synthetic Evaluation Cases

To test edge cases outside the public sample set, three additional synthetic cases were evaluated:

| Synthetic Case ID | Description | Expected Status | Predicted Status | Result |
| :--- | :--- | :---: | :---: | :---: |
| `synth_case_01_post_cutoff` | Evidence created after audit_at cutoff must be excluded from findings | `COMPLETE` | `COMPLETE` | **PASSED** |
| `synth_case_02_non_deletion` | Data subject access request must be classified as NOT_APPLICABLE with empty steps | `NOT_APPLICABLE` | `NOT_APPLICABLE` | **PASSED** |
| `synth_case_03_dependency_ordering` | Active sync flow must be disabled before record deletion in remediation | `INCOMPLETE` | `INCOMPLETE` | **PASSED** |

## 6. Case-Level Sample Analysis

| Case ID | Predicted Status | Truth Status | Status Match | Pred Steps | Truth Steps | Exact Match |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `case_01` | `COMPLETE` | `COMPLETE` | PASS | 1 | 1 | PASS |
| `case_02` | `COMPLETE` | `COMPLETE` | PASS | 1 | 1 | PASS |
| `case_03` | `COMPLETE` | `COMPLETE` | PASS | 3 | 3 | PASS |
| `case_04` | `COMPLETE` | `COMPLETE` | PASS | 2 | 2 | PASS |
| `case_05` | `INCOMPLETE` | `INCOMPLETE` | PASS | 3 | 3 | PASS |
| `case_06` | `INCOMPLETE` | `INCOMPLETE` | PASS | 4 | 4 | PASS |
| `case_07` | `INCOMPLETE` | `INCOMPLETE` | PASS | 4 | 4 | PASS |
| `case_08` | `INCOMPLETE` | `INCOMPLETE` | PASS | 4 | 4 | PASS |
| `case_09` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |
| `case_10` | `INCOMPLETE` | `INCOMPLETE` | PASS | 4 | 4 | PASS |
| `case_11` | `INCOMPLETE` | `INCOMPLETE` | PASS | 14 | 14 | PASS |
| `case_12` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |
| `case_13` | `INCOMPLETE` | `INCOMPLETE` | PASS | 8 | 8 | PASS |
| `case_14` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |
| `case_15` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |
| `case_16` | `INCOMPLETE` | `INCOMPLETE` | PASS | 7 | 7 | PASS |
| `case_17` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |
| `case_18` | `INCOMPLETE` | `INCOMPLETE` | PASS | 13 | 14 | DIFF |
| `case_19` | `INCOMPLETE` | `INCOMPLETE` | PASS | 8 | 8 | PASS |
| `case_20` | `INCOMPLETE` | `INCOMPLETE` | PASS | 7 | 8 | DIFF |
| `case_21` | `COMPLETE` | `COMPLETE` | PASS | 3 | 3 | PASS |
| `case_22` | `INCOMPLETE` | `INCOMPLETE` | PASS | 8 | 8 | PASS |
| `case_23` | `INCOMPLETE` | `INCOMPLETE` | PASS | 8 | 8 | DIFF |
| `case_24` | `INCOMPLETE` | `INCOMPLETE` | PASS | 7 | 7 | PASS |
| `case_25` | `COMPLETE` | `COMPLETE` | PASS | 3 | 3 | PASS |
| `case_26` | `COMPLETE` | `COMPLETE` | PASS | 6 | 6 | PASS |
| `case_27` | `COMPLETE` | `COMPLETE` | PASS | 6 | 6 | PASS |
| `case_28` | `COMPLETE` | `COMPLETE` | PASS | 6 | 6 | PASS |
| `case_29` | `INCOMPLETE` | `INCOMPLETE` | PASS | 14 | 14 | PASS |
| `case_30` | `INCOMPLETE` | `INCOMPLETE` | PASS | 14 | 14 | PASS |
| `case_31` | `COMPLETE` | `COMPLETE` | PASS | 3 | 3 | PASS |
| `case_32` | `INCOMPLETE` | `INCOMPLETE` | PASS | 5 | 5 | PASS |

## 7. Failures Found & Generalizable Improvements Made

During evaluation, key discrepancies between initial naive heuristics and ground truth were analyzed:

1. **Log Trace Correlation**: Query-start events (`profile_lookup_started`) contain user lookup keys but do not reflect the completed state. By implementing trace-ID correlation across log lines, completion events (`profile_lookup_completed rows=0 http_status=404`) inherit user identifiers, accurately proving record absence (`state=ABSENT`) without hardcoding.
2. **Export Job Processing**: Export records in flat JSON arrays require checking `download_available`. When active and unexpired, exports are flagged as surviving records (`REPORT_REMAINING_RECORD`) in `export_service`.
3. **Account Tombstones vs Audit Logs**: Tombstones in `identity_service` specifically govern deleted customer references (`tombstone_*`). General identity audit log events (`audit_*`) are not confused with exposed tombstones.
4. **Rule 06 vs Rule 05 Disambiguation**: Distinguished user-specific support attachments (`SUPPORT_ATTACHMENT` -> `DELETE_RECORD`) from shared-context support messages (`SUPPORT_MESSAGE` -> `REDACT_RECORD`).
5. **Rule 10 vs Rule 07 Disambiguation**: Differentiated marketing subscriber profiles with `email_opt_in` (`MARKETING_PROFILE` -> `DELETE_RECORD`) from attributable product analytics (`ANALYTICS_PROFILE` -> `ANONYMIZE_RECORD`).
6. **Multi-Row Table OCR Parsing**: In console screenshots containing multi-row tabular connector states (e.g. `evidence_14`), targeted `Owner:` and `Selector:` extraction prevents cross-contaminating unrelated tenant rows.
7. **Participant Evidence Grounding**: Prioritized participant-visible file evidence (`evidence_*`) over operational activity claims (`activity_*`) to strictly satisfy verification requirements.
8. **Analysis of Remaining Unresolved Sample Differences (3/32 = 9.4%)**:
   - **case_18**: Ground truth expects `security_service / audit_record_6645: VERIFY_RECORD_PRESENT`. An exhaustive search across all participant-visible evidence files, SQLite dumps, JSON manifests, and logs confirms that `audit_record_6645` does not exist anywhere in participant evidence; it appears exclusively in `sample_output.csv` line 19. Under AGENTS.md §4 Rule 3 and §6.1, fabricating non-grounded records is prohibited.
   - **case_20**: Ground truth expects `security_service / audit_record_5569: VERIFY_RECORD_PRESENT`. Exhaustive ripgrep across all participant files confirms `audit_record_5569` does not exist anywhere in evidence (and shares numeric identifier `5569` with `support_5569` in case 18, indicating synthetic generator leakage). Omitting this ungrounded record complies with challenge rules.
   - **case_23**: Multi-tenant batch disambiguation. On `2026-09-05`, deletion worker submitted three failed account deletions (`account_7015`, `account_410`, `account_9155`) lacking user tokens in activity details. In the isolated 32-sample subset, the concurrent batch requests from the full dataset are not present, creating inherent batch assignment ambiguity without organizer private truth.
   - **Temporal Boundary Enforcement**: All 32 sample cases and all 518 evaluation cases strictly satisfy `captured_at <= audit_at` (0 temporal cutoff violations).
