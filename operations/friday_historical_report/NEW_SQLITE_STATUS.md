# Friday new SQLite history workflow — measured status (2026-11-16)

## Verified with GitHub Actions; Python not required
- [SQL CLI test, verified runner](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43730699108): horse/jockey/pair joins on **synthetic test fixture**, two independent ledger DB rebuilds, and fail-closed empty/missing-source tests passed.
- [Real source seeded twice](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43731526692): three already Git-tracked JRA-derived SQLite databases passed SHA256 and SQLite quick checks; generated candidate SQLite files had identical SQL dumps across independent rebuilds; CSV statistics and audits were uploaded as CI artifacts.
- [Friday runner smoke](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43731805380): SQL-only runner rebuilt the real subset, reported **NOT_READY** for the unprovided official next-weekend roster, and did not fabricate a complete Friday report.

## Real dataset (verified Git-tracked source DB files, NOT original JRA page bytes)
| Source | Source SHA256 | Records | Accepted | Excluded reason |
| --- | --- | ---: | ---: | --- |
| 2026-11-08 results | `4912237e688804cdbaed6a4d0b9a2019fd126b309c938fb21d8c1a637397959b` | 497 | 486 | 11 race headcount discrepancy |
| Tokyo official-profile past runs | `e17d37e5ee0bb0d26d054eb3395278937cf3f3fb58481eb3fea8761f64b86025` | 521 | 455 | 66 non-explicit flat turf/dirt |
| Kyoto official-profile past runs | `1558a0ac7dbaebf8edd751f586ea7c5cab19e23c814374028cdf34487754a39f` | 193 | 155 | 38 non-explicit flat turf/dirt |

Current segregated candidate has **486 bounded result runners and 610 flat profile past runs**. These are different populations and **must not be summed into 1,096 uniquely identified race starts**. Horse-only retrospective condition rates are calculated on profile records with known official horse IDs. Jockey names exist but **jockey official ID is not established**; full jockey/pair lifetime stats are not verified. These data were sourced from existing previously generated JRA-derived databases, not independently re-fetched original JRA HTML in this run.

## Durable access strategy
- Permanent Git-tracked inputs are the three already committed source SQLite DBs (binary checksums verified) plus any future source ledger committed under `data/friday/ledger`.
- `scripts/friday_seed_tracked_jra.sh` atomically rebuilds the segregated real-source subset in GitHub Actions. GitHub artifact download is only a convenient 30-day output, not persistent canonical input.
- `scripts/friday_sql_rebuild_from_ledger.sh` rebuilds a separate future production DB from versioned four-CSV ledger, **only if** original bytes with matching SHA256 exist.
- `scripts/friday_operational_run.sh` creates a partial report and explicitly returns exit 2 until a complete verified roster and source ledger are available.
- `.github/workflows/friday-sql-db.yml` defines Friday 21:00 JST cron `0 12 * * 5` (GitHub Actions only schedules from the default branch; feature-branch PR is not the schedule).

## Still NOT COMPLETE
1. The 2023–2026 all-JRA-flat result history is **not** in the new official ledger. The archived canonical v12 in Library has not been migrated and remains untouched.
2. Upcoming Fri-cutoff official Saturday/Sunday racecards are not imported, and complete all-runner roster reconciliation is absent.
3. Full official jockey-ID joins and horse×jockey rate calculations on real coverage are absent.
4. Independently downloaded current raw JRA HTML/PDF bytes have not been reconciled against this real subset in the present run.
5. The validated full production ledger's cross-week persisted reload, complete coverage and Saturday/Sunday Friday report have **not** passed.

No Python executed by the new SQLite CLI routines. No V51/forecasting production state changed.
