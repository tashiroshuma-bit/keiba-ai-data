# v4.8 Offline data pipeline v5 (2026-10-18)

This package does NOT include historical race-level data or a fitted predictive model. No live connection to JRA or subscription feed is available in the runtime. Never describe a test fixture as a historical backtest.

## Data contract

Input UTF-8 CSV columns: see `production_pipeline.FIELDS`. Every runner needs an immutable horse_id and jockey_id, off_timestamp and odds_timestamp with ISO8601 timezone offsets, pre_off_odds, and a source_url. One row per runner per race. `finish_position` and `final_win_odds` are POST-RACE LABELS ONLY. Source URLs and original snapshot files must be retained separately for audit. Historical race results cannot reconstruct timestamped pre-off odds. Set a fixed cutoff (default five minutes before scheduled off); do not backfill later quotes. Scratch/non-finish/dead heat require special handling and are excluded by current baseline evaluator.

## Commands

`python -m unittest discover -s keiba_v48 -p 'test_*.py'`

`python keiba_v48/production_pipeline.py YOUR_CSV --output-dir output`

`python keiba_v48/backtest_engine.py output/features.csv --output output/market_baseline.json`

Note: `backtest_engine.py` checks pre-off timestamps but not the five-minute cutoff. Always run `production_pipeline.py` first. It uses final_win_odds for settlement only. The market-normalized baseline is NOT a trained v4.8 model. `score_field`/`alpha` are untrained until an independently validated training process is implemented.

## Sources
- JRA official graded races: https://www.jra.go.jp/datafile/seiseki/index.html
- JRA 2025 graded race index: https://www.jra.go.jp/datafile/seiseki/replay/2025/jyusyo.html
- JRA 2024 graded race index: https://www.jra.go.jp/datafile/seiseki/replay/2024/jyusyo.html
- JRA 2023 graded race index: https://www.jra.go.jp/datafile/seiseki/replay/2023/jyusyo.html

## Release blockers
1. Obtain legally reusable official runner-level snapshots with provenance and time-stamped odds, or restrict testing to prediction-only and mark ROI unavailable.
2. Normalize identifiers and prove parser correctness on actual JRA pages.
3. Train on 2023, tune 2024, lock model and evaluate 2025 (or expanding rolling windows), with no future race features.
4. Implement joint outcome probabilities and settlement for wide/trifecta tickets using their own timestamped odds.
5. Evaluate against popularity and market baselines, report missing-data coverage and bootstrap uncertainty.
