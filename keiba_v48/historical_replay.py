"""Exploratory 2023/2024/2025 replay with explicit publication-time assumptions.

Official source identities and result labels are real. Historical availability
is unverified: the chosen calendar-day lag is a research assumption, never a
replacement for the strict production publication timestamp. No pre-off odds
are synthesized; the fixed 100-yen top-choice rule does not consume any odds.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sqlite3

from features import HistoryIndex, timestamp
from fitted_model import HierarchicalModel
from improvements import training_races
from validation import canonical, equity_report, metrics, paired_report
from result_odds import summarize_final_odds

JST = dt.timezone(dt.timedelta(hours=9))


def assumed_availability(date, lag_days):
    if not isinstance(lag_days, int) or lag_days < 2:
        raise ValueError('research availability requires at least two calendar days')
    return dt.datetime.combine(dt.date.fromisoformat(date) + dt.timedelta(days=lag_days),
                               dt.time(), JST).isoformat()


def load_rows(db_path, lag_days=2, allow_missing_jockey=False):
    db = sqlite3.connect('file:' + str(Path(db_path).resolve()) + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    groups = collections.defaultdict(list)
    history = []
    excluded = collections.Counter()
    for r in db.execute('''SELECT r.race_id,r.race_date,r.off_timestamp,r.track,r.surface,
        r.distance_m,r.going,r.expected_runners,r.status,r.metadata_json,r.document_url,
        h.horse_number,h.horse_id,h.jockey_id,h.payload_json
        FROM annual_report_races r JOIN annual_report_runners h USING(race_id)
        ORDER BY r.race_date,r.off_timestamp,r.race_id,h.horse_number'''):
        payload = json.loads(r['payload_json'])
        if r['status'] != 'validated_result' or not r['horse_id'] or (not r['jockey_id'] and not allow_missing_jockey):
            excluded['review_or_unlinked_runner_rows'] += 1
            continue
        if not r['off_timestamp'] or not payload.get('finish_position'):
            excluded['missing_time_or_rank_runner_rows'] += 1
            continue
        row = dict(race_id=r['race_id'], horse_number=str(r['horse_number']),
                   horse_id=r['horse_id'], jockey_id=r['jockey_id'],
                   off_timestamp=r['off_timestamp'], race_date=r['race_date'],
                   track=r['track'], surface=r['surface'], distance_m=r['distance_m'],
                   going=r['going'], field_size=r['expected_runners'],
                   finish_position=payload['finish_position'], source_url=r['document_url'],
                   result_available_at=assumed_availability(r['race_date'], lag_days),
                   availability_basis='assumed_calendar_day_lag_for_research_only',
                   expected_runners=r['expected_runners'], field_complete='yes',
                   pre_off_odds=None, odds_timestamp=None,
                   final_win_odds=payload.get('final_win_odds'),
                   win_payout_100=json.loads(r['metadata_json']).get('win_payout_100'))
        history.append(row)
        # These snapshots were observed after the event. Do not fabricate an
        # as-of time for current going, carried weight, body weight or odds.
        groups[r['race_id']].append({**row, 'going': None, 'carried_weight': None})
    races = []
    for rid, rows in groups.items():
        n = rows[0]['expected_runners']
        if len(rows) != n or n < 3 or sorted(r['finish_position'] for r in rows) != list(range(1, n + 1)):
            excluded['incomplete_or_invalid_races'] += 1
            continue
        if len({r['horse_id'] for r in rows}) != n:
            excluded['duplicate_identity_races'] += 1
            continue
        races.extend(rows)
    db.close()
    return history, races, dict(excluded)


def select_index(probabilities, rows):
    # Deterministic tie handling uses the printed horse number, never row rank.
    return min(range(len(rows)), key=lambda i: (-float(probabilities[i]), int(rows[i]['horse_number'])))


def prepare(history, rows, allow_missing_jockey=False):
    index = HistoryIndex(history, allow_assumed_availability=True, allow_missing_jockey=allow_missing_jockey)
    races = training_races(index, rows)
    fields = collections.defaultdict(list)
    for row in rows:
        fields[row['race_id']].append(row)
    for race in races:
        race['rows'] = fields[race['race_id']]
    return races


def eligible_split(races, year, after=None):
    return [r for r in races if timestamp(r['off_timestamp']).year == year and
            (not after or all(timestamp(f['cutoff_timestamp']) > timestamp(after) for f in r['features']))]


def evaluate_lag(db_path, lag_days=2, iterations=400, allow_missing_jockey=False):
    history, rows, excluded = load_rows(db_path, lag_days, allow_missing_jockey)
    races = prepare(history, rows, allow_missing_jockey)
    train = eligible_split(races, 2023)
    if not train:
        raise ValueError('no eligible training races')
    model = HierarchicalModel().fit(train, iterations=iterations)
    calibration = eligible_split(races, 2024, model.train_end)
    calibration_report = model.calibrate(calibration)
    test = eligible_split(races, 2025, model.calibration_end)
    if not test:
        raise ValueError('no eligible evaluation races')
    records, predictions, settlements, prior_records, odds_records = [], [], [], [], []
    day_groups = collections.defaultdict(list)
    for race in test:
        rs, fs = race['rows'], race['features']
        p = model.predict(fs).tolist()
        baseline = [1 / len(p)] * len(p)
        chosen = select_index(p, rs)
        record = dict(race_id=race['race_id'], baseline=baseline, candidate=p,
                      winner_index=race['winner_index'])
        records.append(record)
        odds_records.append(dict(race_id=race['race_id'],rows=rs,probabilities=p,
                                 winner_index=race['winner_index'],win_payout_100=rs[0]['win_payout_100']))
        prior = [f['values'][0] for f in fs]
        prior = [v / sum(prior) for v in prior]
        prior_records.append({**record, 'baseline': prior})
        payout = rs[0]['win_payout_100'] if chosen == race['winner_index'] else 0
        settlements.append(dict(fully_settled=payout is not None, stake_yen=100,
                                payout_yen=payout))
        day_groups[rs[0]['race_date']].append((metrics(p, race['winner_index'])['log_loss'] -
                                             metrics(baseline, race['winner_index'])['log_loss'], payout))
        predictions.append(dict(race_id=race['race_id'], off_timestamp=race['off_timestamp'],
                                horse_numbers=[r['horse_number'] for r in rs],
                                probabilities=p, selected_horse_number=rs[chosen]['horse_number'],
                                winner_horse_number=rs[race['winner_index']]['horse_number'],
                                payout_per_100=payout,
                                history_starts=[f['history_starts'] for f in fs]))
    report = paired_report(records)
    final_odds_report, final_odds_details = summarize_final_odds(odds_records)
    report['final_odds_reference'] = final_odds_report
    for row, judged in zip(predictions, final_odds_details):
        row['final_odds_judgement'] = judged
    prior_comparison = paired_report(prior_records)
    days = list(day_groups.values())
    rng = random.Random(48)
    deltas, returns = [], []
    for _ in range(500):
        sample = [row for _ in days for row in rng.choice(days)]
        deltas.append(sum(v[0] for v in sample) / len(sample))
        paid = [v[1] for v in sample if v[1] is not None]
        if len(paid) == len(sample):
            returns.append(sum(paid) / len(sample))  # 100 yen stake: numeric value is return %.
    def interval(values):
        ordered = sorted(values)
        return [ordered[int(.025 * len(ordered))], ordered[min(len(ordered)-1, int(.975 * len(ordered)))]] if ordered else None
    # The shared metric uses first-index tie resolution; fields are ordered by
    # horse number, equivalent to select_index, independently of finishing ranks.
    report.update(publication_lag_days=lag_days, training_races=len(train),
                  calibration_races=len(calibration), evaluation_races=len(test),
                  history_rows=len(history), reconstructed_field_rows=len(rows), exclusions=excluded,
                  missing_jockey_policy='neutral_prior' if allow_missing_jockey else 'exclude_incomplete_field',
                  missing_jockey_evaluation_rows=sum(f['jockey_identity_missing'] for r in test for f in r['features']),
                  calibration=calibration_report,
                  comparison_with_shrunk_prior_form={k: prior_comparison[k] for k in
                      ('baseline', 'candidate', 'log_loss_delta', 'race_bootstrap_95pct_delta')},
                  evaluation_days=len(days), day_cluster_95pct_log_loss_delta=interval(deltas),
                  day_cluster_95pct_fixed_top1_return_pct=interval(returns),
                  fixed_top1_100yen=equity_report(settlements, 100000),
                  test_date_range=[min(r['off_timestamp'] for r in test), max(r['off_timestamp'] for r in test)],
                  feature_history_coverage=sum(f['history_starts'] > 0 for r in test for f in r['features']) /
                      sum(len(r['features']) for r in test),
                  production_eligible=False,
                  evaluated_races_by_month=dict(collections.Counter(r['off_timestamp'][:7] for r in test)),
                  evaluated_races_by_course=dict(collections.Counter(r['features'][0]['group'] for r in test)),
                  evaluation_role='exploratory historical reconstruction with assumed publication lag',
                  comparison='uniform same-field probabilities; no timestamped market baseline',
                  bet_rule='fixed 100-yen single win bet on highest probability; lowest horse number on ties',
                  limitations=[
                      'historical publication times and pre-off field snapshots are not verified',
                      'publication lag is a declared assumption; not an observed historical timestamp',
                      'identity coverage is selected by retrieved source pages, not the entire JRA population',
                      'current going and carried weight omitted because pre-off observation times are absent',
                      'EV-based win/wide/trio strategy and forward live performance remain untested',
                      'payouts are official post-race settlement labels, never probability model inputs',
                  ])
    return report, predictions, {**model.to_dict(), 'research_only': True,
                                'allow_missing_jockey': allow_missing_jockey,
                                'publication_lag_days': lag_days,
                                'availability_basis': 'assumed_calendar_day_lag_for_research_only'}


def run(db_path, output, lags=(2, 7), iterations=400, allow_missing_jockey=False):
    dest = Path(output); dest.mkdir(parents=True, exist_ok=True)
    reports = []
    with open(db_path, 'rb') as stream:
        db_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    for lag in lags:
        report, predictions, model = evaluate_lag(db_path, lag, iterations, allow_missing_jockey)
        report['input_db_sha256'] = db_sha256
        report['model_artifact_sha256'] = hashlib.sha256(canonical(model).encode()).hexdigest()
        report['prediction_rows_sha256'] = hashlib.sha256(canonical(predictions).encode()).hexdigest()
        report['optimizer_iterations'] = iterations
        report['source_code_sha256'] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('historical_replay.py', 'features.py', 'fitted_model.py', 'improvements.py', 'validation.py', 'result_odds.py')}
        (dest / f'replay_lag{lag}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (dest / f'predictions_lag{lag}.json').write_text(canonical(predictions), encoding='utf-8')
        (dest / f'model_research_lag{lag}.json').write_text(canonical(model), encoding='utf-8')
        reports.append(report)
        print(json.dumps({'lag_days': lag, 'train': report['training_races'], 'calibrate': report['calibration_races'],
                          'test': report['evaluation_races'], 'candidate': report['candidate'],
                          'fixed_top1_100yen': report['fixed_top1_100yen']}, ensure_ascii=False), flush=True)
    return reports


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True); p.add_argument('--output', required=True)
    p.add_argument('--lags', type=int, nargs='+', default=[2, 7])
    p.add_argument('--iterations', type=int, default=400)
    p.add_argument('--allow-missing-jockey', action='store_true')
    a = p.parse_args()
    run(a.db, a.output, a.lags, a.iterations, a.allow_missing_jockey)
