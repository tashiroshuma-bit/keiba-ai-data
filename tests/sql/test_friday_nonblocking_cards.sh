#!/usr/bin/env bash
# Real permanent JRA history + *synthetic* partial Sat/Sun card test only.
set -euo pipefail
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp" reports/friday_operational' EXIT
git fetch --no-tags origin refs/heads/data/friday-three-year-history
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/history.sqlite"
[[ "$(sqlite3 -readonly "$tmp/history.sqlite" 'PRAGMA quick_check;')" == ok ]]
mkdir -p "$tmp/empty"
export FRIDAY_WEEKEND_SAT=2026-11-21
bash scripts/friday_nonblocking_cards.sh "$tmp/history.sqlite" "$tmp/empty"
grep -q '^report=HISTORICAL_ONLY$' reports/friday_operational/roster_status.txt
grep -q 'WEEKEND_ENTRIES_UNAVAILABLE' reports/friday_operational/status.txt
test -f reports/friday_operational/INDEX.md
# Independent trial of multiple provisional sources: one clash, one unknown horse,
# one different date to ignore. Must publish two race pages, never block all.
bash scripts/friday_nonblocking_cards.sh "$tmp/history.sqlite" tests/fixtures/friday_partial_cards
grep -q '^report=PARTIAL_PER_RACE$' reports/friday_operational/roster_status.txt
grep -q '^input_rows=3$' reports/friday_operational/roster_status.txt
grep -q '^races_with_entries=2$' reports/friday_operational/roster_status.txt
grep -q 'CONFLICT_PROVISIONAL' reports/friday_operational/cards_staging.csv
grep -q 'NO_HORSE_ID_HISTORY' reports/friday_operational/cards_joined.csv
grep -q 'MATCHED_EXACT_UNIQUE_NAME' reports/friday_operational/cards_joined.csv
grep -Fq '**62.5%** (5/8)' reports/friday_operational/2026-11-21_京都_1R.md
grep -q 'SOURCE_CONFLICT' reports/friday_operational/cards_joined.csv
grep -q '架空のSQL動作試験' reports/friday_operational/2026-11-21_京都_1R.md
grep -q '存在しない検証馬' reports/friday_operational/2026-11-22_京都_11R.md
grep -q '未照合' reports/friday_operational/2026-11-22_京都_11R.md
# No history for a first-time entrant is valid missingness; don't impute a 0% chance.
grep '存在しない検証馬' reports/friday_operational/2026-11-22_京都_11R.md | grep -Fq '未照合 | 未照合'
! grep '存在しない検証馬' reports/friday_operational/2026-11-22_京都_11R.md | grep -Fq '0%'
grep -Fq '初出走馬など過去成績がない馬は、欠損のまま掲載' reports/friday_operational/2026-11-22_京都_11R.md
grep -q '取得できた出走情報' reports/friday_operational/2026-11-22_京都_11R.md
grep -q '部分レポート' reports/friday_operational/INDEX.md
# No represented race is claimed as a verified complete JRA roster.
! grep -q 'OFFICIAL_VERIFIED' reports/friday_operational/INDEX.md
echo 'PASS: 0 card rows -> history-only; mixed card sources -> two partial race tables; conflict/unknowns explicitly shown'
