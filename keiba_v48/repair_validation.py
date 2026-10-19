"""Expanded-cohort time-split validation after offline source repair.

Selections use 2024 only. Previously inspected 2025 is exploratory. Final
market models are post-race research tools and cannot replace live forecasts.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import random
import numpy as np

from completion_validation import pack,pace_probabilities,settlement,final_odds_stress,day_interval,sha
from enriched_features import load_archive,history_index,previous_contract_index
from features import FEATURE_NAMES,ENRICHED_FEATURE_NAMES,finish,timestamp
from fitted_model import HierarchicalModel,softmax
from historical_replay import eligible_split
from market_residual import MarketResidualModel
from result_odds import summarize_final_odds,final_market_probabilities,judge_final_odds
from risk_replay import risk_report,capital_replay
from risk_policy import calibrate_policy,policy_decision
from validation import canonical,paired_report

PROTOCOL=json.loads(Path(__file__).with_name('RESEARCH_REPAIR_PROTOCOL.json').read_text())


def mask_style(races):
    result=[]
    for r in races:
        fs=[]
        for f in r['features']:
            v=list(f['values'])
            for i in (7,8,20,21):v[i]=0
            fs.append({**f,'values':v,'front_rate':.5,'style_observed':False})
        result.append({**r,'features':fs})
    return result


def structural_tune(enriched,original):
    grid=[];best=None;best_loss=float('inf')
    for family in PROTOCOL['structural_families']:
        races=original if family=='original13' else mask_style(enriched) if family=='enriched23_without_style' else enriched
        names=FEATURE_NAMES if family=='original13' else ENRICHED_FEATURE_NAMES
        train=eligible_split(races,2023)
        for reg in PROTOCOL['regularization']:
            m=HierarchicalModel().fit(train,regularization=reg,iterations=PROTOCOL['iterations'],feature_names=names)
            cal=eligible_split(races,2024,m.train_end);score=m.calibrate(cal,PROTOCOL['temperature'])
            decision=dict(family=family,regularization=reg,**score);grid.append(decision)
            if score['after_log_loss']<best_loss:
                best_loss=score['after_log_loss'];best=(m,decision,races)
        print(json.dumps(dict(stage='structural_calibration',family=family,decisions=grid[-3:])),flush=True)
    return *best,grid


def market_tune(enriched):
    available=[r for r in enriched if all(x.get('final_win_odds') is not None for x in r['rows'])]
    train=eligible_split(available,2023);best=None;best_loss=float('inf');grid=[]
    for reg in PROTOCOL['market_residual_regularization']:
        m=MarketResidualModel().fit(train,regularization=reg,iterations=PROTOCOL['iterations'])
        cal=eligible_split(available,2024,m.train_end)
        score=m.calibrate(cal,PROTOCOL['market_residual_calibration_scale'],PROTOCOL['market_power'])
        decision=dict(regularization=reg,**score);grid.append(decision)
        if score['choice']['log_loss']<best_loss:
            best_loss=score['choice']['log_loss'];best=(m,decision,available)
        print(json.dumps(dict(stage='market_calibration',regularization=reg,choice=score['choice'],calibration_races=len(cal))),flush=True)
    return *best,grid


def ev_settlement(rows,p,cap=None):
    eligible=[i for i,r in enumerate(rows) if cap is None or r['final_win_odds']<=cap]
    order=sorted(eligible,key=lambda i:(-p[i]*rows[i]['final_win_odds'],int(rows[i]['horse_number'])))
    pick=order[0] if order and p[order[0]]*rows[order[0]]['final_win_odds']>=1.05 else None
    hit=pick is not None and finish(rows[pick])==1
    payout=rows[0]['win_payout_100'] if hit else 0
    return dict(fully_settled=not hit or payout is not None,stake_yen=100 if pick is not None else 0,payout_yen=payout,
                horse_number=rows[pick]['horse_number'] if pick is not None else None,selected_odds=rows[pick]['final_win_odds'] if pick is not None else None,
                expected_return=p[pick]*rows[pick]['final_win_odds'] if pick is not None else None)


def paired_profit_interval(records):
    days=collections.defaultdict(list)
    for r in records:
        if not r['previous']['fully_settled'] or not r['candidate']['fully_settled']:continue
        days[r['date']].append((r['candidate']['payout_yen']-r['candidate']['stake_yen'])-(r['previous']['payout_yen']-r['previous']['stake_yen']))
    values=list(days.values());rng=random.Random(48);samples=[]
    for _ in range(500):
        x=[v for _ in values for v in rng.choice(values)];samples.append(sum(x)/len(x))
    samples.sort();return [samples[12],samples[487]] if samples else None


def comparison(rows,baseline,candidate):
    paired=[];bs=[];cs=[];profits=[]
    for r,p,q in zip(rows,baseline,candidate):
        paired.append(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],baseline=list(p),candidate=list(q),winner_index=r['winner_index']))
        b=ev_settlement(r['rows'],p);c=ev_settlement(r['rows'],q);bs.append(b);cs.append(c);profits.append(dict(date=r['rows'][0]['race_date'],previous=b,candidate=c))
    report=paired_report(paired)
    report.update(day_cluster_95pct_log_loss_delta=day_interval(paired),previous_EV=risk_report(bs),candidate_EV=risk_report(cs),
                  paired_day_95pct_profit_delta_yen_per_race=paired_profit_interval(profits),
                  evaluation_role='exploratory historical final-odds comparison; not live or unseen holdout')
    for name,st in (('previous_EV',bs),('candidate_EV',cs)):
        known=[s for s in st if s['fully_settled']]
        report[name]['net_profit_yen']=sum(s['payout_yen']-s['stake_yen'] for s in known)
        report[name]['profit_yen_per_scheduled_race']=report[name]['net_profit_yen']/len(rows)
    return report


def evaluate(db,output,lag):
    dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
    h,fields,audit=load_archive(db,lag,allow_unlinked_fields=True)
    print(json.dumps(dict(stage='expanded_cohort',lag=lag,**audit)),flush=True)
    enriched=pack(history_index(h),fields);original=pack(previous_contract_index(h),fields,False)
    sm,sd,sr,sg=structural_tune(enriched,original)
    mm,md,mr,mg=market_tune(enriched)
    policy_cal=[r for r in eligible_split(sr,2024,sm.train_end) if all(x.get('final_win_odds') is not None for x in r['rows'])]
    policy=calibrate_policy(policy_cal,[softmax(sm.scores(r['features']),sm.temperature).tolist() for r in policy_cal],PROTOCOL['risk_policy'])
    (dest/f'risk_policy_lag{lag}.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
    # All selections are fixed before reading previously saved 2025 predictions.
    structural_art={**sm.to_dict(),'research_only':True,'model_family':sd['family'],'allow_missing_jockey':True,'publication_lag_days':lag,'availability_basis':'assumed_calendar_day_lag_for_research_only','unlinked_policy':'isolated_source_row','live_eligible':False}
    market_art={**mm.to_dict(),'publication_lag_days':lag}
    (dest/f'structural_model_lag{lag}.json').write_text(canonical(structural_art));(dest/f'market_model_lag{lag}.json').write_text(canonical(market_art))
    print(json.dumps(dict(stage='selections_frozen_before_evaluation',lag=lag,structural=sd,market=md['choice'])),flush=True)
    stest=eligible_split(sr,2025,sm.calibration_end);stest_by={r['race_id']:r for r in stest}
    mtest=eligible_split(mr,2025,mm.calibration_end)
    frozen=json.loads(Path(__file__).with_name('deployment').joinpath('active_model.json').read_text());old_model=HierarchicalModel.from_dict(frozen,allow_research=True)
    original_by={r['race_id']:r for r in original};enriched_by={r['race_id']:r for r in enriched}
    selected_struct={r['race_id']:sm.predict(r['features']).tolist() for r in stest}
    market_predictions={r['race_id']:mm.probabilities(r).tolist() for r in mtest}
    baseline_predictions={r['race_id']:pace_probabilities(old_model,original_by[r['race_id']]['features'],(1/3,1/3,1/3),.15).tolist() for r in mtest}
    market_only=[final_market_probabilities([x['final_win_odds'] for x in r['rows']]) for r in mtest]
    new=[market_predictions[r['race_id']] for r in mtest];old=[baseline_predictions[r['race_id']] for r in mtest]
    struct=[selected_struct[r['race_id']] for r in mtest]
    report=dict(protocol=PROTOCOL,lag_days=lag,data_audit=audit,structural_tuning=sg,selected_structural=sd,market_tuning=mg,selected_market=md,
                full_market_cohort_vs_frozen_model=comparison(mtest,old,new),full_market_cohort_vs_market=comparison(mtest,market_only,new),
                full_market_cohort_vs_structural=comparison(mtest,struct,new),
                training_races=len(eligible_split(sr,2023)),calibration_races=len(eligible_split(sr,2024,sm.train_end)),test_races=len(stest),market_test_races=len(mtest),
                strict_publication_verified=False,live_eligible=False,forward_observed_races=0)
    previous_records=json.loads(Path(__file__).with_name('reports').joinpath('completion',f'paired_predictions_lag{lag}.json').read_text())
    matched=[];po=[];pc=[];ps=[];pn=[];changed=[]
    for p in previous_records:
        r=next((x for x in mtest if x['race_id']==p['race_id']),None)
        if r is None:continue
        ns=[x['horse_number'] for x in r['rows']]
        if set(ns)!=set(p['horse_numbers']):changed.append(p['race_id']);continue
        perm=[p['horse_numbers'].index(n) for n in ns]
        matched.append(r);po.append([p['previous'][i] for i in perm]);pc.append([p['candidate'][i] for i in perm]);ps.append(selected_struct[r['race_id']]);pn.append(market_predictions[r['race_id']])
    report['matched_prior_fields_vs_original']=comparison(matched,po,pn)
    report['matched_prior_fields_vs_rejected_candidate']=comparison(matched,pc,pn)
    report['matched_structural_vs_original']=comparison(matched,po,ps)
    original_EV=json.loads(Path(__file__).with_name('reports').joinpath('completion',f'final_market_decisions_lag{lag}.json').read_text())
    fixed_ids={r['race_id'] for r in original_EV};fixed_ix=[i for i,r in enumerate(matched) if r['race_id'] in fixed_ids]
    report['exact_original_EV_cohort_vs_original']=comparison([matched[i] for i in fixed_ix],[po[i] for i in fixed_ix],[pn[i] for i in fixed_ix])
    report['exact_original_EV_cohort_structural_vs_original']=comparison([matched[i] for i in fixed_ix],[po[i] for i in fixed_ix],[ps[i] for i in fixed_ix])
    report['changed_prior_fields']=changed
    report['risk_policy']=policy
    if policy['selected'] is not None:
        choice=policy['selected'];policy_p=[];policy_settlements=[]
        for r,p in zip(mtest,struct):
            st,prob=policy_decision(r,p,choice['structural_weight'],choice['odds_cap'],PROTOCOL['risk_policy']['threshold'])
            policy_p.append(prob);policy_settlements.append(st)
        report['risk_policy_full_settlement']=risk_report(policy_settlements)
        # comparison() uses the uncapped reference rule, so use the actual capped
        # decisions separately rather than presenting its ROI as the policy ROI.
        matched_policy=[];profit_records=[]
        for r,previous,structural in zip(matched,po,ps):
            st,_=policy_decision(r,structural,choice['structural_weight'],choice['odds_cap'],PROTOCOL['risk_policy']['threshold'])
            matched_policy.append(st);profit_records.append(dict(date=r['rows'][0]['race_date'],previous=ev_settlement(r['rows'],previous),candidate=st))
        report['risk_policy_matched_settlement']=risk_report(matched_policy)
        report['risk_policy_exact_original_EV_settlement']=risk_report([matched_policy[i] for i in fixed_ix])
        report['risk_policy_matched_profit_delta_95pct']=paired_profit_interval(profit_records)
        (dest/f'risk_policy_decisions_lag{lag}.json').write_text(canonical([dict(race_id=r['race_id'],**st) for r,st in zip(mtest,policy_settlements)]))
    for name,pred in (('structural',selected_struct),('market',market_predictions)):
        races=[r for r in stest if r['race_id'] in pred];settled={k:[] for k in ('win','wide','trio')};capital=[]
        for r in races:
            choices=settlement(r['rows'],pred[r['race_id']])
            for k,v in choices.items():settled[k].append(v)
            capital.append(dict(race_id=r['race_id'],cutoff_timestamp=r['features'][0]['cutoff_timestamp'],result_available_at=r['result_available_at'],markets=list(choices.values())))
        cap,decisions=capital_replay(capital)
        report[name+'_probability_rank_settlement']={k:risk_report(v) for k,v in settled.items()};report[name+'_virtual_capital']=cap
        (dest/f'capital_{name}_lag{lag}.json').write_text(canonical(decisions))
    ev_records=[dict(race_id=r['race_id'],rows=r['rows'],probabilities=market_predictions[r['race_id']],winner_index=r['winner_index'],win_payout_100=r['rows'][0]['win_payout_100']) for r in mtest]
    report['market_EV_stress']={str(cap):final_odds_stress(ev_records,cap) for cap in PROTOCOL['stress_caps']}
    report['segments']={}
    for field in ('course','class','month'):
        groups=collections.defaultdict(list)
        for i,r in enumerate(mtest):
            key=r['features'][0]['group'] if field=='course' else r['rows'][0].get('race_category','unknown') if field=='class' else r['rows'][0]['race_date'][:7]
            groups[key].append(i)
        report['segments'][field]={key:dict(races=len(ix),previous_EV=risk_report([ev_settlement(mtest[i]['rows'],old[i]) for i in ix]),candidate_EV=risk_report([ev_settlement(mtest[i]['rows'],new[i]) for i in ix])) for key,ix in groups.items()}
    predictions=[dict(race_id=r['race_id'],race_date=r['rows'][0]['race_date'],horse_numbers=[x['horse_number'] for x in r['rows']],
                      final_odds=[x['final_win_odds'] for x in r['rows']],previous_expanded=baseline_predictions[r['race_id']],structural=selected_struct[r['race_id']],market_residual=market_predictions[r['race_id']],winner_index=r['winner_index'],
                      market_EV_decision=ev_settlement(r['rows'],market_predictions[r['race_id']])) for r in mtest]
    report.update(input_db_sha256=sha(db),source_code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')},
                  protocol_sha256=hashlib.sha256(canonical(PROTOCOL).encode()).hexdigest(),prediction_sha256=hashlib.sha256(canonical(predictions).encode()).hexdigest(),
                  probability_sum_max_error=max(abs(sum(r['market_residual'])-1) for r in predictions))
    (dest/f'repair_comparison_lag{lag}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(dest/f'repair_predictions_lag{lag}.json').write_text(canonical(predictions))
    print(json.dumps(dict(lag=lag,matched=report['matched_prior_fields_vs_original'],full=report['full_market_cohort_vs_market']),ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--output',required=True);p.add_argument('--lags',type=int,nargs='+',default=[2,7]);a=p.parse_args()
    for lag in a.lags:evaluate(a.db,a.output,lag)
