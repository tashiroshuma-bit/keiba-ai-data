"""Calibrated post-race final-market judgement, never an executable quote.

Follow-up exploratory protocol: choose a structural/market mixture on 2024
NLL only. Preserve the initial structural-model comparison unchanged. A pure
market choice is allowed and usually implies no value pick after overround.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from completion_validation import pack,pace_probabilities,final_odds_stress,sha
from enriched_features import load_archive,history_index
from fitted_model import HierarchicalModel
from historical_replay import eligible_split
from features import timestamp
from result_odds import final_market_probabilities,judge_final_odds,summarize_final_odds
from validation import canonical,metrics

PROTOCOL=dict(version='final-market-judgement-1',selection_year=2024,exploratory_evaluation_year=2025,
              structural_weights=[0.,.1,.25,.5,.75,1.],selection_metric='calibration_log_loss',threshold=1.05,
              default_tie='smaller_structural_weight',odds_basis='post_race_final',actionable_before_off=False,
              motivation='structural models failed the requested final-odds return axis in the initial exploratory comparison',
              data_limit='partial official ID/source coverage after HTTP 403; not a random JRA population sample')


def mixed_probabilities(structural,odds,weight):
    if not math.isfinite(weight) or not 0<=weight<=1:raise ValueError('invalid structural weight')
    market=final_market_probabilities(odds)
    if len(structural)!=len(market) or any(not math.isfinite(p) or not 0<=p<=1 for p in structural) or abs(sum(structural)-1)>1e-8:raise ValueError('invalid structural probabilities')
    return [weight*p+(1-weight)*q for p,q in zip(structural,market)]


def fit_judgement(calibration_records,train_end):
    if not calibration_records:raise ValueError('no calibration records')
    if any(timestamp(r['off_timestamp']).year!=2024 or timestamp(r['cutoff_timestamp'])<=timestamp(train_end) for r in calibration_records):raise ValueError('judgement tuning uses 2024 after training only')
    grid=[]
    for weight in PROTOCOL['structural_weights']:
        losses=[metrics(mixed_probabilities(r['probabilities'],[x['final_win_odds'] for x in r['rows']],weight),r['winner_index'])['log_loss'] for r in calibration_records]
        grid.append(dict(structural_weight=weight,log_loss=sum(losses)/len(losses)))
    chosen=min(grid,key=lambda g:(g['log_loss'],g['structural_weight']))
    return dict(protocol=PROTOCOL,structural_weight=chosen['structural_weight'],calibration_races=len(calibration_records),grid=grid,
                calibration_end=max(r['result_available_at'] for r in calibration_records),research_only=True)


def judge(rows,probabilities,artifact):
    mixed=mixed_probabilities(probabilities,[r['final_win_odds'] for r in rows],artifact['structural_weight'])
    out=judge_final_odds(rows,mixed,PROTOCOL['threshold'])
    return dict(out,probabilities=mixed,structural_weight=artifact['structural_weight'],judgement_model='2024-calibrated structural-market mixture')


def run(db,comparison_dir,output):
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    (folder/'final_market_protocol.json').write_text(canonical(PROTOCOL))
    results=[]
    for lag in (2,7):
        model_path=Path(comparison_dir)/f'candidate_model_lag{lag}.json'
        artifact=json.loads(model_path.read_text());model=HierarchicalModel.from_dict(artifact,allow_research=True)
        history,fields,_=load_archive(db,lag);races=pack(history_index(history),fields)
        calibration=eligible_split(races,2024,model.train_end);test=eligible_split(races,2025,model.calibration_end)
        def records(rs):
            output=[]
            for r in rs:
                if not all(x.get('final_win_odds') is not None for x in r['rows']):continue
                output.append(dict(race_id=r['race_id'],rows=r['rows'],off_timestamp=r['off_timestamp'],cutoff_timestamp=r['features'][0]['cutoff_timestamp'],result_available_at=r['result_available_at'],
                                   probabilities=pace_probabilities(model,r['features'],[artifact['pace_weights'][name] for name in ('slow','average','high')],artifact['pace_strength']).tolist(),
                                   winner_index=r['winner_index'],win_payout_100=r['rows'][0]['win_payout_100']))
            return output
        cal=records(calibration);test_records=records(test)
        fitted=fit_judgement(cal,model.train_end)
        # Stored artifact is fixed before processing the exploratory evaluation records.
        (folder/f'final_market_judgement_lag{lag}.json').write_text(canonical(fitted))
        judged=[];details=[]
        for r in test_records:
            j=judge(r['rows'],r['probabilities'],fitted)
            judged.append({**r,'probabilities':j['probabilities']});details.append(dict(race_id=r['race_id'],**j))
        report,_=summarize_final_odds(judged)
        report.update(lag_days=lag,calibration=fitted,available_test_races=len(test_records),excluded_missing_final_odds_races=len(test)-len(test_records),
                      final_odds_stress={str(cap):final_odds_stress(judged,cap) for cap in (None,50,100)},input_db_sha256=sha(db),structural_model_file_sha256=sha(model_path),
                      source_sha256=sha(__file__),protocol_sha256=hashlib.sha256(canonical(PROTOCOL).encode()).hexdigest(),
                      evaluation_role='follow-up exploratory; 2025 initial outcome motivated this method; not an unseen holdout',
                      deployment_decision='do_not_generate_live_bets_or_claim_profit; preserve existing active structural model')
        (folder/f'final_market_report_lag{lag}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (folder/f'final_market_decisions_lag{lag}.json').write_text(canonical(details));results.append(report)
        print(json.dumps(dict(lag=lag,weight=fitted['structural_weight'],calibration_races=len(cal),test_races=len(test_records),settlement=report['post_race_value_settlement'])),flush=True)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--comparison-dir',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.db,a.comparison_dir,a.output)
