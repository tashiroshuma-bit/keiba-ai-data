# v51 prospective pilot validation 2026-11-09 (19:xx JST)

## Proven operational test results
- PR [#4](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/4) merged to main via squash `fcd126069e9d1bf2f7254afd87c390fa8c95a830`.
- GitHub Actions [run 42605493968](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42605493968): test job **success**, legacy-diagnostics **success**.
- Verified in run job steps: v50 related historical/rider tests, body weight research capture unit tests, new synthetic CLI round-trip, main keiba_v48 tests and compileall all **success**.
- Initial run [42605187840](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42605187840) **failed** because `scripts/body_weight_audit.py` misbucketed exact -20 and -10 kg. Fixed in PR #4. Regression rerun **passed**.
- All synthetic test records are non-JRA fixtures; they do **not** demonstrate current racing data source availability, prospective prediction uptime, or v51 superiority.
- Genuine latest canonical DB v11 and auxiliary 2025/2026 historical evaluation are as recorded in `reports/v51_body_weight_validation_decision_20261109.md` (no v50 paired saved forecast).
- `PROJECT_STATE.standard_forecast.version=v50` remains unchanged. No v51 promotion.

## Outstanding criteria for actual operational verification
1. Obtain authentic pre-off `source_model=A` race input and execute `scripts/standard_v50_forecast.py` against canonical DB with matching SHA256.
2. Capture genuine *full-field* announced weights with original source bytes (not merely a claimed URL/hash), provenance, at least one verified observation time **before** each race off.
3. Execute `scripts/capture_v50_bodyweight.py` with original A-input, saved v50 output and same-asof weight manifest, preserving immutable capture output and evidence bytes.
4. After official results become available, execute `scripts/evaluate_v50_v51_weight_pairs.py` with full official finish order and provenance.
5. Evaluate a truly later, unseen race cohort under fixed parameters, sufficient dates for clustered uncertainty estimates; assess top1/top3, exact podium, logloss/Brier, and no leakage before production selection.

## Decision
`GATE=HOLD`: verified **software-only** round-trip with synthetic inputs. **No** authenticated real race preoff capture. **No** genuinely independent measured v50-v51 uplift. The calendar is 2026-11-09; upcoming JRA meetings 2026-11-14/15 according to JRA 2026 race calendar. Do not backdate, fabricate future data, or claim completed live validation.
