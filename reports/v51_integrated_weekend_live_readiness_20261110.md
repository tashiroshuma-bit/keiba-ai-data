# 2026-11-10 v51 integrated weekend real-data pilot readiness

## Decisions
- **Production**: v50, unchanged. **Research**: v51, not promoted.
- PR [#10](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/10) merged as `94646b072c1f8f04af24388cd5dd46b8f5a8c63d`, [CI run 42718359775](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42718359775) all jobs success.
- PR [#11](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/11) merged as `31055593425ab0b3c345a889df418a960bd10620`, [CI run 42718934934](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42718934934) all jobs success.
- Morning vs final source requirements separated. Missing unannounced weights do **not** block v50 morning preoff generation, but full-field raw evidence and matching SHA are compulsory for final v51 weight capture.
- All integrations in CI use synthetic snapshots to demonstrate software mechanics; no actual 2026-11-14/15 JRA race has happened yet and no genuine preoff metrics are available.

## Actual canonical DB verified this turn, locally
Source: Library materialized copy, path `/mnt/data/keiba/jra_2023_2025.sqlite`.
- SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`, exact 322,170,880 bytes, matches PROJECT_STATE v11.
- `PRAGMA quick_check` result `ok`.
- `annual_report_races` has 11,201 validated races, `annual_report_runners` contains 154,191 runners for those validated races.
- Validated-runner cohort missing official `horse_id`: **66,360**; missing `jockey_id`: **5,446**. This cohort is NOT the all-raw-rows count (PROJECT_STATE lists 77,317 total unlinked horse rows for its own broader scope).
- Validated-runner `payload_json` has 0 non-null `result_available_at`, 0 non-null `odds_timestamp`, 0 non-null `pre_off_odds`. Although all rows have a `body_weight_raw` key, that does not prove these weights were published before the historical race. Historical provenance requires separate proof. Never retrospectively assert that unknown timestamp is valid.

## Integrated execution
### Before first weekend race, e.g. 08:00
Inputs: genuine all-runner original source-A JSON with `source_model=A`, `asof`, each `race` with `original_off_at`, `surface`, all horses with `number,name,jockey_id,p1`; true canonical SQLite.
```bash
python -m scripts.v51_weekend_preflight --repo . --phase morning --database /data/canonical_v11.sqlite --source-a /data/real_A_preoff.json --strict
python -m scripts.v51_weekend_integrated_runner --forecast-source /data/real_A_preoff.json --database /data/canonical_v11.sqlite --output-dir /data/frozen/2026-11-14/
```
Results: standard v50 full field, immutable SHA receipt, v51 PL podium-only research baseline, feature / learned rank missingness. **PL is NOT learned conditional p2/p3**.

### When same-asof announced bodyweight is actually available
```bash
python -m scripts.v51_weekend_preflight --repo . --phase final --database /data/canonical_v11.sqlite --source-a /data/real_A_asof.json --weight-manifest /data/real_weights_asof.json --weight-archive /data/raw_weight_sources --strict
python -m scripts.v51_weekend_integrated_runner --forecast-source /data/real_A_asof.json --database /data/canonical_v11.sqlite --weights /data/real_weights_asof.json --weight-source-archive /data/raw_weight_sources --research-input /data/proven_feature_input.json --rank-snapshots /data/frozen_preoff_rank.json --output-dir /data/frozen/2026-11-14/
```
The last two research args are **optional**, only supply when complete time-evidenced official race/horse ID/features and separately learned ranked shadow are available; exclude rather than impute. All source hashes must be verified against original archived bytes `<sha256>.bin`. Runner refuses after actual off, asof newer than runtime, or stale source > 1 hour.
A new full source-A snapshot is required for a new asof: **do not reuse the 08:00 probability output while claiming final asof**.

### After all runners have official results
```bash
python -m scripts.v51_weekend_postrace_runner --archive /data/frozen/v50_weight_pair_<actual_sha>.json --official-results /data/official_results.json --official-original-bytes /data/official_result_source.bin --output /data/evaluation/official_pair_audit.json
```
Optional `--rank-snapshots /data/frozen_preoff_rank.json` only with fully authenticated genuine preoff learned conditional rank forecasts. Outputs same-race top1, winner top3, exact unordered/ordered podium, LogLoss, Brier and post-race reliability / entropy buckets. Never use outcome to refit on this evaluation cohort.

## 8-item status
| Requested improvement | Actual implemented route | Not yet proven |
|---|---|---|
| Horse IDs and past-race joins | `v51_identity_sidecar.py`, `v51_preoff_feature_builder.py`; official same race/number/name + bytes required | 66,360 historical validated rows remain without ID, no real new links verified |
| Conditional 2nd/3rd | Existing learned `keiba_v48/rank_forecast.py` + `v51_conditional_rank_pair_evaluation.py`; PL nonlearned baseline | Genuine same-asof learned rank shadow missing |
| Horse last 3 form, class | `v51_preoff_feature_builder.py` | Independent historical publication timestamps lacking |
| Jockey course/distance/surface | Same builder, shrinkage | Actual runner ID evidence needed |
| Relative field opponents | Same builder | Historical provenance required |
| Same-day track/pace/inside outside | Same builder, JST local-day fix | Earlier race result availability must be proven at asof |
| Layoff, age, bodyweight changes | Same builder, source archived weight manifest | Real announced weight still to be obtained |
| Calibration/overconfidence | `v51_calibration_audit.py` + weekend postrace runner | Genuine future frozen pairs and official results needed |

## Non-negotiable remaining blockers
1. A live, source-attributed generator for **source-model-A** full-field probabilities and matching race IDs has not been independently verified end-to-end. Repo's CI and hourly automation alone do not prove this exists.
2. A Github Actions runner does NOT automatically carry the 322 MB canonical Library DB, even though this conversation's local environment passed SHA and quick_check. Friday 11/13 preflight must independently materialize it.
3. The existing hourly preoff automation cannot guarantee 15–20 minute-before-off snapshots for every race; label misses as failed and preserve only verified pred.
4. No historical record can be upgraded to genuine preoff simply because its result PDF or bodyweight exists. Publication and acquisition timestamps are absent for the database cohort.

These risks are explicit instead of hidden. Weekend automations now invoke the integrated runner and preserve v50 as standard.


## Preflight schema hardening, same day
- PR [#12](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/12), merge SHA `f2f53d90e4e20f7a0cb676ed0c85863cc7e98d99`; [GitHub Actions run 42719612990](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42719612990), both jobs successful.
- `v51_weekend_preflight.py` now verifies source-model-A schema including full roster, unique numbers, finite normalized p1 sum, race surface and timezone-aware preoff timing. An empty JSON can no longer pass the morning readiness check just because the file exists.
- The source's *true external observation time* is still not independently proven by the mere presence of these fields. The live acquisition process must supply and independently archive it.
