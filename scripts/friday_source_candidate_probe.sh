#!/usr/bin/env bash
set -euo pipefail
for db in \
  operations/data_updates/jra_official_full_runner_history_20261108_v2.sqlite \
  operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite \
  operations/data_updates/multisource_overlay_20261108_v2.sqlite \
  operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite \
  operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite
do
  [[ -f "$db" ]] || continue
  printf '\n==== SOURCE=%s ====\n' "$db"
  sha256sum "$db"
  sqlite3 -readonly "$db" 'PRAGMA quick_check;'
  sqlite3 -readonly "$db" "SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('source_race','source_runner','runner_postrace','jra_result_history_full','official_past_run','official_profile') ORDER BY name;"
  for table in source_race source_runner runner_postrace jra_result_history_full official_past_run official_profile; do
    if [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$table'")" == 1 ]]; then
      echo "TABLE=$table"
      sqlite3 -readonly "$db" "SELECT COUNT(*) FROM $table;"
      sqlite3 -readonly -header -csv "$db" "SELECT * FROM $table LIMIT 1;"
    fi
  done
done
