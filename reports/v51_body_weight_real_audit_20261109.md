# 馬体重増減実測監査（2026-11-09）— v51研究候補、正式昇格なし

## Provenance
- Canonical Library: jra_2023_2025.sqlite v11, 322170880 bytes
- SHA256: 7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627
- Source: annual_report_races JOIN annual_report_runners, validated_result only, official PDF payload keys `body_weight_raw` and `body_weight_change_raw`
- Validated races: 11201; validated runner rows: 154191; parsed numerical changes: 117336; unknown/newcomer/invalid changes: 36855
- Date coverage: 2023–2026 (2026 complete historical DB only through Oct 18; November 8 supplement is podium-only and not mixed)
- Relative changes are observed reported changes, not horse-ID matched changes.
- All 11201 validated fields have 1 observed winner and full rows (checked). Includes missing-delta runners as unknown in denominators; no imputation.

## Observations: unadjusted, not causal

| Delta kg | N | Winner N | Win % | Top3 % | Winners / field-size uniform expectation |
|--|--:|--:|--:|--:|--:|
| <= -20 | 271 | 4 | 1.476 | 7.749 | 0.214 |
| -19..-10 | 4529 | 236 | 5.211 | 15.743 | 0.733 |
| -9..-4 | 19804 | 1341 | 6.771 | 20.410 | 0.940 |
| -3..+3 | 50132 | 3787 | 7.554 | 22.931 | 1.040 |
| +4..+9 | 30116 | 2200 | 7.305 | 21.985 | 1.008 |
| +10..+19 | 11150 | 794 | 7.121 | 20.395 | 0.990 |
| >=+20 | 1334 | 88 | 6.597 | 17.616 | 0.934 |
| unknown | 36855 | 2751 | 7.464 | 22.252 | 1.014 |

Totals winner counts 11201. Field-size expected uses sum(1/declared runner count). It is NOT a v50 benchmark or an ability-adjusted statistical test.

## Exploratory time split
- Choose smoothed bucket-only factors using 2023–2024, compare with uniform 1/N on 2025–2026, 5336 races.
- Uniform log loss 2.59746; body-weight-only log loss 2.59558; delta 0.00188 in favor of weight-only.
- This is a **tiny descriptive diagnostic**, NOT evidence of improving v50; 2025/2026 historical data previously inspected in other research, so cannot describe as untouched holdout.
- Weight-only ranking top pick 409/5336. Do not compare that hit-rate with v50: no same-race v50 forecast file exists in the canonical database's `jra_model_pair_replay_evidence` (0 records at inspection).
- Confounding remains: horse ability, age, class, layoff, running condition, starting field size and missing-weights mechanism. Confidence intervals must account for races and repeated horses.

## Gate / next experimental requirements
1. Align actual pre-off v50 race/runner probability snapshots with body weights known at the same as-of. Provenance / official horse IDs must be tracked.
2. Freeze training period strictly before evaluation; evaluate paired races and an independent prospective sample.
3. Fit effects regularized to neutral; missing and debut delta must be a separate explicit value, not zero.
4. Required metrics: 1st-choice hit %, true winner top3 capture, exact podium ordered/unordered, racewise LogLoss/Brier and confidence intervals.
5. Only promote after demonstrable non-degradation/improvement on independent paired data and data-integrity checks. Standard v50 remains unchanged; v51 is a research candidate.

## Implementation bug discovered
The initial `scripts/body_weight_audit.py` (commit ffc974b) looked for normalized keys (body_weight / body_weight_change), but the canonical `annual_report_runners.payload_json` actually contains `body_weight_raw` and `body_weight_change_raw`. Its original logic would therefore produce missing-data statistics. Fix the parser before running it and use this report's audited source columns.