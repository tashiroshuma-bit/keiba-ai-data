#!/usr/bin/env bash
# Atomic JRA restored staging CSV -> SQLite import (no Python).
set -euo pipefail
staging="reports/friday_full_backfill/staging"
target="data/friday/archived_official_history.sqlite"
if [[ $# -ge 1 ]]; then staging="$1"; fi
if [[ $# -ge 2 ]]; then target="$2"; fi
[[ -s "$staging/races.csv" && -s "$staging/runners.csv" && -s "$staging/summary.json" ]] || { echo 'NOT_READY: restored CSV missing'; exit 2; }
command -v sqlite3 >/dev/null
command -v jq >/dev/null
mkdir -p "$(dirname "$target")"
tmp="$(mktemp -d "$(dirname "$target")/.official-import.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
db="$tmp/official.sqlite"
sqlite3 -bail "$db" < sql/friday_archived_official_schema.sql
cat > "$tmp/import.sql" <<EOF
.bail on
PRAGMA foreign_keys=ON;
.mode csv
.import --skip 1 "$staging/races.csv" archive_races
.import --skip 1 "$staging/runners.csv" archive_runners
EOF
sqlite3 -bail "$db" < "$tmp/import.sql"
expected_races="$(jq -r '.source_verified_races' "$staging/summary.json")"
expected_runners="$(jq -r '.source_verified_runners' "$staging/summary.json")"
actual_races="$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_races;')"
actual_runners="$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_runners;')"
[[ "$expected_races" == "$actual_races" && "$expected_runners" == "$actual_runners" ]] || {
  echo "NOT_READY: CSV/SQLite count mismatch expected=$expected_races,$expected_runners actual=$actual_races,$actual_runners" >&2
  exit 2
}
[[ "$(sqlite3 -readonly "$db" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$db" 'PRAGMA foreign_key_check;')" ]] || exit 2
hash_errors="$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM archive_runners r JOIN archive_races p USING (race_id) WHERE r.source_sha256!=p.source_sha256;')"
[[ "$hash_errors" == 0 ]] || { echo "NOT_READY: unmatched source SHA in $hash_errors rows"; exit 2; }
dup_ids="$(sqlite3 -readonly "$db" 'SELECT COUNT(*) FROM (SELECT race_id,horse_id,COUNT(*) n FROM archive_runners GROUP BY race_id,horse_id HAVING n>1);')"
[[ "$dup_ids" == 0 ]] || { echo "NOT_READY: duplicated official horse ID in one race"; exit 2; }
mv "$db" "$target"
sha256sum "$target" > "$target.sha256"
mkdir -p reports/friday_full_backfill
sqlite3 -readonly -header -csv "$target" '
 SELECT year,COUNT(*) official_source_races,SUM(horse_count) official_id_horse_rows,
 SUM(CASE WHEN race_number BETWEEN 1 AND 12 THEN 0 ELSE 1 END) bad_race_numbers
 FROM archive_races GROUP BY year ORDER BY year;
' > reports/friday_full_backfill/coverage.csv
printf 'SOURCE_VERIFIED_IMPORT_SUCCESS: races=%s horse_rows=%s\n' "$actual_races" "$actual_runners"
cat reports/friday_full_backfill/coverage.csv
