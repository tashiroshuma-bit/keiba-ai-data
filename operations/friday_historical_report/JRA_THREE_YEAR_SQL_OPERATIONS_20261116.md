# JRA 2023–2025: SQL-only complete scheduled-result history (2026-11-16 JST)

## Operational result
Historical SQLite access, SQL aggregation, independent Git persistence/re-download and production Friday scheduler's source checks were **verified in GitHub Actions, with no Python**.

Historical data (2023–2025) is reconciled to **all 10,368 scheduled race slots**: 10,365 JRA official result pages and 3 officially cancelled races with no starts. The full original 2023–2025 JRA race-result runner-record cohort **142,737 rows** is reproduced from independently SHA-verified official result HTML. Some runner records are scratches/exclusions and are **not** actual starts; the `started` column distinguishes them.

| year | Official race result pages | Officially cancelled | Reconciled scheduled | Result-page horse records |
|:---|---:|---:|---:|---:|
| 2023 | 3,456 | 0 | 3,456 | 47,672 |
| 2024 | 3,454 | 2 | 3,456 | 47,181 |
| 2025 | 3,455 | 1 | 3,456 | 47,884 |
| TOTAL | 10,365 | 3 | 10,368 | 142,737 |

- Three separately verified JRA-cancelled scheduled races (not silently reported as missing): `202404030612` Niigata 12R (lightning risk), `202408060108` Kyoto 8R (heavy rain), `202505021109` Tokyo 9R (lightning risk). Evidence URLs and evidence verification status appear in `sql/friday_official_cancelled_2024_2025.sql`; these JRA official notice/summary URLs were located independently, **not original-byte SHA verified**.
- Current expanded archive also includes a **partial** 2026 history. 2023–2026 combined: 13,095 official result pages / 180,418 horse-result records.
- The prior v12 annual audit's `surface_explicit_turf_dirt` differs from parsing the real official result headers for **27 races across 2023–2025** (8+10+9). This is a **surface-classification audit discrepancy**, NOT 27 missing race results; official result+cancelled panels cover 100%. Do not conflate those counts.

## Real historical aggregate validation
- Original SHA, official horse number/name/ID, unique race and runner keys, SQLite `quick_check`, FK checks and official result/scheduled panel counts were verified.
- Official jockey profile IDs were obtained from actual JRA race-result HTML links, not guessed from names. A missing profile ID remains missing from **strict verified-ID jockey/pair aggregates**; no 0% substitution.
- Historical SQL count includes horse starts with numerical placings, **中止** (started but did not finish), **失格**; skips **取消** and **除外**. Unknown start statuses are rejected by the production persistence acceptance gate.
- Production 2023–2025 query output: **1,027,789 individual horse/jockey/pair×condition observed rows**, plus **80,795 last-five-start rows**. Includes surface/going, venue and distance splits with explicit wins/top-three/starts denominators. No Python.
- [2023–2025 full source replay/cancellation acceptance and 1,264,581 combined-period condition output](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43776666478).
- [Independent remote Git snapshot replay and full 2023–2025 actor/condition export](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43777011527).

## Durable snapshot
- [Permanent database branch](https://github.com/tashiroshuma-bit/keiba-ai-data/tree/data/friday-three-year-history).
- `snapshots/archived_official_history.sqlite`; `snapshots/archived_official_history.sqlite.sha256`; `snapshots/archived_official_history.status`.
- Verified snapshot SHA256: `8a08a5ebae28e0890a0586d6d0217b6cd5e7aab88624f9e8c6c1941dc1ea33bb`.
- Independent compressed **SQL backup** is permanently stored as `snapshots/archived_official_history.dump.sql.gz`, with SHA256 `0abdbd0d23a853ea89748dd844564a3a1107fe4166627ce17c0b6ea18805fb19`. A fresh GitHub Actions runner fetched this backup, rebuilt the whole SQLite using SQLite CLI (no Python), and re-verified every 2023–2025 scheduled race and row count: [independent restoration run 43777699446](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43777699446), merged by [PR #60](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/60). Original raw HTML artifacts in Actions still have retention deadlines; the durable normalized data and replay SQL remain independently accessible, not falsely asserted to be original HTML bytes.

## Friday 21:00 JST execution
- `.github/workflows/friday-sql-db.yml` is scheduled with `0 12 * * 5`. Runs on GitHub main, uses `scripts/friday_full_history_runtime.sh` to fetch the permanent DB independently and check source, years and cancellation panels.
- Always writes the verified historical three-year horse/jockey/pair conditional statistics and last-five CSV, even if Saturday/Sunday official entries are not available.
- **Upcoming weekend all-runner matching is NOT READY** until a complete Friday-cutoff official racecard capture, URL/original-byte hash, scratches and roster headcount and horse/jockey ID reconciliation have actually run. The GitHub job must show this status and should not pretend unverified future cards were collected.
- ChatGPT's Friday 21:00 JST automation also references this source and the same fail-closed rules.
- Forecasting standard v51 and archived Library v12 remain unchanged; this is a separate observed-historical-results database.

## Next-weekend all-runner readiness criteria
1. Capture actual JRA Saturday/Sunday official entries with verifiable source bytes before Friday 21:00, including number/name/horse ID/jockey ID.
2. Compare complete official races and rosters and apply scratch/jockey changes to each race; preserve capture time and hash.
3. Execute per-runner as-of-date joins with the above verified historical source and reject future leakage.
4. Verify a fresh independent Friday full-result run and persist comprehensive evidence/status, not only a synthetic fixture.

Historic 2023–2025 scheduled results are complete; **the future weekend roster integration is explicitly not**.
