#!/usr/bin/env bash
set -euo pipefail
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
db="$tmp/fixture.sqlite"
sqlite3 "$db" < sql/friday_schema.sql
sqlite3 "$db" < tests/sql/friday_fixture.sql
sqlite3 -readonly -header -csv "$db" < sql/friday_report.sql > "$tmp/report.csv"
echo 'DIAGNOSTIC: fixture report CSV'; cat "$tmp/report.csv"
# H1: 2 historical starts, 1 win, 2 top3; J1: 2 starts, 2 wins; pair H1/J1: 1 start, 1 win.
# H4: 0 history, J2: 2 starts, 0 wins; pair H4/J2: 0.
actual="$(sqlite3 -readonly "$db" "WITH h AS (SELECT * FROM v_eligible_history WHERE race_date<'2026-11-21') SELECT (SELECT COUNT(*) FROM h WHERE horse_id='H1'),(SELECT SUM(win) FROM h WHERE horse_id='H1'),(SELECT SUM(top3) FROM h WHERE horse_id='H1'),(SELECT COUNT(*) FROM h WHERE jockey_id='J1'),(SELECT SUM(win) FROM h WHERE jockey_id='J1'),(SELECT COUNT(*) FROM h WHERE horse_id='H1' AND jockey_id='J1');")"
[[ "$actual" == '2|1|2|2|2|1' ]] || { echo "FAIL: $actual"; exit 1; }
[[ "$(($(wc -l < "$tmp/report.csv") - 1))" == 2 ]] || { echo 'FAIL report row count'; exit 1; }
grep -q 'H1,TEST-H1,J1,TEST-J1,2,1,2,50.0,100.0,2,2,2,100.0,100.0,1,1,1,100.0,100.0' "$tmp/report.csv"
grep -q 'H4,TEST-H4,J2,TEST-J2,0,0,0,' "$tmp/report.csv"
echo 'PASS: fixture-only horse/jockey/pair SQL joins, rates, zero history, future exclusion'
