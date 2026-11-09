# 2026-11-10 official-profile-backed horse ID recovery — interim real-data result

## Scope and disposition
User requested ID completion; exact historical publication timestamp is **not** a prerequisite to recover a stable horse identity. The genuine prospective weekend forecasts still need actual preoff capture timestamps to prove predictions were frozen before each race.

Canonical v11 Library SQLite **not modified**:
- size 322,170,880 bytes
- SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`
- SQLite quick_check = ok.

Read-only validated-runner scope: 154,191 rows, with 66,360 lacking horse_id. 2026 validated rows without horse_id: 22,630. Scope differs from all-row `PROJECT_STATE.unresolved` 77,317.

## Genuine ID matching from published official JRA horse profiles

All six profile pages show the exact horse name and birth date. The JRA profile URL encodes the horse registration identifier. Every candidate canonical runner was matched on exact name **and** birth year versus archived race date / recorded Japanese age, with no fuzzy name correction. Race-specific full official roster cross-check **has not yet been done**, so preserve the source rank `PROFILE_NAME_BIRTHYEAR_AGE_CORROBORATED` and do not silently count as independently race-verified primary source.

| Horse | JRA horse ID | Matched result rows | Source |
|---|---|---:|---|
| フレンドモナコ | jra:2023106197 | 20 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102023106197%2FC9 |
| ブルーストレイル | jra:2021106078 | 18 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102021106078%2FD3 |
| ナンナンプー | jra:2022102878 | 23 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102022102878%2F2B |
| ゴーゴーパンチ | jra:2023103931 | 11 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002023103931%2F8B |
| ゴーゴータカシ | jra:2022102135 | 24 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102022102135%2F3B |
| ブリックアブラック | jra:2023102410 | 13 | https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102023102410%2FFB |

**109 historical runner-to-ID candidate links**, 6 distinct horses, distributed 2024: 11 rows; 2025: 28; 2026: 70. Original official HTML bytes were NOT captured; record that honestly.

**Existing known-ID exact-name matching outside these six found 16 more candidate rows, but they belong to race IDs `202301020407` and `202301020408` with `status=requires_review`, no established race date. Therefore they were **not** inserted into the validated-runner recovery overlay.**

## Saved artifacts (ChatGPT Library)
- `/競馬/recovered_horse_ids_20261110.json`, 109 rows, SHA256 `1658ed75e09d4efcd06024f5384257d06b2c21c9bc2a090b`
- `/競馬/horse_id_overlay_20261110.sqlite`, 109 rows, 6 horses, 36,864 bytes, SHA256 `5084da4a83ec5749283c994ce36b98f6e68560d0b36fa360fc2e1fa62be0e69a`; SQLite quick_check=ok.
- `/競馬/recover_ids_20261110.py`, reproducible source.

The `horse_identity_overlay` table is keyed by (race_id,horse_number); retain source URL, evidence_level, no raw-original archived indicator. Do not overwrite canonical v11 or increase formal official-verified ID count before independent race-specific confirmation.

## Next expansion
Only 109 candidate rows is **not** full historical ID completion. 2026 alone has 7,260 distinct missing-name entries. Need official JRA race results (race ID + horse number + horse ID), or a repeatable horse profile race-history match, with invalid/multi-match exclusions and error ledger, then write verified matches to an updated sidecar. Backfill exact names and birth years alone is insufficient for unrestricted authoritative joining when duplicated historical names exist. No 2026 result labels can be used to train a model to forecast a preceding 2026 race.

## Statistical / temporal distinction
- ID reconciliation is retrospective historical entity resolution; no old PDF publication timestamp needed.
- Retrospective research training features must exclude the predicted race and all later races; unavailable preoff feature timestamps remain an assumption, not a basis for declaring a true forward test.
- Prospective Nov 14/15 v50 vs v51 requires SHA-archived preoff actual prediction and source as-of before off. Preserve baseline v50 official status and v51 research-only.
