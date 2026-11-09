# V51 research backlog and 2026-11-14/15 real-data execution protocol
Date: 2026-11-09 JST. **Research-only. Standard v50 unchanged.**

## Verified current state
- JRA official website shows Tokyo/Kyoto/Fukushima on Sat Nov 14 and Sun Nov 15, 2026. See https://www.jra.go.jp/ and https://www.jra.go.jp/keiba/calendar2026/2026/11/1114.html (advance schedule is provisional).
- PROJECT_STATE.json: canonical Library SQLite v11 SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`; complete history through 2026-10-18, 2026-11-08 supplement is podium only.
- Standard v50 active by user policy; `operations/prediction_policy/standard_v50.json`. Reused legacy A model probabilities plus rider residual T=.7; 2026-11-01 (23 races) comparison did **not** demonstrate statistical improvement: Log Loss v50 2.27434 vs A 2.26425, [reports/v50/V50_REAL_HISTORICAL_STATISTICAL_REPORT_20261102.md](../../reports/v50/V50_REAL_HISTORICAL_STATISTICAL_REPORT_20261102.md).
- Fitted general v51 candidate `operations/prediction_policy/v51_candidate_fitted_research.json`: 2025 2890 races top1 baseline 608, candidate 588; Log Loss 2.375821 vs 2.383844; 2026 2384 races top1 baseline 470, candidate 486; Log Loss 2.408272 vs 2.417495. Candidate failed independent historical chronological gates; do not promote.
- Bodyweight auxiliary 2026 2411 races: first choice 21.153% without vs 21.029% with; Log Loss 2.364639 vs 2.364320 (95% day-block CI includes zero), exact unordered top3 100 vs 97. This is **not** v50 same-race comparison; see [report](../../reports/v51_body_weight_validation_decision_20261109.md).
- Ranking research `keiba_v48/RANKING_RESULTS.md`: stagewise top3 candidate 2025 3329 races baseline first-choice 19.98% vs 22.20%; 2026 2707 races 18.62% vs 20.24% under 2-day assumed historical availability. 2026 unordered full-podium 3.44% vs 3.47%, hardly changed. Historic exploratory and **not** actual v50-v51 calibrated comparison.
- `scripts/v50_difficulty_flags.py` flags low p1, tight first-second gap, many runners, high entropy; **unvalidated** as error predictor.
- Unlinked horse rows 77,317 (2026 26,021), jockey 6,349 (2026 1,198) at project state snapshot. These are *not* legitimate imputation targets by name alone.
- [GitHub Actions CI run 42605493968](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42605493968) passed synthetic capture+evaluator CLI tests. Real end-to-end race execution remains unproven.

## Improvement priority queue, before altering v51 coefficients
| Rank | Workstream | Why / evidence | Trial feature or implementation | Validation / release gate |
|---|---|---|---|---|
| P0 | Verified pre-off full-field snapshots and authentic horse identity | 0 truly prospective same-asof v50/v51 races; missing 77k horse links. Largest validity bottleneck, not demonstrated accuracy gain | Persist immutable original web bytes and capture timestamps; horse number+name+official ID + asof; no name-only joins | No synthetic rows, SHA match, exact field match, publication time <= asof < off, 100% field or exclude race |
| P0 | Same-race probability and ordered-top3 evaluation | Existing scripts use p1 rank to proxy ordered podium; actual joint ordered 3-horse maximum differs | Compare proper P(1), P(2), P(3) conditional distributions + joint sequential PL as a *separately labeled approximation*; ensure distinctions in reports | Paired complete fields, ranking type explicit, no post-off features, independent official finish order |
| P1 | Horse baseline ability / recent form | Recent rank model 2025 +2.22pp and 2026 +1.63pp first-choice in exploratory cohort but near-zero unordered podium gain | Time-lagged horse ability: last 3 races, opponent strength, race class changes, speed and margin, recency; official IDs only | Head-to-head vs frozen v50 SAME genuine preoff snapshot; day-block bootstrap; missingness coverage logged |
| P1 | Jockey-by-course/distance with horse-adjusted residual and limited sample shrinkage | Current v50 rider overlay uses turf/dirt and T=.7; 23-race independent day not improved | Add course × surface × distance bucket hierarchical residual, past ride count, slope/cold-start, rider/horse pairing | Compare fixed candidate alpha/regularization selected only on earlier chronology; no leakage, minimum samples |
| P1 | Class strength and field opposition | Expected finish depends on opponents, class and number of starters; existing enriched_features computes opponent_quality | Race-specific opposition-adjusted form and class promotion/demotion with missing-value flags; avoid using current outcome | Equal cohort paired v50 vs candidate; calibration logloss/Brier and winner top3 |
| P1 | 2nd/3rd-place conditional ordering | Previous historical research improved 1st pick but 3-horse full capture stays ~3.5% | Separate conditional 2nd/3rd models with valid no-repeat joint probability; simultaneous p2/p3 calibration | Exact unordered/ordered podium and separate 1st,2nd,3rd marginal validation; racing-day bootstrap |
| P2 | Track-day bias / ground by race as-of | Same-day bias is informative only when earlier races genuinely complete before target off | Rolling earlier-race pace, 4th-corner positions, inner/outer performance by surface/going | Timestamp prove earlier results observed before cutoff; no retrospective same-day leakage |
| P2 | Layoff and body weight interactions, age/growth | 2026 bodyweight-only addition did not improve hit-rate; may be heterogenous | Weight delta percent of previous, age 2/3/4+, rest days, previous best weight, first start as explicit missing | Out-of-time subgroup and correction for multiplicity; no global penalty chosen from winning bucket |
| P2 | Race uncertainty and upset calibration | `v50_difficulty_flags.py` thresholds are descriptive not validated | Entropy / top-two gap / field size stratified calibration, optional abstain/report-confidence, not horse reweighting | Cross-validated reliability; no claimed win probability boost |
| P3 | Odds as separate market research axis | `standard_v50_forecast.py` odds overlay research is not validated, current final odds forbidden | Preoff quote timestamp and market implied odds, calibrate alpha for quality separate from rank goals | Model comparison free of post-off final odds; return rate secondary |

## 2026-11-14/15 field readiness gate
Scheduled tasks registered 2026-11-09 via automations:
- Friday 2026-11-13 at ~21:00 JST preflight;
- Saturday/Sunday 2026-11-14/15 09:00-16:00 JST hourly real-data watch;
- Saturday/Sunday 2026-11-14/15 at 19:00 JST result reconciliation.
Schedules are **attempts**, not guarantees. Failure must be reported; avoid false "100% operational" claims.

**Blocking checklist**
1. For each race, immutable source A input with observed asof, original off timestamp, all runner IDs/numbers/p1; genuine source-time evidence.
2. Authentic same-race preoff body weights; archived original source bytes + SHA256 + acquisition time; false / missing capture => no official prediction count.
3. Canonical v11 actually materializes with SHA256 equal to PROJECT_STATE. Repository root stub must not be used as canonical.
4. v50 generated from current source A with official standard entrypoint; original input hash retained.
5. Frozen output written with `scripts/capture_v50_bodyweight.py`; source original archived and verified on readback; no overwrite.
6. After official full finish order (including dead heats/scratches handling), result evaluator `scripts/evaluate_v50_v51_weight_pairs.py`; report coverage numerator/denominator and exclusion reasons.
7. Winner top1, winner in top3, exact podium ordered/unordered, Log Loss/Brier and same-race deltas; preserve v50 immutable and V51 shadow.
8. If first day samples small, report descriptive not "statistically significant", and don't refit weights on heldout weekend.

## Promotion criterion
Do not promote v51 until real same-asof prospective records for enough distinct race days, stable provenance and no error/coverage regression; predeclare primary metric (first-choice accuracy) and probability guardrails (LogLoss/Brier), require independent positive evidence. Numbers from prior 2025/2026 exploratory reports are not untouched prospective evidence.
