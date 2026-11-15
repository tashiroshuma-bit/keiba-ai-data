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
sqlite3 -readonly -header -csv "$db" '
 WITH expected(year,expected_flat_races) AS (VALUES (2023,3337),(2024,3337),(2025,3344)),
 observed AS (
  SELECT year,COUNT(*) actual_verified_flat
  FROM archive_races WHERE metadata_verified=1 AND surface IN ('"'"'芝'"'"','"'"'ダート'"'"')
  GROUP BY year
 )
 SELECT expected.year,expected_flat_races,COALESCE(observed.actual_verified_flat,0) actual_verified_flat,
        expected_flat_races-COALESCE(observed.actual_verified_flat,0) gap,
        "BASELINE_V12_20261112_PRIOR_AUDIT_NOT_REALTIME" baseline_provenance
 FROM expected LEFT JOIN observed USING(year) ORDER BY expected.year;
' > "$out/three_year_full_flat_gap.csv"
echo 'THREE_YEAR_COVERAGE_GAP_VS_PRIOR_AUDIT:'
cat "$out/three_year_full_flat_gap.csv"
sqlite3 -readonly -header -csv "$db" '
 WITH expected(year,expected_horse_rows) AS (VALUES (2023,47672),(2024,47181),(2025,47884)),
 observed AS (
 SELECT p.year,COUNT(*) actual_source_horse_rows
 FROM archive_runners r JOIN archive_races p USING (race_id)
 WHERE p.year BETWEEN 2023 AND 2025 GROUP BY p.year
 )
 SELECT expected.year,expected_horse_rows,COALESCE(actual_source_horse_rows,0) actual_source_horse_rows,
        expected_horse_rows-COALESCE(actual_source_horse_rows,0) unrepresented_runner_rows,
        "BASELINE_V12_20261112_PRIOR_AUDIT" baseline_provenance
 FROM expected LEFT JOIN observed USING(year) ORDER BY expected.year;
' > "$out/three_year_runner_reconciliation.csv"
sqlite3 -readonly -header -csv "$db" '
 WITH RECURSIVE nums(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM nums WHERE n<12),
 sessions AS (
  SELECT DISTINCT SUBSTR(race_id,1,10) session_key,year,race_date,venue_code
  FROM archive_races WHERE year BETWEEN 2023 AND 2025
 )
 SELECT s.year,s.race_date,s.venue_code,s.session_key,
        s.session_key||printf("%02d",n.n) missing_race_id,
        "NOT_PRESENT_IN_VERIFIED_OFFICIAL_RESULT_HTML_ARCHIVES" status
 FROM sessions s CROSS JOIN nums n
 LEFT JOIN archive_races r ON r.race_id=s.session_key||printf("%02d",n.n)
 WHERE r.race_id IS NULL
 ORDER BY s.year,s.race_date,s.venue_code,n.n;
' > "$out/missing_races_in_observed_sessions.csv"
echo 'FULL_THREE_YEAR_RUNNER_RECONCILIATION:'
cat "$out/three_year_runner_reconciliation.csv"
echo 'MISSING_RACE_IDS_FROM_EXISTING_SESSIONS:'
cat "$out/missing_races_in_observed_sessions.csv"
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
