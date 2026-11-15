#!/usr/bin/env bash
# Independent fresh-runner SQL-only restore from public Git data branch.
# Verifies *full* official 2023–2025 scheduled panels and actual start semantics.
set -euo pipefail
branch="data/friday-three-year-history"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git fetch --no-tags origin "refs/heads/$branch"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/remote.sqlite"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite.sha256 > "$tmp/remote.sha256"
git show FETCH_HEAD:snapshots/archived_official_history.status > "$tmp/remote.status"
git show FETCH_HEAD:snapshots/archived_official_history.dump.sql.gz > "$tmp/remote.dump.sql.gz"
git show FETCH_HEAD:snapshots/archived_official_history.dump.sql.gz.sha256 > "$tmp/remote.dump.sha256"
actual="$(sha256sum "$tmp/remote.sqlite" | cut -d ' ' -f 1)"
declared="$(cut -d ' ' -f 1 "$tmp/remote.sha256")"
asserted="$(sed -n 's/^sha256=//p' "$tmp/remote.status")"
[[ "$actual" == "$declared" && "$declared" == "$asserted" ]] || { echo "FAIL: historical DB digest disagreement"; exit 2; }
dump_digest="$(sha256sum "$tmp/remote.dump.sql.gz" | cut -d ' ' -f 1)"
declared_dump="$(cut -d ' ' -f 1 "$tmp/remote.dump.sha256")"
asserted_dump="$(sed -n 's/^sql_dump_gzip_sha256=//p' "$tmp/remote.status")"
[[ "$dump_digest" == "$declared_dump" && "$dump_digest" == "$asserted_dump" ]] || { echo "FAIL: historical SQL dump digest disagreement"; exit 2; }
# Rebuild a second DB from only the fetched compressed SQL: no Python or temporary artifact.
gzip -dc "$tmp/remote.dump.sql.gz" | sqlite3 -bail "$tmp/rebuilt.sqlite"
for db in "$tmp/remote.sqlite" "$tmp/rebuilt.sqlite"; do
 [[ "$(sqlite3 -readonly "$db" 'PRAGMA quick_check;')" == ok ]] || exit 2
 [[ -z "$(sqlite3 -readonly "$db" 'PRAGMA foreign_key_check;')" ]] || exit 2
 for year in 2023 2024 2025; do
  panels="$(sqlite3 -readonly "$db" "SELECT (SELECT COUNT(*) FROM archive_races WHERE year=$year)+(SELECT COUNT(*) FROM archive_cancelled_scheduled_races WHERE year=$year);")"
  [[ "$panels" == 3456 ]] || { echo "FAIL: $db official scheduled panels $year=$panels"; exit 2; }
 done
 [[ "$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_races;')" == 13095 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_runners;')" == 180418 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM archive_runners a JOIN archive_races r USING (race_id) WHERE r.year BETWEEN 2023 AND 2025;")" == 142737 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_cancelled_scheduled_races;')" == 3 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM archive_races WHERE metadata_verified=1 AND year BETWEEN 2023 AND 2025;")" == 9991 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM v_archive_observed_starts;')" == 174411 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM v_archive_observed_starts WHERE jockey_id LIKE 'jra-jockey:pw04kmk%';")" == 169592 ]] || exit 2
 [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM archive_runners a JOIN archive_races r USING(race_id) WHERE r.year BETWEEN 2023 AND 2025 AND a.started IS NULL;")" == 0 ]] || exit 2
done
echo "PASS: independent permanent DB read-back and SQL-only backup reconstruction"
echo "HISTORICAL_2023_2025_SCHEDULED_PANELS=10368 RESULT_ROWS=142737 ACTUAL_FLAT_STARTS_2023_2026=174411"
echo "SQL_BACKUP_SHA=$dump_digest SQLITE_SHA=$actual"
