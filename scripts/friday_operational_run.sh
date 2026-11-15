#!/usr/bin/env bash
# Friday runner: rebuild independent of container/Python; preserve partial data but
# never assert a complete all-race report without verified full official ledger.
set -euo pipefail
out="reports/friday_operational"
mkdir -p "$out" data/friday
printf 'run_utc=%s\ncode_commit=%s\n' "$(date -u +%FT%TZ)" "$(git rev-parse HEAD)" > "$out/manifest.txt"
# The Git-tracked source databases are permanent inputs; generated DB is disposable.
bash scripts/friday_seed_tracked_jra.sh data/friday/available_historical_subset.sqlite >> "$out/manifest.txt"
cp reports/friday_source_audit/tracked_profile_horse_stats.csv "$out/partial_horse_profile_stats.csv"
sha256sum data/friday/available_historical_subset.sqlite >> "$out/manifest.txt"
if [[ ! -s data/friday/ledger/source_manifest.csv || ! -s data/friday/ledger/races.csv || ! -s data/friday/ledger/historical_starts.csv || ! -s data/friday/ledger/declared_entries.csv ]]; then
  printf 'all_races_status=NOT_READY\nreason=verified_complete_official_history_and_friday_cards_not_imported\n' | tee -a "$out/manifest.txt"
  echo "NOT_READY: available subset generated, full next-weekend card statistics not possible" > "$out/status.txt"
  exit 2
fi
if ! bash scripts/friday_sql_rebuild_from_ledger.sh data/friday/ledger data/friday/official_ledger.sqlite data/friday/originals >> "$out/manifest.txt"; then
  printf 'all_races_status=NOT_READY\nreason=source_provenance_or_import_check_failed\n' | tee -a "$out/manifest.txt"
  exit 2
fi
bash scripts/friday_sql_report.sh data/friday/official_ledger.sqlite "$out"
printf 'all_races_status=PARTIAL_PENDING_ROSTER_COMPLETENESS_AUDIT\n' | tee -a "$out/manifest.txt"
# Roster completeness and jockey ID coverage not yet certified; fail closed.
exit 2
