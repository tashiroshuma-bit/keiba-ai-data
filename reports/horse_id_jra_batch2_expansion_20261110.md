# Horse ID recovery: JRA official profile expansion, 2026-11-10 batch 2

## Results directly checked on the real v11 canonical DB
- Canonical DB: `/mnt/data/keiba/jra_2023_2025.sqlite`, 322170880 bytes; expected SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`. No canonical write.
- Existing missing horse ID validated runner cohort: **66,360 rows**.
- Previous official profile candidate sidecar: 778 historical rows, 33 horses.
- **27** additional official JRA profile horse IDs: exact name, numeric 10-digit ID encoded in each official profile URL, and birth year.
- Matched against real canonical `annual_report_runners`, with `annual_report_races.status='validated_result'`, exact name, age from `payload_json.sex_age` and race-date year − horse birth year:
  - **558** newly recovered historical runner-row **candidates** from 27 horses.
  - New total **1336** candidate rows from **60 horses**.
  - 2023 +99, 2024 +155, 2025 +176, 2026 +128 added.
  - Remaining original null-ID rows excluding this research candidate sidecar: **65,024**, not yet actually assigned inside canonical DB.
  - 0 mismatched birth-year/age evidence; 0 duplicate composite (race_id, horse_number); previous 778 triple keys unchanged.
- Created read-only overlay output `horse_id_overlay_batch2_20261110.sqlite`: 294912 bytes, SHA256 `d481127836f4a5dec3a309c2e3e3774be2746e352d11dd2d60cf842e9be83c26`, SQLite `PRAGMA quick_check` returned `ok`.
- Detailed sidecar `recovered_horse_ids_batch2_20261110.json`: SHA256 `354fc3aef2e39ac66b7a68d29f5eee6baa2bb829f4923cac095b99ac7b5993b7`.
- Both files plus generator `expand_official_profiles_batch2_20261110.py` were uploaded to ChatGPT Library `/競馬/`, with successful upload results.

## Provenance
- 27 records' JRA profile URL + horse-ID + search source ref are saved in `operations/data_updates/horse_id_official_profile_candidates_20261110.json` with previous 33 IDs (60 total).
- Representative new primary sources:
  - トウカイポワール https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002021102389%2F46
  - ペルフェツィオーネ https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002021106690%2F9A
  - ハピ https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002019100630%2F95
  - キャントウェイト https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102021102800%2F97
  - スマートサニー https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102020104304%2FC0
- This is profile-name+birthday-year+historical-age-based **candidate matching**, NOT a claim of direct independent racewise confirmation of all 1336 events. Original JRA HTML bytes weren't archived and cannot be claimed to have been. The profile in some pages may have shifted through time (registered/transferred), and each historical race's original official entry roster still needs confirmation. This keeps the immutable canonical database unchanged and production v50 unchanged.
- Historical result original publication time is NOT needed for retrospective identity reconciliation. Future race forecast snapshots must still be frozen with source timestamp prior to actual off.

## Next action
Batch highest-count still-unlinked horses; retain exact profile URL and all provenance; quarantine any ambiguous names, duplicate horse registration numbers, races lacking exact name or birth-age; create new overlay rather than overwrite validated canonical DB. Need external full official horse-roster ID dataset to reach 65,024 unresolved rows efficiently.
