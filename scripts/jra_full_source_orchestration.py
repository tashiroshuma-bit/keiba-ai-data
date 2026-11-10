"""Shard source-attested week seeds over JRA's public official result pages.

This collects immutable primary HTML evidence; it NEVER fills or changes the
canonical database. Each shard has a bounded source rate and publishes its
success/failure ledger. One year/week is a transaction for recoverability.
"""
import argparse
import json
from pathlib import Path
from scripts.jra_official_race_bulk_id_crawler import run


def collect_week_shard(seed_json, output_dir, *, shard=0, shards=1,
                       max_pages_week=90, delay=1.5, year=None):
    if not (1 <= shards <= 128 and 0 <= shard < shards):
        raise ValueError('invalid shard index')
    source = json.loads(Path(seed_json).read_text(encoding='utf-8'))
    rows = source.get('rows')
    if not isinstance(rows, list):
        raise ValueError('expected primary-source seed rows')
    # Deterministic sorting/sharding. One week is covered by one job only.
    weeks = {}
    for row in rows:
        key = (int(row['iso_year']), int(row['iso_week']))
        if year and key[0] != year:
            continue
        if key in weeks:
            raise ValueError('duplicate source-attested calendar week')
        weeks[key] = row['seed_url']
    selection = [(k, url) for i, (k, url) in enumerate(sorted(weeks.items()))
                 if i % shards == shard]
    root = Path(output_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError('immutable shard destination is not empty')
    root.mkdir(parents=True, exist_ok=True)
    success = []
    failures = []
    pages, horse_rows = 0, 0
    for (iso_year, iso_week), url in selection:
        label = f'{iso_year}-w{iso_week:02d}'
        try:
            outcome = run([url], root / label, max_pages=max_pages_week,
                          delay=delay, target_week=(iso_year, iso_week))
            pages += outcome['success']
            horse_rows += outcome['horse_rows']
            success.append({'week': label, **outcome})
            if outcome['success'] == 0 or outcome['failed']:
                failures.append({'week': label, 'reason': 'source failures or zero pages',
                                 'attempted': outcome['attempted'],
                                 'failed_pages': outcome['failed']})
        except Exception as e:
            failures.append({'week': label, 'reason': type(e).__name__ + ': ' + str(e)[:300]})
    manifest = {'schema': 'jra-identity-week-shard-run-v1',
                'shard_index': shard, 'shards': shards,
                'total_source_weeks': len(weeks), 'selected_weeks': len(selection),
                'successful_week_fetches': len(success),
                'downloaded_races': pages, 'source_horse_links': horse_rows,
                'failures': failures, 'week_details': success,
                'canonical_join_not_yet_performed': True}
    (root / 'batch_summary.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seed-file', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--shard', type=int, required=True)
    p.add_argument('--shards', type=int, required=True)
    p.add_argument('--max-pages-week', type=int, default=90)
    p.add_argument('--delay', type=float, default=1.5)
    p.add_argument('--year', type=int)
    a = p.parse_args()
    out = collect_week_shard(a.seed_file, a.output_dir, shard=a.shard, shards=a.shards,
                             max_pages_week=a.max_pages_week, delay=a.delay, year=a.year)
    print(json.dumps({k: out[k] for k in ('shard_index','selected_weeks',
                'successful_week_fetches','downloaded_races','source_horse_links','failures')},
                ensure_ascii=False))

if __name__ == '__main__':
    main()