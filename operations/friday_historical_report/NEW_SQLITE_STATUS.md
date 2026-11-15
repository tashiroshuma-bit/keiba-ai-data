# Friday new SQLite database — operational status (no Python)
Date: 2026-11-16

## What exists
- `sql/friday_schema.sql`: source-manifest, races, historical starts and target entries, indexes and a verified-history view.
- `sql/friday_report.sql`: horse, jockey and horse×jockey observed starts/wins/top-three with numerator/denominator; excludes historical results dated on or after the target race.
- `tests/sql/friday_fixture.sql` and `tests/sql/test_friday_sql.sh`: **synthetic fixture only**, no JRA observations. Must pass on GitHub Actions before real data use.
- `scripts/friday_sql_bootstrap.sh`: creates schema; rejects an empty DB rather than fabricating a report.
- `.github/workflows/friday-sql-db.yml`: runs SQLite CLI and uploads an **empty schema** database as a 30-day CI artifact.

## Explicit limitations and production blockers
1. **No verified official JRA result rows have been imported into the new database.** An empty schema database is not a historical database.
2. **No actual Friday race-card rows have been imported**. Therefore all-race Friday reports cannot be generated yet.
3. CI workflow results have not yet been observed; SQL fixtures are committed but are not claimed passing.
4. CI artifact retention is **30 days**, not persistent storage. A production-grade storage path must be implemented and tested before claiming reliable operation.
5. Old v12 remains untouched; new DB is a candidate only, not yet the authoritative production source.
6. Source manifest must reference real immutable source capture, with SHA256 and official provenance. Test fixtures are excluded from production.
7. Current SQL produces all-condition career totals only. Surface/going/venue/distance condition breakdowns and recent five runs are not yet implemented.
8. No Python is required by the new SQL bootstrap, SQL report, fixture tests or workflow.

## Acceptance criteria
Real official source captured and hashed -> rows imported with verified IDs -> constraints and source reconciliation pass -> production queries verified -> complete next-weekend race cards present -> report produced -> durable DB persisted and reloaded in a later independent run. All conditions are mandatory.

## Manual SQLite CLI commands
```bash
sqlite3 data/friday/history.sqlite < sql/friday_schema.sql
bash tests/sql/test_friday_sql.sh
bash scripts/friday_sql_bootstrap.sh data/friday/history.sqlite
```
The last command deliberately exits 2 (NOT_READY) if verified data and target cards are missing.
