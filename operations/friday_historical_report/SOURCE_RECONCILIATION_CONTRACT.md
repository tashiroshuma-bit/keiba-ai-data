# Friday historical report — source and reconciliation contract

## Scope
Friday 21:00 JST: upcoming Saturday/Sunday JRA flat races only. Output every registered runner and declared jockey, including missing-data rows. **Historical observed rates, not V51 forecast probabilities.**

## Required source artifacts (immutable)
1. JRA official race card: race ID, local date, venue, race number, surface, distance, all horse numbers/names, horse IDs where evidenced, jockey names, scratch status, observed_at (JST), URL, original-byte SHA256.
2. Canonical v12 SQLite: `jra_2023_2025_v12_horse_ids_full_20261111.sqlite`; expected SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`, size 362139648 bytes. Verify before querying. **Read-only; never modify canonical DB.**
3. Official historical race results: unique race ID, race date, official horse ID, jockey ID (or explicitly documented name fallback), surface, going, venue, distance, finish, starters, source URL, source capture timestamp and SHA256.
4. Any 2026 results beyond the canonical DB coverage must be a separately versioned, source-backed supplement, not silently assumed present in a file named 2023–2025.

## Reconciliation and integrity gates
- Reject mismatched SQLite checksum or byte size; do not claim an aggregate.
- Read `sqlite_master` and `PRAGMA table_info` before choosing joins. No fabricated schema or columns.
- For each card, compare full horse-number roster and count against JRA original; detect duplicates, late scratches, jockey changes, and absent ID proofs.
- Join by official horse ID and race ID, not fuzzy horse name. For jockey use verified official ID; otherwise flag unverified rather than silently merge namesakes.
- Only include races with official results published **before the Friday cutoff**; no future leakage.
- Normalize `芝/ダート` and `良/稍重/重/不良` as two separate dimensions; distinguish race surface from going. Exclude obstacles from all aggregates.
- Exclude non-starters from denominator. Define win = official finishing position 1; top 3 = official positions 1–3; handle dead heats by official placing. Record disqualifications and missing finishing positions separately.
- Deduplicate one horse per race ID, and one jockey start per race ID × horse ID. A jockey can have multiple starts in a day; count rides, not days.
- Use the exact same eligible historical races for horse, jockey and horse×jockey comparisons; disclose any difference in source coverage.

## Required per-runner output
`meeting_date,venue,race_number,horse_number,horse_name,horse_id,jockey_name,jockey_id,cutoff_jst,source_status,starts,wins,top3,win_rate,top3_rate`.
Separate condition breakdowns for `surface`, `surface × going`, `venue`, `distance`, and `venue × surface × going`, for both horse and jockey; include numerator/denominator for every percentage. Add horse×jockey career joint starts/wins/top3 and most recent five historical runs.

For zero eligible runs show `0走／率—`; for no prior joint rides show `初コンビ／率—`. For missing evidence show `未取得` or `未照合`, never 0% or estimated values.

## Output and audit
- One index by Saturday/Sunday → venue → 1R–12R, with all flat runners, plus detailed CSV/JSON per race and human-readable compact summary.
- A manifest must include the exact JRA source URLs, SHA256, fetched timestamps, canonical DB SHA256, source coverage date, join-key counts, eligible/excluded race counts, missing IDs, duplicate count, scratch/late-change log, and generation code commit SHA.
- **FAIL_CLOSED** on unverifiable original, missing complete card, checksum mismatch or join ambiguity. Still report verified subsets clearly labeled PARTIAL, with affected races/rows listed; never claim complete coverage.
- Friday task must publish a status matrix per race: VERIFIED / PARTIAL / NOT_READY and reasons. If no source data are available, report NOT_READY and never invent statistics.

## Source links
- JRA official results: https://www.jra.go.jp/datafile/seiseki/
- JRA official site: https://www.jra.go.jp/
- Existing policy: `operations/prediction_policy/standard_v51.json` (unchanged; forecasting is separate).
