# v4.8 学習・検証パイプライン

開発の共通入口は **[統合台帳](../DEVELOPMENT_HANDOFF.md)**、機械可読の現在値は **[PROJECT_STATE.json](../PROJECT_STATE.json)**。別スレッド・旧ZIPからも最初に参照してください。

最新の検証は **[DEEP_RESEARCH_RESULTS.md](DEEP_RESEARCH_RESULTS.md)**。正本DBはversion 8、利用可能10,056レース。6課題の修正と全候補保存を実施しましたが、クラス修復後候補は収益悪化で不採用。本番重みを維持しています。

初回の修復・悪化診断は [OFFLINE_REPAIR_RESULTS.md](OFFLINE_REPAIR_RESULTS.md) に当時の結果として保存しています。

前回の追加実装・396レース比較・本番昇格見送りは **[COMPLETION_RESULTS.md](COMPLETION_RESULTS.md)** を参照。以下の旧記録と区別してください。

以前の[結果オッズ基準・確率予測の試験本番採用](PRODUCTION_POLICY.md)に、2025年218レースの検証、未連携IDの原因、稼働コマンドを記録しています。

重賞・一般競走を含む公式年度別全成績の取り込みは [ANNUAL_IMPORT.md](ANNUAL_IMPORT.md) を参照。

10項目の改善コードと実行手順は **[IMPROVEMENTS.md](IMPROVEMENTS.md)** を参照。
新しい入口は `improvements.py`（train / predict / evaluate / settle）。
構造モデル・校正・リスク管理・固定予測台帳を実装済み。最新の回顧検証と真の前向き検証の未完了を区別します。
以下は旧プロトタイプの仕様・当時の状況として残している。

# v4.8 research prototype

Status: model architecture implemented, NOT trained or historically backtested. `model.py` includes market implied probability normalization, pre-race feature score adjustment and Plackett-Luce ordered finish distribution for a complete field. Do not use a subset of runners to estimate race probabilities. A calibrated full-field fitted score model is still required.

## Input table: one row per runner per race
race_id, race_date, cutoff_timestamp, horse_id, horse_name, horse_number, gate, jockey_id, trainer_id, sex, age, carried_weight, body_weight, body_weight_change, odds_timestamp, win_odds, last1_to_last4_finish, last1_to_last4_distance, last1_to_last4_surface, last1_to_last4_speed_or_time, last1_to_last4_race_date, days_since_last, historical_course_stats_asof, track_condition_asof, prior_turf_race_bias_asof, finish_position, win_payout.

`finish_position` and `win_payout` are target/evaluation fields and MUST NEVER enter features. `odds_timestamp` and all historical feature observation timestamps must be <= cutoff_timestamp. Archived final odds are not proof of pre-race availability; record the timestamp and origin.

## Backtest procedure
1. Assemble complete fields and verified point-in-time data for 2023-2025 JRA graded races.
2. Time-split training 2023, validation 2024, exploratory reference 2025 (already inspected; not an unseen holdout); expand history if coverage allows. 2026 Akikasho is an audit case, not holdout after review.
3. Fit multinomial/horse-ranking features on training only, calibrate on validation only. Market-only Plackett-Luce is a baseline, not a trained v4.8 model.
4. Calculate finish-order likelihood, win log-loss, Brier score, top-three probability calibration, and all-bet ROI with actual payouts. For place/wide/trifecta, compute exact combinations from the full ordering distribution, never multiply marginal probabilities.
5. Compare against same-timestamp market-only and popularity baseline with equal capital and no-bet allowed; track max drawdown and sample size.
6. Block bets with missing odds/payouts or time leakage. Confidence bounds via race-level bootstrap.

## Evidence / provenance
JRA official 2025 Akikasho race card: https://www.jra.go.jp/keiba/thisweek/2025/1019_2/syutsuba.html
JRA official 2025 Akikasho result: https://jra.jp/datafile/seiseki/g1/shuka/result/shuka2025.html
JRA official 2024 Kikuka Sho result: https://jra.jp/datafile/seiseki/g1/kikka/result/kikka2024.html

## Current blocker
Official 2023–2025 result PDFs have been ingested and partial official horse/jockey ID linkage is available. Exact historical publication times, pre-off field snapshots and timestamped odds remain missing. Research-only fitted models and an exploratory fixed-stake replay are documented in [HISTORICAL_REPLAY.md](HISTORICAL_REPLAY.md); strict production and EV-strategy validation remain pending.

## New ingestion gate (2026-10-18)
`pipeline.py` reads one runner per row CSV using `runners_template.csv` and generates a JSON race-level audit. Example: `python pipeline.py runners.csv --output audit.json`. It rejects after-cutoff odds/features, duplicate IDs, invalid odds, incomplete field, missing source, and inconsistent timestamps. A `field_complete=yes` attestation is required per runner; a source file alone cannot prove completeness. Dead heats, cancellations and disqualifications require explicit custom handling before model training. Do not fill absent odds with final odds. Historical result ingestion and the strict pre-off input gate are separate steps.

Use verified user-exported CSV from available free/official sources; no JRA-VAN subscription is required by this workflow. JRA result PDFs alone do not establish point-in-time odds. Export the full-field table with timezone-qualified ISO8601 timestamps. `finish_position` and payout are labels, not predictors.

## 公式ID・時刻と実データ検証

追加した[ID連携・研究用実測検証](HISTORICAL_REPLAY.md)に、公式ソースの照合方法、再実行コマンド、2025年86レースの検証結果と制約を記録しています。
