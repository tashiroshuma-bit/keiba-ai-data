#!/usr/bin/env bash
# Read-only reporting from verified historic source subset.
set -euo pipefail
db="data/friday/archived_official_history.sqlite"
out="reports/friday_full_backfill"
if [[ $# -ge 1 ]]; then db="$1"; fi
if [[ $# -ge 2 ]]; then out="$2"; fi
[[ -s "$db" ]] || { echo 'NOT_READY historical source DB missing'; exit 2; }
[[ "$(sqlite3 -readonly "$db" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$db" 'PRAGMA foreign_key_check;')" ]] || exit 2
mkdir -p "$out"
sqlite3 -readonly -header -csv "$db" '
 SELECT year,COUNT(*) all_source_races,
 SUM(CASE WHEN metadata_verified=1 AND surface IN ('"'"'芝'"'"','"'"'ダート'"'"') THEN 1 ELSE 0 END) verified_flat_races,
 SUM(CASE WHEN surface='"'"'障害'"'"' THEN 1 ELSE 0 END) confirmed_obstacles,
 SUM(CASE WHEN metadata_verified=0 AND surface!='"'"'障害'"'"' THEN 1 ELSE 0 END) condition_not_verified,
 SUM(horse_count) all_runner_rows
 FROM archive_races GROUP BY year ORDER BY year;
' > "$out/flat_coverage_by_year.csv"
sqlite3 -readonly -header -csv "$db" '
 SELECT year,venue_code,COUNT(*) observed_all_races,
 SUM(CASE WHEN metadata_verified=1 THEN 1 ELSE 0 END) verified_flat_races,
 SUM(CASE WHEN surface='"'"'障害'"'"' THEN 1 ELSE 0 END) obstacles,
 SUM(CASE WHEN metadata_verified=0 AND surface!='"'"'障害'"'"' THEN 1 ELSE 0 END) unverified
 FROM archive_races GROUP BY year,venue_code ORDER BY year,venue_code;
' > "$out/coverage_by_track_year.csv"
sqlite3 -readonly -header -csv "$db" < sql/friday_official_three_year_observed_stats.sql > "$out/official_observed_conditions.csv"
sqlite3 -readonly "$db" '
 SELECT "eligible_flat_known_placements="||COUNT(*) FROM v_archive_observed_starts;
 SELECT "verified_jockey_rides="||COUNT(*) FROM v_archive_observed_starts WHERE jockey_id LIKE "jra-jockey:pw04kmk%";
 SELECT "distinct_horses="||COUNT(DISTINCT horse_id) FROM v_archive_observed_starts;
 SELECT "distinct_jockey_ids="||COUNT(DISTINCT jockey_id) FROM v_archive_observed_starts WHERE jockey_id LIKE "jra-jockey:pw04kmk%";
'
echo 'OFFICIAL_ARCHIVE_PARTIAL_METRICS_GENERATED:'
cat "$out/flat_coverage_by_year.csv"
wc -l "$out/official_observed_conditions.csv"
printf 'FULL_THREE_YEAR_PRODUCTION=NOT_READY (source gaps and missing verified future race cards)\n' > "$out/production_status.txt"
