# JRA primary-source 10-digit horse ID retrieval and reconciliation — 2026-11-10

## Actual result, fully source-backed
Canonical source is Library `jra_2023_2025.sqlite`, SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`, 322170880 bytes, immutable. Its validated_result cohort contains **66,360 NULL horse ID rows**, and has not been rewritten.

Downloaded exact JRA official race HTML with the linked profile registration ID per `horse_number`, exact name, race ID, original source SHA256 and UTC observation timestamps. Stored original raw HTML bytes in GitHub Actions archived artifacts, separately downloaded for local audit. Source comparison independently reparses exact raw original HTML. Only `annual_report_races.status='validated_result'` rows count toward the historical 66,360.

**Initial validated source batches**:
| Genuine source cohort | Official direct-ID rows |
|---|---:|
| 2023 original 72 official race HTML pages (July 22/23 Sapporo and other locations) | 239 |
| 2024 June 8/9 original official results | 376 |
| 2025 Dec 20/21 original official results | 536 |
| 2023 Jan 5/9 seed week | 0 (outside target validated cohort) |
| 2026 Nov 8 seed week | 0 (beyond canonical full-history cutoff) |
| Total direct row verified | **1,151** |

Comparison with previous 60 official-profile-derived candidates: 1,336 prior weak candidates, 26 overlap/upgrade to stronger independent per-race evidence; new unique verified 1,125; source-graded combined sidecar contains **2,461** candidates, of which 1,151 are direct and 1,310 remain profile-only. Remaining **63,899** effective null-ID rows if sidecar candidates are applied; **65,209** effective remaining if one accepts only direct official race-row evidence. **Original canonical DB still has 66,360 actual nulls**.

Combined immutable research sidecar:
- Library `/競馬/horse_id_overlay_jra_primary_batch_20261110.sqlite`
- SHA256 `9421192bdf94e16aa2120d1ede9ed3cf6da91ed27b845f2b5f3ad1a441544533`
- `PRAGMA quick_check = ok`
- `horse_identity_overlay`: 2461 rows and `official_direct_evidence`: 1151 rows.
- primary raw bytes available in Library under `/競馬/jra-id-2024-w23-20261110.zip`, `/競馬/jra-id-2025-w51-20261110.zip`, 2023 official seed ZIP also downloaded; GitHub Actions artifacts retained for 7 days.
- importer `scripts/jra_official_race_id_import.py`: strict SHA, raw HTML reparsing, URL/race ID validation, horse number, normalized exact name, canonical status, no conflicts; copy of executable in Library.
- consolidator `scripts/jra_horse_identity_consolidate.py`: immutable graded research overlay, JRA source outranks weaker profile-derived estimates.

### Why not zero yet?
- 66,360 covers nearly 11,201 validated races, requiring multiple years of actual race-by-race HTML acquisition (11k+ pages), rate-limited and source-preserved. It cannot be correctly replaced with guessed IDs; a JRA registration name-list PDF numbering format is not the same as 10-digit horse ID.
- Need year-week seeds; `operations/data_updates/jra_official_seed_weeks_2023_2025.json` enumerates **148 source-attested week seeds** spanning **43,730** of the original missing rows, but still requires bounded crawling and actual exact-name verification. Supplement 2026 dates.
- Official result URLs have **two** known CNAME route variants `pw01sde10...` and `pw01sde01...` for recent 2026 races; parser now accounts for both. June 2024 had one transient SSL timeout race; retry it individually.
- Profiles not proven by raw JRA race HTML stay marked research-candidate; no false "official verified" promotion.

## Evidence
- GitHub Actions direct official HTML proof: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42751286332
- Original 12 race test: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42752505623
- 72 race result primary HTML cohort: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42752838341
- 4-week parallel source samples: https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42753573761
- 2026-10-18 Kyoto real official race source: https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde0108202604070120261018%2F9A

No JRA-VAN subscription; no paid sources. All result source timestamps are **postrace** and used only to reconstruct historical identity, not as proof of past prediction at off-time. Standard forecasting model v50 unchanged, v51 remains research.

## Updated final-source cohort (2026 October 17/18 official result pages)
The earlier table above reports the first three strictly verified week cohorts, NOT the final cumulative count. A separately archived **2026-10-17/18 official source batch** adds 72 original source HTML pages, 922 full-field runners and **610** exact ID results matching `validated_result` canonical missing rows; 8 further downloaded race IDs are outside the validated canonical cohort and must be excluded. Original source was downloaded with GitHub Actions [run 42754603332](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42754603332) and raw SHA256 bytes stored in Library `/競馬/jra_official_raw_2026oct_20261110.zip`.

**Final exact cumulative actuals as of this report**:
- Direct per-race original-JRA-HTML matched existing-null-ID rows: **1,761** (2023 Jul 239 + 2024 Jun 376 + 2025 Dec 536 + 2026 Oct 610).
- Overlap with 1,336 earlier profile-only horse identity candidates: **33** candidates were upgraded with direct evidence.
- Remaining weaker name/birth-year/age-only candidates: **1,303**.
- New direct IDs outside the original profile-only candidate set: **1,728**.
- Total unique sidecar covered validated runner rows: **3,064**.
- Remaining validated original NULL-ID rows if *both* source strata treated as usable: **63,296**. Remaining if only independent direct original-JRA-HTML rows accepted: **64,599**.
- Original canonical SQLite actual NULL horse IDs: **66,360**; it has never been mutated.
- Final merged and verified Library sidecar: `/競馬/horse_id_overlay_jra_primary_2026oct_batch_20261110.sqlite` with SHA256 `3c9005f323392e57d6db9d092ede045bbde5682b1fa221ed6ae1c7445c74de34`, `PRAGMA quick_check=ok`.
- JSON audit `/競馬/horse_id_overlay_jra_primary_2026oct_batch_20261110.audit.json`.

**Important**: all these verified IDs are retrospective historical identity reconstruction, not a completed future-race model backtest. Full-coverage ID recovery remains blocked by ~63k unmatched rows and slow, bounded upstream official source retrieval. Do not label source-graded sidecar as a modified official canonical DB or claim zero remaining.
