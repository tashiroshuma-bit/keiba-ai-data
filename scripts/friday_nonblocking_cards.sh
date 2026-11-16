#!/usr/bin/env bash
# Optional Sat/Sun entry roster -> partial historical per-race Markdown.
# Racecard collection failures do not prevent delivery of verified historical tables.
set -euo pipefail
db="data/friday/archived_official_history.sqlite"
card_dir="data/friday/weekend_cards"
out="reports/friday_operational"
if [[ $# -ge 1 ]]; then db="$1"; fi
if [[ $# -ge 2 ]]; then card_dir="$2"; fi
if [[ $# -ge 3 ]]; then out="$3"; fi
mkdir -p "$out"
node scripts/friday_prepare_available_cards.mjs "$card_dir" "$out"
num="$(($(wc -l < "$out/cards_staging.csv") - 1))"
if [[ "$num" -le 0 ]]; then
  printf 'HISTORY_READY; WEEKEND_ENTRIES_UNAVAILABLE; published history-only index\n' > "$out/status.txt"
  printf 'report=HISTORICAL_ONLY\nweekend_entries=0\n' > "$out/roster_status.txt"
  node scripts/friday_mobile_report.mjs status "$out"
  echo 'FRIDAY_REPORT_PUBLISHED_HISTORY_ONLY: card sources absent'
  exit 0
fi
[[ -s "$db" ]] || { echo "HISTORY_DB_MISSING" >&2; exit 2; }
[[ "$(sqlite3 -readonly "$db" 'PRAGMA quick_check;')" == ok ]] || exit 2
# Write only to an isolated scratch DB; the permanent history is attached read-only.
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
absolute_db="$(realpath "$db")"
if [[ "$absolute_db" == *"'"* ]]; then echo 'INVALID_DB_PATH_QUOTE' >&2; exit 2; fi
if ! { printf "ATTACH DATABASE 'file:%s?mode=ro' AS hist;\n" "$absolute_db"; cat sql/friday_join_available_cards.sql; } | sqlite3 -bail "$scratch/report.sqlite"; then
  printf 'HISTORY_READY; WEEKEND_ENTRY_JOIN_FAILED; history-only delivered\n' > "$out/status.txt"
  printf 'report=HISTORICAL_ONLY\nweekend_entries=%s\njoin_error=SQL_JOIN_FAILED\n' "$num" > "$out/roster_status.txt"
  node scripts/friday_mobile_report.mjs status "$out"
  echo 'FRIDAY_REPORT_FALLBACK_AFTER_JOIN_FAILURE'
  exit 0
fi
node scripts/friday_mobile_report.mjs partial "$out/cards_joined.csv" "$out"
races="$(tail -n +2 "$out/card_coverage.csv" | wc -l)"
{
 printf 'report=PARTIAL_PER_RACE\n'
 printf 'input_rows=%s\n' "$num"
 printf 'races_with_entries=%s\n' "$races"
 printf 'roster_completeness=UNVERIFIED\n'
 printf 'horse_id_link_method=EXACT_UNIQUE_HORSE_NAME_ONLY\n'
 printf 'jockey_id_link_method=EXACT_UNIQUE_JOCKEY_NAME_ONLY\n'
} > "$out/roster_status.txt"
echo "FRIDAY_PARTIAL_RACES_PUBLISHED races=$races listed_entries=$num; official roster completeness not asserted"
