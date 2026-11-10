# 2026-11-10 JRA official profiles: 27 new horses, 669 more matched historical runs

## Real canonical-DB join result
- Database version v11 unchanged. SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`.
- JRA official profile names + 10-digit IDs + birth dates added: **27** (six existing + 27 = **33 horses**).
- Profile-name / birth year / canonical race-year-age matches: **778 runner rows total**, including **669 new rows** over the previous 109.
- Counts by year in expanded sidecar: 2023 **126**, 2024 **212**, 2025 **236**, 2026 **204**; sum 778.
- Original missing 66,360; remaining **65,582** if these profile-based candidate links are included.
- Candidate collisions: 0; mismatched ages: 0 among the 33 selected names; duplicate race/horse-number keys: 0.
- New overlay SQLite: `PRAGMA quick_check = ok`, 180,224 bytes, SHA256 `65af7722dfdb012229fb300c8c5fb825dec455daf225743a0392a568e12e1279`.
- Full per-runner candidate audit JSON SHA256 `0e30ef0beda7a344fd39203bd65d74dfa0a716061bd86a99b84d1bf629024012`.
- Files saved to ChatGPT Library `/競馬/recovered_horse_ids_expanded_20261110.json`, `/競馬/horse_id_overlay_expanded_20261110.sqlite`, and `/競馬/expand_profile_ids_20261110.py`.

## Profile/history cross-check examples
- オウケンボルト (`jra:2019103827`) JRA https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102019103827%2F73: 2026-07-12 9th, canonical race `202610020610` 9th.
- ショウナンマグマ (`jra:2019104998`) JRA https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102019104998%2FC3: 2026-07-12 福島七夕賞 14th, canonical `202603020611` 14th.
- ツルマウカタチ (`jra:2021102106`) JRA https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102021102106%2FF2: 2026-10-11 東京鷹巣山特別 10th, canonical `202605040409` 10th.
- モモンウールー (`jra:2021105984`) JRA https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002021105984%2FFA: 2026-10-17 京都トルマリンS 11th, canonical `202608040611` 11th.

## Provenance / boundaries
- Full 778 rows have exact official profile name + birth year matched to original recorded age and race year. **Only the named sample races** were additionally checked against JRA profile history; do NOT claim all 778 separately race-verified.
- Official JRA HTML original raw bytes could not be archived in this environment. Do not silently mark this as primary-source-original evidence.
- No database mutation or promotion of v51. Past result publication times are unnecessary for retrospective identity resolution, but prospective forecast freeze and feature cutoff still require proof before each off-time.
- Source index and birth dates: `operations/data_updates/horse_id_official_profile_candidates_20261110.json`, updated from 6 to 33 horses.

Remaining obstacle: verifying official identities for 65,582 missing candidate rows across more than 15k names, and independent race-wise verification. This one batch demonstrates actual JRA primary-profile collection and canonical DB joining, not full completion.
