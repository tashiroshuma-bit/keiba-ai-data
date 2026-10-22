"""Frozen rank-only experiment; selection precedes all 2025/2026 evaluation."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from completion_validation import pack, sha
from enriched_features import load_archive, history_index, previous_contract_index
from features import timestamp
from fitted_model import HierarchicalModel
from historical_replay import eligible_split
from ranking_model import RankModel, augment, top3_labels, joint_distribution, picks
from validation import canonical

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / 'RANKING_PROTOCOL.json').read_text())


def save(path, value):
    raw = canonical(value).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)
    return sha(path)


def record(race, marginal, joint):
    target = top3_labels(race)
    numbers = [row['horse_number'] for row in race['rows']]
    winner, trio, ordered = picks(marginal, joint, numbers)
    logs = [-math.log(max(float(marginal[target[k], k]), 1e-300)) for k in range(3)]
    return dict(winner_hit=int(winner == target[0]), top3_recall=len(set(trio) & set(target)) / 3,
                top3_all_hit=int(set(trio) == set(target)), ordered_all_hit=int(ordered == target),
                mean_rank_log_loss=sum(logs) / 3, winner_log_loss=logs[0],
                ordered_position_hits=[int(ordered[k] == target[k]) for k in range(3)],
                winner_pick=numbers[winner], top3_pick=[numbers[i] for i in trio],
                ordered_pick=[numbers[i] for i in ordered], target=[numbers[i] for i in target],
                marginal_probabilities=marginal.tolist(),
                joint_target_probability=float(joint[tuple(target)]))


def aggregate(records):
    if not records:
        raise ValueError('nonempty rank evaluation required')
    names = ('winner_hit', 'top3_recall', 'top3_all_hit', 'ordered_all_hit', 'mean_rank_log_loss', 'winner_log_loss')
    return dict(races=len(records), **{k:float(np.mean([r[k] for r in records])) for k in names},
                ordered_position_hits=np.mean([r['ordered_position_hits'] for r in records], axis=0).tolist())


def conditional_loss(model, races, temperature):
    losses = []
    for r in races:
        scores = model.scores(r['features']) / temperature
        remaining = list(range(len(r['features'])))
        total = 0.
        for k, winner in enumerate(top3_labels(r)):
            x = scores[k, remaining]; maximum = x.max()
            total += maximum + np.log(np.exp(x - maximum).sum()) - scores[k, winner]
            remaining.remove(winner)
        losses.append(total / 3)
    return float(np.mean(losses))


def evaluate_model(model, races):
    return [record(r, *model.predict(r['features'])) for r in races]


def paired_intervals(races, before, after):
    groups = collections.defaultdict(list)
    keys = ('winner_hit', 'top3_recall', 'top3_all_hit', 'ordered_all_hit', 'mean_rank_log_loss')
    for r, a, b in zip(races, before, after):
        groups[r['rows'][0]['race_date']].append([b[k] - a[k] for k in keys])
    totals = np.array([np.sum(v, axis=0) for v in groups.values()])
    counts = np.array([len(v) for v in groups.values()])
    rng = np.random.default_rng(48)
    draws = rng.integers(len(counts), size=(1000, len(counts)))
    values = totals[draws].sum(axis=1) / counts[draws].sum(axis=1)[:, None]
    return {k:np.quantile(values[:, i], [.025, .975]).tolist() for i, k in enumerate(keys)}


def run(db, output, lag):
    dest = Path(output); dest.mkdir(parents=True, exist_ok=True)
    if (dest / f'selection_lag{lag}.json').exists():
        raise ValueError('fresh experiment output required')
    before_hash = sha(db)
    history, fields, source_audit = load_archive(db, lag, allow_unlinked_fields=True)
    print(canonical(dict(stage='features', lag=lag, fields=len(fields))), flush=True)
    original = pack(history_index(history), fields)
    rejected = []; races = []
    for r in original:
        try:
            top3_labels(r)
        except ValueError:
            rejected.append(r['race_id']); continue
        races.append(augment(r))
    train = eligible_split(races, 2023)
    train_end = max(r['result_available_at'] for r in train)
    calibration = [r for r in eligible_split(races, 2024, train_end) if int(r['rows'][0]['race_date'][5:7]) <= 6]
    calibration_end = max(r['result_available_at'] for r in calibration)
    selection = [r for r in eligible_split(races, 2024, calibration_end) if int(r['rows'][0]['race_date'][5:7]) > 6]
    grid = []; selected = None; best = None
    for family in PROTOCOL['families']:
        for reg in PROTOCOL['regularization']:
            name = f'{family}_reg{reg}'
            model = RankModel().fit(train, family=family, regularization=reg, iterations=PROTOCOL['iterations'])
            losses = {str(t):conditional_loss(model, calibration, t) for t in PROTOCOL['temperatures']}
            model.temperature = min(PROTOCOL['temperatures'], key=lambda t: (losses[str(t)], abs(t-1)))
            model.calibration_end = calibration_end
            metrics = aggregate(evaluate_model(model, selection))
            key = (-metrics['top3_recall'], -metrics['winner_hit'], metrics['mean_rank_log_loss'], name)
            grid.append(dict(name=name, family=family, regularization=reg, temperature=model.temperature,
                             calibration_conditional_loss=losses, selection_metrics=metrics))
            if best is None or key < best:
                best = key; selected = (model, name)
            print(canonical(dict(stage='candidate_selected_period', lag=lag, name=name, metrics=metrics)), flush=True)
    model, name = selected
    model_path = dest / f'model_lag{lag}.json'
    model_hash = save(model_path, model.to_dict())
    frozen = dict(protocol=PROTOCOL, input_db_sha256=before_hash, lag_days=lag,
                  train_races=len(train), calibration_races=len(calibration), selection_races=len(selection),
                  train_end=train_end, calibration_end=calibration_end,
                  selection_end=max(r['result_available_at'] for r in selection), selected=name, grid=grid,
                  model_sha256=model_hash, excluded_top_three_ties=rejected,
                  source_sha256={p:sha(ROOT / p) for p in ('ranking_model.py', 'ranking_research.py', 'RANKING_PROTOCOL.json')})
    frozen_hash = save(dest / f'selection_lag{lag}.json', frozen)
    print(canonical(dict(stage='selection_frozen_before_evaluation', lag=lag, selected=name, sha256=frozen_hash)), flush=True)
    # Baseline uses the same legacy feature contract as the active service.
    baseline_data = json.loads((ROOT / 'deployment/active_model.json').read_text())
    baseline = HierarchicalModel.from_dict(baseline_data, allow_research=True)
    old_races = {r['race_id']:r for r in pack(previous_contract_index(history), fields, enriched=False)}
    restored = RankModel.from_dict(json.loads(model_path.read_text()))
    reports = {}; predictions = []; maximum_reload_error = 0.
    boundary = max(timestamp(frozen['selection_end']), timestamp(baseline.calibration_end or baseline.train_end)).isoformat()
    for year in PROTOCOL['exploratory_evaluation_years']:
        cohort = eligible_split(races, year, boundary)
        old_records = []; new_records = []
        for r in cohort:
            old = old_races[r['race_id']]
            p, q = joint_distribution(np.repeat(baseline.scores(old['features'])[None, :], 3, axis=0), baseline.temperature)
            before = record(r, p, q)
            p, q = restored.predict(r['features'])
            maximum_reload_error = max(maximum_reload_error, float(np.abs(p - model.predict(r['features'])[0]).max()))
            after = record(r, p, q)
            old_records.append(before); new_records.append(after)
            predictions.append(dict(race_id=r['race_id'], date=r['rows'][0]['race_date'],
                horse_numbers=[x['horse_number'] for x in r['rows']],
                feature_sha256=hashlib.sha256(canonical(r['features']).encode()).hexdigest(),
                baseline=before, candidate=after))
        reports[str(year)] = dict(baseline=aggregate(old_records), candidate=aggregate(new_records),
                paired_day_bootstrap_95pct_delta=paired_intervals(cohort, old_records, new_records),
                evaluation_role='already inspected exploratory retrospective; no forward claim')
        print(canonical(dict(stage='rank_evaluation', lag=lag, year=year, report=reports[str(year)])), flush=True)
    prediction_hash = save(dest / f'predictions_lag{lag}.json.gz', predictions)
    report = dict(protocol_sha256=sha(ROOT / 'RANKING_PROTOCOL.json'), input_db_sha256=before_hash,
                  selection_sha256=frozen_hash, model_sha256=model_hash, predictions_sha256=prediction_hash,
                  selected=name, years=reports, maximum_reload_error=maximum_reload_error,
                  baseline_model_sha256=hashlib.sha256(canonical(baseline_data).encode()).hexdigest(),
                  source_eligible_races=len(original), rank_eligible_races=len(races), top_three_ties=len(rejected),
                  database_unchanged=sha(db) == before_hash, live_model_promoted=False, forward_races=0)
    save(dest / f'evaluation_lag{lag}.json', report)
    if maximum_reload_error != 0 or not report['database_unchanged']:
        raise ValueError('replay/database verification failed')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True); p.add_argument('--output', required=True)
    p.add_argument('--lag', required=True, type=int, choices=(2, 7))
    a = p.parse_args(); run(a.db, a.output, a.lag)
