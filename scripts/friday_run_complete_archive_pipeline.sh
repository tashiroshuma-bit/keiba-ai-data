#!/usr/bin/env bash
# Recover 46 known + 8 additional JRA original HTML evidence artifacts and rebuild one SQL database.
set -euo pipefail
if [[ -z "$GH_TOKEN" ]]; then echo "GH_TOKEN missing"; exit 2; fi
root="/tmp/friday-all-JRA-originals"
mkdir -p "$root"
gh run download 42780017487 --repo "$GITHUB_REPOSITORY" --dir "$root/three_years"
gh run download 42780335360 --repo "$GITHUB_REPOSITORY" --dir "$root/twenty26"
gh run download 42944374933 --repo "$GITHUB_REPOSITORY" --dir "$root/missing_days"
bash scripts/friday_find_additional_originals.sh
for shard in $(seq 0 7); do
  name="jra-review-missing16-shard-$shard"
  run_id="$(awk -F "\t" -v n="$name" '$2==n{print $6;exit}' reports/friday_full_backfill/missing16_artifacts.tsv)"
  [[ -n "$run_id" ]] || { echo "Missing run for $name"; exit 2; }
  mkdir -p "$root/extra/$name"
  gh run download "$run_id" --repo "$GITHUB_REPOSITORY" --name "$name" --dir "$root/extra/$name"
done
printf 'RECOVERED_WEEKLY_MANIFESTS='
find "$root" -type f -name official_race_horse_ids.json | wc -l
node scripts/friday_restore_archive_results.mjs "$root" reports/friday_full_backfill/staging
bash scripts/friday_import_archive_staging.sh reports/friday_full_backfill/staging data/friday/archived_official_history.sqlite
bash scripts/friday_official_three_year_stats.sh data/friday/archived_official_history.sqlite reports/friday_full_backfill
