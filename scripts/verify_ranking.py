"""Independently audit saved rank probabilities, labels and all hit counts.

This checks every saved race against the canonical result loader. It does not
rebuild all features or independently prove that each ordered pick is joint-MAP.
"""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'keiba_v48'))
from completion_validation import sha
from enriched_features import load_archive
from features import timestamp, finish
from ranking_model import RankModel
from validation import canonical


def verify(db, directory, predictions, lag):
    folder = Path(directory)
    report = json.loads((folder / f'evaluation_lag{lag}.json').read_text())
    frozen = json.loads((folder / f'selection_lag{lag}.json').read_text())
    artifact = json.loads((folder / f'model_lag{lag}.json').read_text())
    assert sha(db) == report['input_db_sha256'] == frozen['input_db_sha256']
    assert sha(predictions) == report['predictions_sha256']
    assert sha(folder / f'selection_lag{lag}.json') == report['selection_sha256']
    assert sha(folder / f'model_lag{lag}.json') == report['model_sha256'] == frozen['model_sha256']
    assert RankModel.from_dict(artifact).to_dict() == artifact
    grid = frozen['grid']
    def selection_key(row):
        m = row['selection_metrics']; n = m['races']
        return (-round(m['top3_recall'] * 3 * n), -round(m['winner_hit'] * n), m['mean_rank_log_loss'], row['name'])
    assert min(grid, key=selection_key)['name'] == frozen['selected'] == report['selected']
    for name, expected in frozen['source_sha256'].items():
        assert sha(ROOT / 'keiba_v48' / name) == expected
    old = json.loads((ROOT / 'keiba_v48/deployment/active_model.json').read_text())
    assert hashlib.sha256(canonical(old).encode()).hexdigest() == report['baseline_model_sha256']
    _, fields, _ = load_archive(db, lag, allow_unlinked_fields=True)
    actual = collections.defaultdict(list)
    for row in fields:
        actual[row['race_id']].append(row)
    boundary = max(timestamp(frozen['selection_end']), timestamp(old['calibration_end'] or old['train_end']))
    eligible = set()
    for rid, rows in actual.items():
        if (timestamp(rows[0]['off_timestamp']).year in (2025, 2026)
                and timestamp(rows[0]['off_timestamp']) - dt.timedelta(minutes=5) > boundary
                and all(sum(finish(r) == k for r in rows) == 1 for k in (1, 2, 3))):
            eligible.add(rid)
    records = json.loads(gzip.decompress(Path(predictions).read_bytes()))
    assert len({r['race_id'] for r in records}) == len(records)
    assert {r['race_id'] for r in records} == eligible
    metrics = collections.defaultdict(list)
    for r in records:
        rows = actual[r['race_id']]
        numbers = r['horse_numbers']
        assert len(numbers) == len(set(numbers)) == len(rows)
        assert set(numbers) == {x['horse_number'] for x in rows}
        target = [next(x['horse_number'] for x in rows if finish(x) == k) for k in (1, 2, 3)]
        for family in ('baseline', 'candidate'):
            value = r[family]; p = np.asarray(value['marginal_probabilities'])
            assert p.shape == (len(numbers), 3) and np.isfinite(p).all() and (p >= 0).all()
            assert np.max(np.abs(p.sum(axis=0)-1)) < 1e-10
            assert np.max(p.sum(axis=1)) <= 1 + 1e-10
            winner = min(range(len(numbers)), key=lambda i: (-p[i,0], int(numbers[i])))
            trio = sorted(range(len(numbers)), key=lambda i: (-p[i].sum(), int(numbers[i])))[:3]
            assert value['winner_pick'] == numbers[winner]
            assert set(value['top3_pick']) == {numbers[i] for i in trio}
            assert value['target'] == target
            ordered = value['ordered_pick']
            assert len(ordered) == len(set(ordered)) == 3 and set(ordered) <= set(numbers)
            logs = [-math.log(max(float(p[numbers.index(target[k]), k]), 1e-300)) for k in range(3)]
            computed = dict(winner_hit=int(numbers[winner] == target[0]),
                top3_recall=len(set(value['top3_pick']) & set(target))/3,
                top3_all_hit=int(set(value['top3_pick']) == set(target)),
                ordered_all_hit=int(ordered == target), mean_rank_log_loss=sum(logs)/3,
                winner_log_loss=logs[0], ordered_position_hits=[int(ordered[k] == target[k]) for k in range(3)])
            for key in computed:
                assert np.allclose(computed[key], value[key], rtol=0, atol=1e-12), key
            metrics[r['date'][:4], family].append(computed)
    for year, families in report['years'].items():
        for family in ('baseline', 'candidate'):
            values = metrics[year, family]
            assert len(values) == families[family]['races']
            for key in values[0]:
                assert np.allclose(np.mean([v[key] for v in values], axis=0), families[family][key], rtol=0, atol=1e-12)
    assert report['database_unchanged'] and report['maximum_reload_error'] == 0
    return dict(verified=True, lag_days=lag, races=len(records), input_db_sha256=sha(db),
                predictions_sha256=sha(predictions), model_sha256=report['model_sha256'],
                checks=['all saved race IDs and result labels', 'marginal normalization and occupancy',
                        'probability-ranked picks', 'independently counted hits and log losses',
                        'calibration-selection artifact and source hashes', 'model JSON roundtrip'],
                full_feature_replay=False, independent_ordered_MAP_replay=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'directory', 'predictions'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--lag', required=True, type=int, choices=(2,7))
    a = p.parse_args(); result = verify(a.db, a.directory, a.predictions, a.lag)
    (Path(a.directory) / f'verification_lag{a.lag}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
