# Usage Report — Ghost Data Still Exists

## 1. System Architecture & Model Calls

The Ghost Data Still Exists deletion audit agent is designed as a **deterministic, evidence-grounded neuro-symbolic engine** combining:
1. **Deterministic Intent Classifier**: Rule-based multilingual parser supporting English, Spanish, French, German, and Portuguese with regex boundary tokens.
2. **Relational Identity Resolver**: SQLite-backed temporal indexing across `user_identities.csv` and historical `user_audit_log.csv`.
3. **Multi-Source Evidence Extractor**: Structured SQLite parser, JSON snapshot deserializer, structured log analyzer, and OCR cache reader.
4. **Remediation Planner**: Deterministic phase-ordered planner with tie-breaking according to specification priority.

## 2. Model Usage & Cost Summary

Because all audit decisions, rule evaluations, and remediation plans are executed deterministically on-device without external LLM API calls during inference:

| Model Provider | Model Name | Total Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| Fully Deterministic / On-Device | None (Deterministic Rules) | 0 | 0 | 0 | 0 | $0.00 |

## 3. Per-Request Metrics

- **Total Requests Processed**: 518 evaluation requests
- **Average Model Calls per Request**: 0.0
- **Average Tokens per Request**: 0.0
- **Average Cost per Request**: $0.00
- **Total Estimated Inference Cost**: **$0.00**

## 4. Development & Coding Harness Context

- **Development Coding Harness**: Antigravity (`tool=Antigravity`)
- **Runtime Assistance Model**: `model=Gemini 3.8 Flash (High)`
- **Code Execution**: Pure Python 3.11 with SQLite3 and Pandas for offline temporal evaluation.
