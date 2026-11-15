# Friday JRA historical-report acceptance contract — SQL-only new DB

## Ownership and legacy
- New operational data source: **Git-tracked official provenance ledger** plus replayable SQLite SQL. The old Library v12 SQLite (`jra_2023_2025_v12_horse_ids_full_20261111.sqlite`, SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`) is an **untouched archival comparison**, not a prerequisite for SQL CLI startup or a source automatically substituted into the new DB.
- New SQL-only source and data paths are in `scripts/friday_*.sh`, `sql/friday_*.sql`, `data/friday/ledger`; no Python runtime.
- Git-tracked 2026-11-08 JRA-derived DBs are **research subset only**. CI verified source-file hashes and reconstructed 486 observed result runners + 610 retrospective flat profile past runs. The original official page bytes were not independently reverified by this run. Jockey official identity coverage is not sufficient.

## Production evidence contract
Every imported original must have:
1. JRA official result or declared race-card document URL, original response bytes, SHA256, observed_at in JST, and no unverified rewrites; source-manifest verification is not accepted without original-byte hash comparison.
2. Result races with unambiguous official race ID, date, venue, race number, surface, going, distance, and complete roster. Exclude jumps.
3. Each runner must have official horse ID and horse number, result status and official placing. For jockey/group and pair totals, verified official jockey ID is mandatory. Do not manufacture an ID from a jockey name.
4. For Friday 21:00 JST output, complete official Saturday/Sunday flat cards, all registered numbers/names/jockeys, documented scratches, as-of time and independent expected roster counts.

## Integrity, denominator and time gates
- `PRAGMA quick_check`, `PRAGMA foreign_key_check`, original-byte SHA256 match, uniqueness and card counts must pass.
- Only results existing before the cutoff can appear in historical totals; never use target-race outcome or later source publication.
- Wins = placed first; top-three = placed 1–3; denominators = officially started horses, distinguishing disqualifications, nonstarters, missing finishers and no evidence. Until result-status handling is verified, incomplete status rows are quarantined, not silently counted.
- Horse, jockey, and horse×jockey rates use the same certified race population and documented cutoffs; missing official jockey identity is **UNVERIFIED**, not 0%.
- Group by surface (芝/ダート), going (良/稍重/重/不良), venue, distance and combinations; expose numerator/denominator and last five known starts. Incomplete source coverage must be visibly marked PARTIAL or NOT_READY; 0 races in a partial database is not proven 0 career starts.
- Verify source batch SHA256, row count, exact duplicates, source/checkpoint mismatches and race-level expected headcount. Preserve rejection CSV and source history.

## Required run output
- One clear status per Sat/Sun → venue → race and each declared horse.
- Exact historical start/win/top3 counts and percentages for horse, jockey, pair and conditions where verified; display missing and first-time pair distinctly.
- Manifest with source-file checksums, code commit, cutoff JST, venue/date coverage, accepted/rejected counts and reason codes.
- Durable source ledger in Git is the authoritative replay input; generated DB can be rebuilt independently in a fresh GitHub Actions job; temporary Actions artifacts are not permanent source storage.
- Scheduled GitHub Action `cron: 0 12 * * 5` (Friday 21:00 JST) is eligible only on main; Friday output stays NOT_READY until **all** the gates above pass.

## Separate duties
New DB historical metrics are **observed statistics**, not V51/V52 predicted probabilities, and do not alter the forecasting model or its canonical v12 archive.

Primary official historical results reference: https://www.jra.go.jp/datafile/seiseki/
