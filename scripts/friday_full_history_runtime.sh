#!/usr/bin/env bash
# Friday 21:00 JST, production readiness gate for the permanent historical source.
# No Python. Never promote a not-ready weekend roster to full official statistics.
set -euo pipefail
output="reports/friday_operational"
mkdir -p "$output"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
branch="data/friday-three-year-history"
git fetch --no-tags origin "refs/heads/$branch"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/history.sqlite"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite.sha256 > "$tmp/history.sha256"
git show FETCH_HEAD:snapshots/archived_official_history.status > "$tmp/history.status"
actual="$(sha256sum "$tmp/history.sqlite" | cut -d ' ' -f 1)"
expected="$(cut -d ' ' -f 1 "$tmp/history.sha256")"
claimed="$(sed -n 's/^sha256=//p' "$tmp/history.status")"
[[ "$actual" == "$expected" && "$actual" == "$claimed" ]] || { echo 'FAIL: canonical history checksum mismatch' | tee "$output/status.txt"; exit 2; }
[[ "$(sqlite3 -readonly "$tmp/history.sqlite" 'PRAGMA quick_check;')" == ok ]] || { echo 'FAIL: SQLite quick_check'; exit 2; }
[[ -z "$(sqlite3 -readonly "$tmp/history.sqlite" 'PRAGMA foreign_key_check;')" ]] || { echo 'FAIL: SQLite foreign keys'; exit 2; }
year_totals="$(sqlite3 -readonly "$tmp/history.sqlite" "
 SELECT group_concat(year||':'||n,'|') FROM (
 SELECT r.year,COUNT(*) n FROM archive_runners a JOIN archive_races r USING(race_id)
 WHERE r.year IN (2023,2024,2025)
 GROUP BY r.year ORDER BY r.year);")"
[[ "$year_totals" == '2023:47672|2024:47181|2025:47884' ]] || {
  printf 'NOT_READY: annual horse result rows disagree: %s\n' "$year_totals" | tee "$output/status.txt"; exit 2;
}
sqlite3 -readonly -header -csv "$tmp/history.sqlite" "
 SELECT year,COUNT(*) race_results,
 SUM(CASE WHEN surface IN ('芝','ダート') AND metadata_verified=1 THEN 1 ELSE 0 END) flat_races,
 SUM(CASE WHEN surface='障害' THEN 1 ELSE 0 END) obstacle_races
 FROM archive_races WHERE year IN (2023,2024,2025) GROUP BY year ORDER BY year;" > "$output/historical_coverage.csv"
sqlite3 -readonly -header -csv "$tmp/history.sqlite" "
 SELECT COUNT(*) eligible_flat_finish_rows,
 SUM(CASE WHEN jockey_id LIKE 'jra-jockey:pw04kmk%' THEN 1 ELSE 0 END) official_jockey_id_rows,
 COUNT(DISTINCT horse_id) horse_ids,
 COUNT(DISTINCT CASE WHEN jockey_id LIKE 'jra-jockey:pw04kmk%' THEN jockey_id END) jockey_ids
 FROM v_archive_observed_starts WHERE substr(race_date,1,4) IN ('2023','2024','2025');" > "$output/historical_id_coverage.csv"
printf 'runtime_utc=%s\nruntime_code_commit=%s\nremote_source_branch=%s\nremote_sqlite_sha256=%s\nannual_horse_rows=%s\nsource_scope=OFFICIAL_ORIGINAL_HTML_SHA_VERIFIED_WITH_RACE_EXCEPTIONS\n' \
  "$(date -u +%FT%TZ)" "$(git rev-parse HEAD)" "$branch" "$actual" "$year_totals" > "$output/manifest.txt"
# The official roster needs to have been captured for the forthcoming Sat/Sun weekend
# with horse ID, jockey ID, race ID and source SHA, plus an independent headcount.
# Until it is available, full all-race reports are NOT READY.
card_dir="data/friday/official_cards"
if [[ ! -s "$card_dir/latest_verified.csv" ]]; then
  printf 'NOT_READY: complete official next-weekend racecards and roster headcounts are not loaded\n' | tee "$output/status.txt"
  printf 'full_friday_report=NOT_READY\nreason=OFFICIAL_WEEKEND_ROSTER_ABSENT\n' >> "$output/manifest.txt"
  exit 2
fi
# This job deliberately does not silently accept a manually written CSV as certified.
# A separate official-card source-byte verifier must be implemented and pass before opening this gate.
printf 'NOT_READY: official card SHA and independent roster reconciliation not yet implemented\n' | tee "$output/status.txt"
printf 'full_friday_report=NOT_READY\nreason=OFFICIAL_ROSTER_SOURCE_BYTE_VERIFICATION_MISSING\n' >> "$output/manifest.txt"
exit 2
