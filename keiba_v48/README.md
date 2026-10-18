# v4.8 research prototype

Status: model architecture implemented, NOT trained or historically backtested. `model.py` includes market implied probability normalization, pre-race feature score adjustment and Plackett-Luce ordered finish distribution for a complete field. Do not use a subset of runners to estimate race probabilities. A calibrated full-field fitted score model is still required.

## Input table: one row per runner per race
race_id, race_date, cutoff_timestamp, horse_id, horse_name, horse_number, gate, jockey_id, trainer_id, sex, age, carried_weight, body_weight, body_weight_change, odds_timestamp, win_odds, last1_to_last4_finish, last1_to_last4_distance, last1_to_last4_surface, last1_to_last4_speed_or_time, last1_to_last4_race_date, days_since_last, historical_course_stats_asof, track_condition_asof, prior_turf_race_bias_asof, finish_position, win_payout.

`finish_position` and `win_payout` are target/evaluation fields and MUST NEVER enter features. `odds_timestamp` and all historical feature observation timestamps must be <= cutoff_timestamp. Archived final odds are not proof of pre-race availability; record the timestamp and origin.

## Backtest procedure
1. Assemble complete fields and verified point-in-time data for 2023-2025 JRA graded races.
2. Time-split training 2023, validation 2024, holdout 2025; expand history if coverage allows. 2026 Akikasho is an audit case, not holdout after review.
3. Fit multinomial/horse-ranking features on training only, calibrate on validation only. Market-only Plackett-Luce is a baseline, not a trained v4.8 model.
4. Calculate finish-order likelihood, win log-loss, Brier score, top-three probability calibration, and all-bet ROI with actual payouts. For place/wide/trifecta, compute exact combinations from the full ordering distribution, never multiply marginal probabilities.
5. Compare against same-timestamp market-only and popularity baseline with equal capital and no-bet allowed; track max drawdown and sample size.
6. Block bets with missing odds/payouts or time leakage. Confidence bounds via race-level bootstrap.

## Evidence / provenance
JRA official 2025 Akikasho race card: https://www.jra.go.jp/keiba/thisweek/2025/1019_2/syutsuba.html
JRA official 2025 Akikasho result: https://jra.jp/datafile/seiseki/g1/shuka/result/shuka2025.html
JRA official 2024 Kikuka Sho result: https://jra.jp/datafile/seiseki/g1/kikka/result/kikka2024.html

## Current blocker
The isolated code environment cannot access the public internet, and the retrieved web excerpts do not provide a machine-readable, verified point-in-time full-field dataset. Therefore no fitted coefficients or v4.8 backtest ROI are reported.

## New ingestion gate (2026-10-18)
`pipeline.py` reads one runner per row CSV using `runners_template.csv` and generates a JSON race-level audit. Example: `python pipeline.py runners.csv --output audit.json`. It rejects after-cutoff odds/features, duplicate IDs, invalid odds, incomplete field, missing source, and inconsistent timestamps. A `field_complete=yes` attestation is required per runner; a source file alone cannot prove completeness. Dead heats, cancellations and disqualifications require explicit custom handling before model training. Do not fill absent odds with final odds. No historical data has been ingested yet; synthetic assertions only test safeguards.

Recommended source: licensed JRA-VAN Data Lab JV-Link setup (historical RA/SE and odds snapshots) or verified user-exported CSV. JRA result PDFs alone do not establish point-in-time odds. Export the full-field table with timezone-qualified ISO8601 timestamps. `finish_position` and payout are labels, not predictors.
