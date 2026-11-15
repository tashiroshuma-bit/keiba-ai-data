# SQL-only Friday DB: verified access and historical coverage (2026-11-16 JST)

## Outcome
- **New SQLite access/storage: VERIFIED for a partial real JRA-derived research dataset**, using GitHub Actions and SQLite CLI only. Python and the archived Library v12 are not required to open or rebuild this candidate.
- **Full Friday all-JRA-race historical report: NOT_READY**, because the candidate is NOT the complete official historical dataset, complete upcoming Friday-cutoff cards and official jockey IDs are unavailable.
- The data candidate is explicitly stamped `scope=PARTIAL_RETROSPECTIVE_NOT_CANONICAL`. Do not use these statistics to assert full career coverage.

## Exact durable location
- Persistent branch: [`data/friday-sql-candidate`](https://github.com/tashiroshuma-bit/keiba-ai-data/tree/data/friday-sql-candidate)
- Snapshot: `snapshots/friday_sql_candidate.sqlite`
- Byte digest and status in `snapshots/friday_sql_candidate.sqlite.sha256` and `snapshots/friday_sql_candidate.status`
- SHA256 verified on remote independent fresh runner: `e9f2a42ff41bd159f015edd2a97f8e3f97cbdec41bf58f9473460015aebb5bd4`
- The source inputs are three Git-tracked JRA-derived SQLite files; they are permanent versioned data and can replay this partial candidate, while generated GitHub Actions artifacts are temporary.

## Measured results and their evidence
- 2026-11-08 actual results source: 497 records observed, **486 accepted**, **11 excluded** after full race-count mismatch.
- Official-profile-derived historic starts, Tokyo DB: 521 observed, **455 flat starts accepted**, 66 filtered as not explicitly flat turf/dirt.
- Official-profile-derived historic starts, Kyoto DB: 193 observed, **155 flat starts accepted**, 38 filtered as not explicitly flat turf/dirt.
- New research candidate therefore stores **486 results** and **610 profile historical flat starts** (two different collections), plus a provenance registry of 3 databases.
- [Actual-source import and rejection audit in green CI](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43731526692).
- [Independent runner remote download, SHA256, SQLite quick/FK check, real row counts, and fresh rebuild logical `.dump` equality in green CI](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43732596693).
- [Synthetic join and missing-source fail-closed test](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43730699108).
- SQL-only pipeline merged in [PR #57](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/57) commit `20f56733e659ff32c94265bcb20cd4f71472a520`.
- Independent read-back test merged in [PR #58](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/58) commit `b145aba7a80858cb889ca679cdaec4e1e4aca8d2`.

## Operational state
- GitHub Actions workflow: `.github/workflows/friday-sql-db.yml`, cron `0 12 * * 5` = Friday 21:00 JST (runs from default branch `main`).
- The separate ChatGPT Friday 21:00 JST automation has been updated to use the new SQL-only permanent candidate and to report NOT_READY on missing full historical and official upcoming cards.
- The pipeline produces partial horse historical surface/going CSV for the verified-profile subset. Complete horse/jockey/pair metrics for all next weekend JRA flat races are **not verified**, so cannot be reported as operational.
- Existing v51/forecasting, its archived v12 and previous source files were not modified.

## Remaining production gates
1. Obtain and preserve JRA official original result bytes from 2023–2026, with exact source bytes, SHA256, observed time, race IDs, official horse IDs, official jockey IDs, surface/going and starters, under an importable durable provenance ledger.
2. Populate the flat historical race/runner tables with full certified coverage, quarantine gaps, and compute source validation stats.
3. At Friday 21:00 JST, collect the official complete weekend flat entries, verify race/horse counts and jockey updates, and link to historical records using official IDs.
4. Pass real (not synthetic) full horse/jockey/pair condition-specific aggregate checks and a *second distinct run* after official Friday cut-off to test full report + persistent reload.
5. Only then mark the Friday all-races statistics system as production READY.

**No claim of full source coverage or complete Friday automation success is made.**
