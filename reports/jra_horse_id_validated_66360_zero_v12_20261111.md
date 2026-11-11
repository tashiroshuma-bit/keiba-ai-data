# JRA historical horse-ID recovery completed — verified cohort 2026-11-11

## Verified result: 66,360 of 66,360 originally NULL horse IDs recovered

- Original primary canonical DB v11: 322,170,880 bytes, SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`, unchanged.
- New canonical DB **v12**: ChatGPT Library `/競馬/jra_2023_2025_v12_horse_ids_full_20261111.sqlite`, Library file ID `libfile_fc0322f2d7888191b87ca5e9f7b00629` (file ref `file_00000000ed80820689e5b758ab44a9d7`).
- New DB exact size: **362,139,648 bytes**; SHA256 **`5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`**.
- Independent Library upload -> materialization -> SHA256 comparison returned an exact match. Reopened materialized SQLite; `PRAGMA quick_check = ok`, `PRAGMA foreign_key_check` 0 rows.
- The scoped cohort is **11,201 `annual_report_races.status='validated_result'` races and 154,191 `annual_report_runners` rows**. Former NULL IDs = 66,360. New NULL IDs = **0**. Every original existing ID preserved without conflict.
- Updated `annual_identity_links.horse_id` for 66,360 rows and JSON payload `annual_report_runners.payload_json.$.horse_id` for 66,360 rows; final discrepancy between these stores = **0**.
- For each recovered row, the new table `horse_identity_backfill_20261111` records the key, exact 10-digit official `jra:` ID, original official result URL, original HTML SHA256, archive filename, verification method and JRA official horse profile link.
- Evidence breakdown: 66,346 exact race-ID + horse number + normalized horse name comparisons; 13 JRA annual PDF `(cid:number)` extraction-prefix repairs against the official result; 1 overseas horse full-name vs result-screen abbreviation, independently checked against the same JRA race (2026-09-06 Hanshin 11R #8 Fast Network, 15th, 506kg).
- Source parser independently reparsed JRA original race HTML and SHA-verified every source byte rather than blindly copying previous identity candidates. **9,883 distinct original HTML SHA256 digests** referenced in new backfill rows. No existing-ID collision.
- Source ZIP originals: 47 distinct JRA workflow source archives bundled and uploaded to Library `/競馬/jra_original_official_html_evidence_all_47_archives_20261111.zip`; 187,741,532 bytes; SHA256 `65fbe2ac1093bac6aea2ecfbd796d856467327751884762e66963f7344e607e6`; independently downloaded, rehashed, ZIP `testzip` passed. Original catalog JSON in Library `/競馬/original_jra_source_archive_catalog_20261111.json`.
- Full row-level totals and checks: Library `/競馬/horse_id_full_recovery_audit_20261111.json`.

## Out-of-scope, explicitly not counted as zero

The DB still has **1,975 races marked `requires_review` with 10,957 NULL horse ID rows** (2023: 2,248; 2024: 2,345; 2025: 2,973; 2026: 3,391). Their race integrity has not been confirmed by the validated-result gate, so they are **not** silently classified as complete and cannot be mixed into the 154,191 validated-runner denominator. Rejected/unfinished rows are in Library `/競馬/requires_review_horse_ids_remaining_10957.csv`.

## Upstream primary evidence / workflow verification
- 2023–2025 24-shard official race HTML capture: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42780017487
- 2026 source 8-shard capture: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42780335360
- Last 28 dates, source original with 14 shards: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42944374933
- JRA official race result domain: https://www.jra.go.jp/JRADB/
- All actual source originals have URL/SHA in the new audited DB. Source capture and original race-result publication are retrospective identity proof, **not** evidence that features existed pre-off for historical forecasts. Forward testing must still use genuine pre-off snapshots.

## Production deployment policy
- **Model version remains v50**; v51 still research-only. No performance improvement is claimed solely from recovered IDs.
- Standard forecast code must accept canonical DB version 12 without disabling SHA or any source-A real-data checks.
- The Library v11 original remains preserved and immutable for reproducibility. This v12 database is an independently verified **new file**, not an in-place mutation of the v11 original.
