#!/usr/bin/env bash
# Explain each row excluded from bounded JRA-derived seed. SQL-only.
set -euo pipefail
mkdir -p reports/friday_source_audit
R="operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite"
P="operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite"
K="operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite"
sqlite3 -readonly -header -csv "$R" <<'SQL' > reports/friday_source_audit/real_result_seed_coverage.csv
WITH categories AS (
SELECT CASE
 WHEN m.race IS NULL THEN 'NO_SOURCE_RACE'
 WHEN m.verified_checkpoint!=1 THEN 'CHECKPOINT_NOT_VERIFIED'
 WHEN m.expected_finishers!=m.parsed_finishers THEN 'RACE_COUNT_MISMATCH'
 WHEN m.official_id_coverage!=m.parsed_finishers THEN 'OFFICIAL_ID_COVERAGE_INCOMPLETE'
 WHEN s.horse_id NOT LIKE 'jra:%' THEN 'MISSING_OFFICIAL_HORSE_ID'
 WHEN s.jockey_name IS NULL OR length(trim(s.jockey_name))=0 THEN 'MISSING_JOCKEY_NAME'
 WHEN s.source_sha256!=m.source_sha256 OR s.source_url!=m.source_url THEN 'SOURCE_LINK_MISMATCH'
 ELSE 'IMPORTED' END reason
FROM runner_postrace s LEFT JOIN source_race m ON m.race=s.race
)
SELECT reason,COUNT(*) records FROM categories GROUP BY reason ORDER BY reason;
SQL
sqlite3 -readonly -header -csv "$P" <<'SQL' > reports/friday_source_audit/real_profile_seed_coverage.csv
WITH categories AS (
SELECT CASE
 WHEN p.horse_id IS NULL OR p.horse_id NOT LIKE 'jra:%' THEN 'HORSE_ID_UNVERIFIED'
 WHEN h.distance_surface NOT LIKE '芝%' AND h.distance_surface NOT LIKE 'ダート%' THEN 'NOT_FLAT_TURF_OR_DIRT'
 WHEN h.prior_race_date>='2026-11-08' THEN 'NOT_EARLIER_THAN_2026_11_08'
 WHEN h.source_profile_sha256!=p.source_sha256 THEN 'PROFILE_ORIGINAL_HASH_DISAGREES'
 ELSE 'IMPORTED' END reason
FROM official_past_run h LEFT JOIN official_profile p ON p.horse_id=h.horse_id
)
SELECT reason,COUNT(*) records FROM categories GROUP BY reason ORDER BY reason;
SQL
echo 'Nov08 result candidate coverage:'
cat reports/friday_source_audit/real_result_seed_coverage.csv
echo 'Past profile candidate coverage:'
cat reports/friday_source_audit/real_profile_seed_coverage.csv

sqlite3 -readonly -header -csv "$K" <<'SQL' > reports/friday_source_audit/real_kyoto_profile_seed_coverage.csv
WITH categories AS (
SELECT CASE
 WHEN p.horse_id IS NULL OR p.horse_id NOT LIKE 'jra:%' THEN 'HORSE_ID_UNVERIFIED'
 WHEN h.distance_surface NOT LIKE '芝%' AND h.distance_surface NOT LIKE 'ダート%' THEN 'NOT_FLAT_TURF_OR_DIRT'
 WHEN h.prior_race_date>='2026-11-08' THEN 'NOT_EARLIER_THAN_2026_11_08'
 WHEN h.source_profile_sha256!=p.source_sha256 THEN 'PROFILE_ORIGINAL_HASH_DISAGREES'
 ELSE 'IMPORTED' END reason
FROM official_past_run h LEFT JOIN official_profile p ON p.horse_id=h.horse_id
)
SELECT reason,COUNT(*) records FROM categories GROUP BY reason ORDER BY reason;
SQL
echo 'Kyoto profile candidate coverage:'
cat reports/friday_source_audit/real_kyoto_profile_seed_coverage.csv
