"""Run one predeclared ROI95 experiment; all policies are retrospective only."""
import argparse
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from boosted_race import BoostedRaceModel
from completion_validation import pack, sha
from enriched_features import load_archive, history_index
from historical_replay import eligible_split
from result_odds import final_market_probabilities
from risk_replay import risk_report
from validation import canonical, metrics

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT/'ROI95_PROTOCOL.json').read_text())


def save(path, value):
    raw = canonical(value).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)
    return sha(path)


def decide(race, p, policy):
    if len(p) != len(race['rows']) or not np.isfinite(p).all() or min(p) < 0 or abs(sum(p)-1) > 1e-8:
        raise ValueError('full normalized probabilities required')
    cap = policy['odds_cap']; mode = policy['mode']; threshold = policy['threshold']
    if mode not in ('top_probability', 'maximum_ev') or not math.isfinite(threshold) or threshold < 0 or (cap is not None and (not math.isfinite(cap) or cap < 1)):
        raise ValueError('invalid policy')
    odds = [r['final_win_odds'] for r in race['rows']]
    if any(o is None or not math.isfinite(o) or o < 1 for o in odds):
        raise ValueError('complete final odds required')
    ix = [i for i,o in enumerate(odds) if cap is None or o <= cap]
    key = lambda i: (-(p[i] if mode == 'top_probability' else p[i]*odds[i]), int(race['rows'][i]['horse_number']))
    pick = min(ix, key=key) if ix else None
    if pick is not None and p[pick]*odds[pick] < threshold:
        pick = None
    hit = pick is not None and pick == race['winner_index']
    payout = race['rows'][0]['win_payout_100'] if hit else 0
    return dict(fully_settled=payout is not None, stake_yen=100 if pick is not None else 0,
                payout_yen=payout, horse_number=race['rows'][pick]['horse_number'] if pick is not None else None,
                selected_odds=odds[pick] if pick is not None else None)


def interval(races, settlements):
    days = collections.defaultdict(lambda: [0,0])
    for r,s in zip(races, settlements):
        if not s['fully_settled']:
            continue
        d = days[r['rows'][0]['race_date']]
        d[0] += s['stake_yen']; d[1] += s['payout_yen']
    if not days or not sum(v[0] for v in days.values()):
        return None
    a = np.asarray(list(days.values()), float)
    rng = np.random.default_rng(PROTOCOL['seed'])
    draws = a[rng.integers(0,len(a),size=(PROTOCOL['bootstrap_draws'], len(a)))].sum(axis=1)
    draws = draws[draws[:,0]>0]
    return np.quantile(100*draws[:,1]/draws[:,0], [.025,.975]).tolist()


def summarize(races, predictions, policy):
    decisions = [decide(r,p,policy) for r,p in zip(races,predictions)]
    report = risk_report(decisions)
    report['day_bootstrap_95pct_return_interval'] = interval(races,decisions)
    halves = []
    for first in (True,False):
        ix = [i for i,r in enumerate(races) if (int(r['rows'][0]['race_date'][5:7]) <= 6) == first]
        halves.append(risk_report([decisions[i] for i in ix]))
    report['half_years'] = halves
    report['scheduled_races'] = len(races)
    return report, decisions


def select_policy(races, families):
    if not races or any(r['rows'][0]['race_date'][:4] != '2024' for r in races):
        raise ValueError('policy selection uses 2024 only')
    grid = []
    for family,predictions in families.items():
        for mode in PROTOCOL['policy_modes']:
            for cap in PROTOCOL['odds_caps']:
                for threshold in ([0.] if mode == 'top_probability' else PROTOCOL['ev_thresholds']):
                    policy = dict(family=family,mode=mode,odds_cap=cap,threshold=threshold)
                    report,_ = summarize(races,predictions,policy)
                    eligible = (report['bet_races'] >= PROTOCOL['minimum_bets'] and report['pending_races'] == 0
                                and all(h['bet_races'] >= PROTOCOL['minimum_bets_per_half'] for h in report['half_years']))
                    grid.append(dict(policy=policy,metrics=report,eligible=eligible))
    eligible = [g for g in grid if g['eligible']]
    best = max(eligible,key=lambda g:(min(h['return_pct'] for h in g['metrics']['half_years']),
                g['metrics']['day_bootstrap_95pct_return_interval'][0],g['metrics']['return_pct'])) if eligible else None
    return dict(selected=best,grid=grid,live_eligible=False)


def run(db, output, lag):
    dest = Path(output); dest.mkdir(parents=True,exist_ok=True)
    history,fields,audit = load_archive(db,lag,allow_unlinked_fields=True)
    print(canonical(dict(stage='packing',lag=lag,fields=len(fields))),flush=True)
    races = pack(history_index(history),fields)
    races = [r for r in races if all(x.get('final_win_odds') is not None for x in r['rows'])]
    train = eligible_split(races,2023)
    # A common boundary independent of candidate choice.
    train_end = max(r['result_available_at'] for r in train)
    cal = eligible_split(races,2024,train_end)
    models = {}; model_grid = []; predictions = {}
    for settings in PROTOCOL['models']:
        m = BoostedRaceModel().fit(train,**settings, learning_rate=PROTOCOL['learning_rate'],
                minimum_leaf=PROTOCOL['minimum_leaf'], leaf_regularization=PROTOCOL['leaf_regularization'],bins=PROTOCOL['bins'])
        score = m.calibrate(cal,PROTOCOL['temperatures'])
        item = dict(**settings,calibration=score)
        model_grid.append(item)
        family = settings['family']
        if family not in models or score['selected']['log_loss'] < models[family][1]['calibration']['selected']['log_loss']:
            models[family] = (m,item)
        print(canonical(dict(stage='model_calibrated',lag=lag,**item)),flush=True)
    models = {f:m[0] for f,m in models.items()}
    for f,m in models.items():
        predictions[f] = m.predict(cal,enforce_time=False)
    policy_selection = select_policy(cal,predictions)
    frozen = dict(protocol=PROTOCOL,lag_days=lag,input_db_sha256=sha(db),model_grid=model_grid,
            train_races=len(train),calibration_races=len(cal),policy_selection=policy_selection,
            model_artifacts={f:dict(path=f'model_{f}_lag{lag}.json',sha256=save(dest/f'model_{f}_lag{lag}.json',m.to_dict())) for f,m in models.items()},
            source_sha256={n:sha(ROOT/n) for n in ('boosted_race.py','roi95_research.py','ROI95_PROTOCOL.json','enriched_features.py','features.py')})
    save(dest/f'selection_lag{lag}.json',frozen)
    save(dest/f'calibration_predictions_lag{lag}.json.gz',[
        dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=[x['horse_number'] for x in r['rows']],
             final_odds=[x['final_win_odds'] for x in r['rows']],winner_index=r['winner_index'],
             win_payout_100=r['rows'][0]['win_payout_100'],predictions={f:predictions[f][i] for f in predictions}) for i,r in enumerate(cal)])
    print(canonical(dict(stage='selection_frozen_before_2025',lag=lag,selection_sha256=sha(dest/f'selection_lag{lag}.json'),selected=policy_selection['selected'])),flush=True)
    test = eligible_split(races,2025,max(m.calibration_end for m in models.values()))
    ps = {f:m.predict(test) for f,m in models.items()}
    report = dict(lag_days=lag,input_db_sha256=sha(db),selection_sha256=sha(dest/f'selection_lag{lag}.json'),
                  evaluation_role='2025 exploratory historical final-odds; not unseen, forward or executable',
                  live_eligible=False,live_model_promotion_approved=False,target_return_pct=95,races=len(test),families={})
    fixed_ids = {r['race_id'] for r in json.loads((ROOT/'reports'/'completion'/f'final_market_decisions_lag{lag}.json').read_text())}
    fixed_ix = [i for i,r in enumerate(test) if r['race_id'] in fixed_ids]
    for f,pred in ps.items():
        scores = [metrics(p,r['winner_index']) for p,r in zip(pred,test)]
        reference = dict(mode='maximum_ev',odds_cap=None,threshold=1.05)
        report['families'][f] = dict(probability={k:float(np.mean([s[k] for s in scores])) for k in scores[0]},
                full_same_ev=summarize(test,pred,reference)[0],fixed_345_same_ev=summarize([test[i] for i in fixed_ix],[pred[i] for i in fixed_ix],reference)[0])
    selected = policy_selection['selected']
    if selected:
        policy = selected['policy']; f = policy['family']
        selected_report, decisions = summarize(test,ps[f],policy)
        report['selected_policy'] = dict(policy=policy,calibration_metrics=selected['metrics'],exploratory_metrics=selected_report,
                observed_target_met=bool(selected_report['bet_races'] >= 300 and selected_report['return_pct'] >= 95),
                confidence_lower_target_met=bool(selected_report['day_bootstrap_95pct_return_interval'] and selected_report['day_bootstrap_95pct_return_interval'][0] >= 95))
    else:
        decisions = [None]*len(test); report['selected_policy'] = None
    market = [final_market_probabilities([x['final_win_odds'] for x in r['rows']]) for r in test]
    report['market_log_loss'] = float(np.mean([-math.log(p[r['winner_index']]) for p,r in zip(market,test)]))
    save(dest/f'predictions_lag{lag}.json.gz',[
        dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=[x['horse_number'] for x in r['rows']],
             final_odds=[x['final_win_odds'] for x in r['rows']],winner_index=r['winner_index'],
             win_payout_100=r['rows'][0]['win_payout_100'],predictions={f:ps[f][i] for f in ps},decision=decisions[i]) for i,r in enumerate(test)])
    save(dest/f'evaluation_lag{lag}.json',report)
    print(canonical(dict(stage='evaluation_complete',lag=lag,selected=report['selected_policy'])),flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db',required=True); ap.add_argument('--output',required=True)
    ap.add_argument('--lag',type=int,choices=(2,7),required=True)
    args = ap.parse_args(); run(args.db,args.output,args.lag)
