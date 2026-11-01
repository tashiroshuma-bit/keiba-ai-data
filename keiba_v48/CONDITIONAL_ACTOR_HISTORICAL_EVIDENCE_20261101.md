# Conditional actor historical comparison: evidence and next gate

## Existing historical benchmark (saved, not re-run)

Source: keiba_v48/reports/actor_hit/evaluation_lag2.json

| Year | Races | Prior calibrated winner hits | Horse index only | Jockey index only | Equal horse+jockey |
|---|---:|---:|---:|---:|---:|
| 2025 | 3329 | 745 (22.38%) | 271 (8.14%) | 611 (18.35%) | 562 (16.88%) |
| 2026 | 2707 | 564 (20.83%) | 209 (7.72%) | 533 (19.69%) | 479 (17.69%) |

This is an existing **actor index** comparison, not a distance/going feature or
horse-adjusted rider residual ablation. It uses assumed historical result
publication lags; it is retrospective research, not formal production evidence.

## New feature implementations

- keiba_v48/conditional_horse_features.py computes prior-only distance,
  surface, going, track and opponent-score availability summaries.
- keiba_v48/rider_ability_adjusted.py computes prior-only full-field
  observational jockey residuals against horse pre-race scores.
- keiba_v48/horse_confidence_pipeline.py supports opt-in frozen confidence
  overlay; default is unchanged.

## Missing integration evidence

The full-card October 31 roster has career counts and jockey-form proxies, but
does not itself contain each runner's full historical race-by-race going and
distance history, nor each historical field's horse **pre-race** scores. Joining
current actor index snapshots to historical races would leak future data.
No condition-specific accuracy number is claimed.

Next reproducible replay must read canonical historical starts, index by horse
and jockey IDs, join by race cutoff and source availability, compute each
historical horse's pre-race strength before estimating rider residual, then
compare same-card baseline / horse conditions / rider residual / combined.
Keep 2025 and 2026 as separately reported evaluation cohorts and never tune
on the reported cohort.

## Promotion status

Research only; production remains v49 until replay evidence and tests pass.
