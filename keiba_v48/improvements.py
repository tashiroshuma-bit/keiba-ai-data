"""v4.8 executable workflow. See IMPROVEMENTS.md for input contracts and limits."""
import argparse
import collections
import csv
import json
from pathlib import Path
from features import IdentityMap, HistoryIndex, integrate_histories, build_features, timestamp
from fitted_model import HierarchicalModel
from model import market_probs
from strategy import validate_field, scenario_distribution, opportunities, allocate
from validation import Ledger, paired_report, metrics, canonical


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def predict(model, history, rows, identities=None, quotes=(), bankroll=100000,
            race_budget=5000, open_exposure=0, scenario_weights=None):
    cutoff = validate_field(rows, require_odds=False)
    features = build_features(history, rows, identities)
    if len({f['horse_id'] for f in features}) != len(features):
        raise ValueError('duplicate canonical horse ID')
    rank, pairs, triples, scenarios = scenario_distribution(model, features, scenario_weights)
    # Partial or stale all-runner win quotes block all virtual purchases, not predictions.
    reasons = []
    try:
        validate_field(rows)
    except (ValueError, KeyError) as exc:
        reasons.append(str(exc))
    if not model.calibration_end:
        reasons.append('model has no later-period calibration')
    candidates = opportunities(rows, features, rank, pairs, triples, scenarios, cutoff, quotes) if not reasons else []
    allocation = allocate(candidates, bankroll, race_budget, open_exposure)
    allocation['gate_reasons'] = reasons
    runners = []
    for i, (r, f) in enumerate(zip(rows, features)):
        ev = next((c['expected_return'] for c in candidates if c['kind'] == 'win' and c['horse_numbers'] == [str(r['horse_number'])]), None)
        bet_reasons = [x['reason'] for x in allocation['rejected'] if str(r['horse_number']) in x['horse_numbers']]
        selected = any(str(r['horse_number']) in x['horse_numbers'] for x in allocation['bets'])
        runners.append({'horse_number': str(r['horse_number']), 'horse_id': f['horse_id'],
                        'p_first': rank[i][0], 'p_second': rank[i][1], 'p_third': rank[i][2],
                        'p_top3': sum(rank[i]), 'win_expected_return': ev,
                        'going_suitability': f['values'][4] if f['current_going_known'] and f['going_samples'] else None,
                        'third_place_probability': rank[i][2],
                        'history_starts': f['history_starts'], 'course_samples': f['course_samples'],
                        'selected': selected, 'exclusion_reasons': [] if selected else (reasons or bet_reasons or ['no qualifying quoted combination'])})
    axes = {}
    for axis, field in [('win', 'p_first'), ('expected_value', 'win_expected_return'), ('going', 'going_suitability'), ('third_place', 'third_place_probability')]:
        axes[axis] = [r['horse_number'] for r in sorted((r for r in runners if r[field] is not None), key=lambda r: r[field], reverse=True)]
    return {'version': '4.8', 'race_id': rows[0]['race_id'], 'off_timestamp': rows[0]['off_timestamp'],
            'cutoff_timestamp': cutoff.isoformat(), 'runners': runners, 'axes': axes,
            'scenarios': scenarios, 'scenario_weights': scenario_weights or {'slow': 1/3, 'average': 1/3, 'high': 1/3},
            'scenario_status': 'fixed sensitivity hypotheses; not learned pace probabilities',
            'allocation': allocation, 'risk_settings': {'bankroll': bankroll, 'race_budget': race_budget, 'open_exposure': open_exposure, 'race_fraction': .02, 'exposure_fraction': .1, 'unit_yen': 100}, 'inputs': {'runners': rows, 'features': features, 'quotes': list(quotes)}}


def training_races(history, runners, identities=None):
    history = history if isinstance(history, HistoryIndex) else HistoryIndex(history, identities)
    groups = collections.defaultdict(list)
    for r in runners:
        groups[r['race_id']].append(r)
    output = []
    for race_id, rows in groups.items():
        validate_field(rows, require_odds=False)
        if not all(r.get('result_available_at') for r in rows):
            raise ValueError('training requires result_available_at')
        ranks = [int(r['finish_position']) for r in rows]
        if sorted(ranks) != list(range(1, len(rows) + 1)):
            raise ValueError('training requires complete unique finishing ranks')
        if len({timestamp(r['result_available_at']) for r in rows}) != 1:
            raise ValueError('inconsistent result publication')
        output.append({'race_id': race_id, 'off_timestamp': rows[0]['off_timestamp'],
                       'result_available_at': rows[0]['result_available_at'], 'winner_index': ranks.index(1),
                       'features': build_features(history, rows, identities)})
    return sorted(output, key=lambda r: timestamp(r['off_timestamp']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('train', 'predict', 'evaluate'):
        c = sub.add_parser(command)
        c.add_argument('--history', nargs='+', required=True)
        c.add_argument('--runners', required=True)
        c.add_argument('--aliases')
        c.add_argument('--model', required=True)
        if command == 'train':
            c.add_argument('--train-year', type=int, default=2023)
            c.add_argument('--validation-year', type=int, default=2024)
        else:
            c.add_argument('--output', required=True)
        if command == 'predict':
            c.add_argument('--ledger', required=True)
            c.add_argument('--mode', choices=['forward', 'replay'], default='forward')
            c.add_argument('--quotes', help='JSON list of timestamped wide/trio quotes')
            c.add_argument('--bankroll', type=float, default=100000)
            c.add_argument('--race-budget', type=float, default=5000)
            c.add_argument('--open-exposure', type=float, default=0)
    s = sub.add_parser('settle')
    s.add_argument('--ledger', required=True); s.add_argument('--prediction-id', required=True)
    s.add_argument('--result', required=True)
    a = p.parse_args()
    if a.command == 'settle':
        print(canonical(Ledger(a.ledger).settle(a.prediction_id, json.loads(Path(a.result).read_text()))))
        return
    identities = IdentityMap(read_csv(a.aliases) if a.aliases else [])
    history = HistoryIndex(integrate_histories([read_csv(path) for path in a.history], identities))
    rows = read_csv(a.runners)
    if a.command == 'train':
        if a.train_year >= a.validation_year:
            raise ValueError('validation year must follow training')
        races = training_races(history, rows, identities)
        train = [r for r in races if timestamp(r['off_timestamp']).year == a.train_year]
        valid = [r for r in races if timestamp(r['off_timestamp']).year == a.validation_year]
        model = HierarchicalModel().fit(train)
        report = model.calibrate(valid)
        Path(a.model).write_text(canonical(model.to_dict()), encoding='utf-8')
        print(canonical(report))
        return
    model = HierarchicalModel.from_dict(json.loads(Path(a.model).read_text()))
    if a.command == 'predict':
        quotes = json.loads(Path(a.quotes).read_text()) if a.quotes else []
        prediction = predict(model, history, rows, identities, quotes, a.bankroll, a.race_budget, a.open_exposure)
        key = Ledger(a.ledger).freeze(prediction, model.to_dict(), a.mode)
        Path(a.output).write_text(canonical({'prediction_id': key, **prediction}), encoding='utf-8')
        print(key)
    else:
        records = []
        groups = collections.defaultdict(list)
        for r in rows:
            groups[r['race_id']].append(r)
        for race_id, rs in groups.items():
            validate_field(rs)
            ranks = [int(r['finish_position']) for r in rs]
            if sorted(ranks) != list(range(1, len(rs) + 1)):
                raise ValueError('invalid evaluation result')
            f = build_features(history, rs, identities)
            rank, _, _, _ = scenario_distribution(model, f)
            records.append({'race_id': race_id, 'baseline': market_probs([float(r['pre_off_odds']) for r in rs]).tolist(),
                            'candidate': [r[0] for r in rank], 'candidate_top3': [sum(r) for r in rank],
                            'observed_top3': [i for i, v in enumerate(ranks) if v <= 3], 'winner_index': ranks.index(1)})
        report = paired_report(records)
        Path(a.output).write_text(canonical(report), encoding='utf-8')
        print(canonical(report))


if __name__ == '__main__':
    main()
