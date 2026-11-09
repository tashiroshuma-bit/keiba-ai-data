# v51 body-weight independent chronological exploratory evaluation — 2026-11-09

## Decision: DO NOT PROMOTE

The canonical Library SQLite v11 was SHA256-verified against PROJECT_STATE: `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`, 322,170,880 bytes. It contains 11,201 validated races and 154,191 runner rows (2023–2026). The table `jra_model_pair_replay_evidence` has **0** rows, so **no genuine contemporaneous v50-v51 paired performance comparison is possible**. These numbers MUST NOT be labeled v50 accuracy.

## Exploratory ability-adjusted historical comparator

Reproducible local Python entrypoint: `v51_bodyweight_exploratory_repro.py` (delivered as conversation artifact). This is a new *auxiliary baseline*, not the production v50 A+horse-adjusted-jockey-residual model.

- Historical covariates for horses and jockeys recomputed by date using a two-calendar-day availability **assumption**; no verified historical publication timestamps. No current final odds or current finishing position used as input features.
- Baseline: per-race softmax model using historical horse win/top3/last normalized place/starts, historical jockey win/top3/starts, age, sex, days since previous linked start; horse ID remains missing rather than guessed.
- Body-weight branch: official reported `body_weight_change_raw` discrete bins, missing bin, change × age<=3, change × >90-day rest interactions. The baseline coefficients are fixed when adding weight effects. Softmax output renormalized by race.
- 2023–2024 fitting; regularization selected on 2025 by Log Loss (0.003 among 0.003, 0.01, 0.03, 0.1, 0.3, 1.0); 2026 only used for evaluation within THIS experiment. 2025/2026 already inspected elsewhere; **not an untouched prospective or external holdout**.
- No actual saved v50 probabilities are compared, and no production routing is modified.

| Period | Races | Measure | Auxiliary baseline | + Body weight |
|---|---:|---|---:|---:|
| 2025 | 2925 | First choice winner | 20.444% | 20.718% |
| 2025 | 2925 | Winner in model top 3 | 49.641% | 49.573% |
| 2025 | 2925 | Winner Log Loss | 2.342814 | 2.342454 |
| 2025 | 2925 | Brier | 0.885886 | 0.885815 |
| 2025 | 2925 | Exact unordered podium | 103 | 104 |
| 2025 | 2925 | Exact ordered podium | 18 | 18 |
| 2026 | 2411 | First choice winner | 21.153% | 21.029% |
| 2026 | 2411 | Winner in model top 3 | 47.905% | 47.822% |
| 2026 | 2411 | Winner Log Loss | 2.364639 | 2.364320 |
| 2026 | 2411 | Brier | 0.887987 | 0.888128 |
| 2026 | 2411 | Exact unordered podium | 100 | 97 |
| 2026 | 2411 | Exact ordered podium | 26 | 26 |

Paired date-block bootstrap, 2026 (89 racing dates, 3,000 seeded resamples):
- Log Loss change (+weight minus baseline): -0.000319, 95% CI [-0.001362, +0.000694].
- First-choice accuracy change (+weight minus baseline): -0.124 percentage points, 95% CI [-0.454, +0.211] percentage points.
- Both intervals include zero; improvement is not demonstrated. Top3 unordered declines 100→97.
- This is statistical association, not causal body-weight impact. Missingness is explicit. Pre-off availability is **assumed**, not authenticated; old races' PDF published dates have not been proven.

## Formal production gate status

1. ✅ Canonical v11 SHA256 and runner-row reproducibility checked.
2. ✅ Auxiliary chronological training/selection/testing executed; results rerun in a new Python process, exit code 0.
3. ✅ Rank metrics and race-date bootstrap computed; benefit not established.
4. ❌ Saved, timestamp-authenticated v50 win probabilities per actual same race/horse field unavailable (`jra_model_pair_replay_evidence=0`).
5. ❌ Verified pre-off publication timestamp evidence for complete bodyweight/horse histories unavailable.
6. ❌ v50 vs v51 true paired independent prospective validation impossible from current evidence; no automatic v51 production promotion.
7. ⚠ GitHub CI / scheduled forecast production execution not verified by this report.

**Keep PROJECT_STATE.standard_forecast=v50**, keep `operations/prediction_policy/standard_v50.json` and `scripts/standard_v50_forecast.py` unchanged. v51 body-weight branch remains research-only; research result does not pass adoption criteria. Future gate must archive per-race, per-runner complete v50 probabilities and authentic pre-off bodyweight snapshots, compare all required metrics on exact same fields, with a new truly unseen time period.