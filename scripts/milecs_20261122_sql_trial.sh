#!/usr/bin/env bash
# Actual SQL-only research test against permanent historical database, not a forecast-model run.
set -euo pipefail
mkdir -p reports/milecs_20261122
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git fetch --no-tags origin refs/heads/data/friday-three-year-history
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/history.sqlite"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite.sha256 > "$tmp/history.sqlite.sha256"
git show FETCH_HEAD:snapshots/archived_official_history.status > "$tmp/snapshot.status"
sha="$(sha256sum "$tmp/history.sqlite"|cut -d ' ' -f1)"
expected="$(cut -d ' ' -f1 "$tmp/history.sqlite.sha256")"
status_sha="$(sed -n 's/^sha256=//p' "$tmp/snapshot.status")"
[[ "$sha" == "$expected" && "$sha" == "$status_sha" ]] || { echo "INVALID SOURCE SNAPSHOT SHA" >&2; exit 2; }
[[ "$(sqlite3 -readonly "$tmp/history.sqlite" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$tmp/history.sqlite" 'PRAGMA foreign_key_check;')" ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/history.sqlite" "SELECT (SELECT COUNT(*) FROM archive_races WHERE year BETWEEN 2023 AND 2025)+(SELECT COUNT(*) FROM archive_cancelled_scheduled_races WHERE year BETWEEN 2023 AND 2025);")" == 10368 ]] || exit 2
sqlite3 -readonly "$tmp/history.sqlite" < sql/milecs_20261122_registered_historical_trial.sql
count="$(tail -n +2 reports/milecs_20261122/registered_21_horse_history.csv|wc -l)"
[[ "$count" == 21 ]] || { echo "registered 21 horse CSV output mismatch: $count"; exit 2; }
ambiguities="$(tail -n +2 reports/milecs_20261122/registered_21_horse_id_ambiguities.csv|wc -l)"
[[ "$ambiguities" == 0 ]] || { echo "AMBIGUOUS REGISTERED HORSE OFFICIAL IDs: $ambiguities"; exit 2; }
{
 echo "source=JRA official Mile CS 2026-11-22 registration (21 runners, NOT FINAL CARD)"
 echo "reference=https://www.jra.go.jp/keiba/g1/mile/horse.html"
 echo "official_entry_release=2026-11-19"
 echo "source_sqlite_sha256=$sha"
 echo "history_2023_2025=verified_full_scheduled_race_cohort"
 echo "history_2026=partial_archived_records_only"
 echo "screenshot_odds=predicted_not_actual"
 echo "screenshot_jockeys=provisional_not_final"
 echo "registered_runners=21"
 echo "system_v51_calibrated_win_probability=NOT_CALCULATED"
 echo "official_cards_verified=NO"
 echo "script_sha256=$(sha256sum sql/milecs_20261122_registered_historical_trial.sql|cut -d ' ' -f1)"
 echo "completed_at_utc=$(date -u +%FT%TZ)"
} > reports/milecs_20261122/manifest.txt
echo '===== PROVISIONAL 21 HORSE OFFICIAL HISTORY ====='
cat reports/milecs_20261122/registered_21_horse_history.csv
echo '===== PROVISIONAL JOCKEY CANDIDATES ====='
cat reports/milecs_20261122/provisional_jockey_lookup_candidates.csv
echo '===== PROVISIONAL HORSE × JOCKEY PAIRS ====='
cat reports/milecs_20261122/provisional_horse_jockey_pair_stats.csv
echo '===== ALL ARCHIVED TURF1600 HISTORICAL STARTS (2026 PARTIAL) ====='
cat reports/milecs_20261122/registered_21_combined_2023_2026_partial_turf1600.csv
echo '===== LAST FIVE RESULT COUNT ====='
wc -l reports/milecs_20261122/registered_21_recent5_from_archive.csv
cat reports/milecs_20261122/manifest.txt
