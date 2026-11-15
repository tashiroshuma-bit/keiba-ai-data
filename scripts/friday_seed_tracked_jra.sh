#!/usr/bin/env bash
# Import a real, bounded subset from already-Git-tracked JRA-derived SQLite files.
# Strictly NOT equivalent to the 2023-2026 canonical v12 history.
set -euo pipefail
TARGET="data/friday/tracked_research_candidate.sqlite"
if [[ $# -ge 1 ]]; then TARGET="$1"; fi
SOURCE_RESULT="operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite"
SOURCE_PROFILE="operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite"
SOURCE_KYOTO="operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite"
RESULT_SHA="4912237e688804cdbaed6a4d0b9a2019fd126b309c938fb21d8c1a637397959b"
PROFILE_SHA="e17d37e5ee0bb0d26d054eb3395278937cf3f3fb58481eb3fea8761f64b86025"
KYOTO_SHA="1558a0ac7dbaebf8edd751f586ea7c5cab19e23c814374028cdf34487754a39f"
for source in "$SOURCE_RESULT" "$SOURCE_PROFILE" "$SOURCE_KYOTO"; do
  [[ -f "$source" ]] || { echo "NOT_READY: missing tracked source $source"; exit 2; }
  [[ "$(sqlite3 -readonly "$source" 'PRAGMA quick_check;')" == ok ]] || { echo "NOT_READY: sqlite corruption $source"; exit 2; }
done
[[ "$(sha256sum "$SOURCE_RESULT" | cut -d ' ' -f 1)" == "$RESULT_SHA" ]] || { echo 'NOT_READY: result source SHA mismatch'; exit 2; }
[[ "$(sha256sum "$SOURCE_PROFILE" | cut -d ' ' -f 1)" == "$PROFILE_SHA" ]] || { echo 'NOT_READY: profile source SHA mismatch'; exit 2; }
[[ "$(sha256sum "$SOURCE_KYOTO" | cut -d ' ' -f 1)" == "$KYOTO_SHA" ]] || { echo 'NOT_READY: Kyoto profile SHA mismatch'; exit 2; }
[[ ! -e "$TARGET" ]] || { echo 'NOT_READY: refusing overwrite of an existing candidate DB'; exit 2; }
mkdir -p "$(dirname "$TARGET")"
work="$(mktemp -d "$(dirname "$TARGET")/.tracked-seed.XXXXXX")"
trap 'rm -rf "$work"' EXIT
DB="$work/research.sqlite"
sqlite3 -bail "$DB" < sql/friday_schema.sql
sqlite3 -bail "$DB" < sql/friday_tracked_research_schema.sql
sqlite3 -bail "$DB" <<'SQL'
.bail on
PRAGMA foreign_keys=ON;
ATTACH DATABASE 'operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite' AS result_src;
ATTACH DATABASE 'operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite' AS profile_src;
ATTACH DATABASE 'operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite' AS kyoto_src;
BEGIN IMMEDIATE;
INSERT INTO tracked_source_db VALUES
('4912237e688804cdbaed6a4d0b9a2019fd126b309c938fb21d8c1a637397959b',
 'operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite',
 'Git-tracked official-HTML-derived source; raw HTML bytes not independently rechecked',
 'DERIVED_NOT_ORIGINAL'),
('e17d37e5ee0bb0d26d054eb3395278937cf3f3fb58481eb3fea8761f64b86025',
 'operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite',
 'Git-tracked official-profile-derived source; raw profile bytes not independently rechecked',
 'DERIVED_NOT_ORIGINAL'),
('1558a0ac7dbaebf8edd751f586ea7c5cab19e23c814374028cdf34487754a39f',
 'operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite',
 'Git-tracked Kyoto official-profile-derived source; original bytes not independently rechecked',
 'DERIVED_NOT_ORIGINAL');
INSERT INTO tracked_result_runner
  (race_date,source_race_key,venue,race_number,horse_number,horse_id,horse_name,
   jockey_name,finish_position,source_url,source_html_sha256,source_db_sha256)
SELECT '2026-11-08',m.race,m.track,m.race_no,s.horse_number,s.horse_id,s.horse_name,
       s.jockey_name,s.finish_position,s.source_url,s.source_sha256,
       '4912237e688804cdbaed6a4d0b9a2019fd126b309c938fb21d8c1a637397959b'
FROM result_src.runner_postrace s
JOIN result_src.source_race m ON m.race=s.race
WHERE m.verified_checkpoint=1 AND m.expected_finishers=m.parsed_finishers
  AND m.official_id_coverage=m.parsed_finishers
  AND s.horse_id LIKE 'jra:%' AND length(trim(s.jockey_name))>0
  AND s.source_sha256=m.source_sha256 AND s.source_url=m.source_url;
INSERT INTO tracked_profile_past_run
  (horse_id,horse_name,prior_race_date,venue,race_name,distance_surface,going,
   finish_position,jockey_name,source_profile_sha256,observed_at,source_db_sha256)
SELECT p.horse_id,p.horse_name,h.prior_race_date,h.venue,h.race_name,
       h.distance_surface,h.going,h.finish_position,h.jockey_name,
       h.source_profile_sha256,h.profile_observed_at,
       'e17d37e5ee0bb0d26d054eb3395278937cf3f3fb58481eb3fea8761f64b86025'
FROM profile_src.official_past_run h
JOIN profile_src.official_profile p ON p.horse_id=h.horse_id
WHERE p.horse_id LIKE 'jra:%'
  AND (h.distance_surface LIKE '芝%' OR h.distance_surface LIKE 'ダート%')
  AND h.prior_race_date<'2026-11-08'
  AND h.source_profile_sha256=p.source_sha256;
INSERT INTO tracked_profile_past_run
  (horse_id,horse_name,prior_race_date,venue,race_name,distance_surface,going,
   finish_position,jockey_name,source_profile_sha256,observed_at,source_db_sha256)
SELECT p.horse_id,p.horse_name,h.prior_race_date,h.venue,h.race_name,
       h.distance_surface,h.going,h.finish_position,h.jockey_name,
       h.source_profile_sha256,h.profile_observed_at,
       '1558a0ac7dbaebf8edd751f586ea7c5cab19e23c814374028cdf34487754a39f'
FROM kyoto_src.official_past_run h
JOIN kyoto_src.official_profile p ON p.horse_id=h.horse_id
WHERE p.horse_id LIKE 'jra:%'
  AND (h.distance_surface LIKE '芝%' OR h.distance_surface LIKE 'ダート%')
  AND h.prior_race_date<'2026-11-08'
  AND h.source_profile_sha256=p.source_sha256;
COMMIT;
SQL
[[ "$(sqlite3 -readonly "$DB" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$DB" 'PRAGMA foreign_key_check;')" ]] || exit 2
result_count="$(sqlite3 -readonly "$DB" 'SELECT COUNT(*) FROM tracked_result_runner;')"
profile_count="$(sqlite3 -readonly "$DB" 'SELECT COUNT(*) FROM tracked_profile_past_run;')"
if [[ "$result_count" == 0 || "$profile_count" == 0 ]]; then
  echo "NOT_READY: no linked real rows ($result_count,$profile_count)" >&2
  exit 2
fi
mv "$DB" "$TARGET"
sha256sum "$TARGET" > "$TARGET.sha256"
printf 'RESEARCH_SEED_CREATED; real historical subset, not official full coverage: nov08_result_runners=%s profile_past_runs=%s\n' "$result_count" "$profile_count"
mkdir -p reports/friday_source_audit
sqlite3 -readonly -header -csv "$TARGET" < sql/friday_tracked_seed_stats.sql > reports/friday_source_audit/tracked_profile_horse_stats.csv
head -n 12 reports/friday_source_audit/tracked_profile_horse_stats.csv
