"""Frozen-protocol, paired v4.8 validation on source-confirmed fields.

2025 has been inspected in earlier project work: exploratory, not an unseen
holdout. Final odds/payouts enter evaluation only after predictions are fixed.
"""
import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import random
import numpy as np
from backtest_engine import podium
from enriched_features import load_archive,history_index,build_enriched,previous_contract_index
from features import build_features,timestamp,finish,ENRICHED_FEATURE_NAMES
from fitted_model import HierarchicalModel,softmax
from historical_replay import eligible_split,select_index
from result_odds import summarize_final_odds,judge_final_odds
from risk_replay import risk_report,capital_replay
from validation import canonical,metrics,paired_report
from exceptional_results import ticket_hit

PROTOCOL=json.loads(Path(__file__).with_name('COMPLETION_PROTOCOL.json').read_text())


def sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def pack(index,fields,enriched=True):
    grouped=collections.defaultdict(list)
    for r in fields:grouped[r['race_id']].append(r)
    result=[]
    for rid,rs in sorted(grouped.items()):
        rs=sorted(rs,key=lambda r:int(r['horse_number']))
        fs=build_enriched(index,rs) if enriched else build_features(index,rs)
        result.append(dict(race_id=rid,features=fs,rows=rs,winner_index=next(i for i,r in enumerate(rs) if finish(r)==1),
                           off_timestamp=rs[0]['off_timestamp'],result_available_at=max(r['result_available_at'] for r in rs)))
    return sorted(result,key=lambda r:(timestamp(r['off_timestamp']),r['race_id']))


def pace_probabilities(model,fs,weights,strength):
    base=model.scores(fs);front=np.array([f['front_rate']-.5 if f['style_observed'] else 0 for f in fs])
    return sum(w*softmax(base+direction*strength*front,model.temperature) for w,direction in zip(weights,(1,0,-1)))


def mean_loss(model,races,weights=(1/3,1/3,1/3),strength=0):
    return sum(-math.log(max(pace_probabilities(model,r['features'],weights,strength)[r['winner_index']],1e-12)) for r in races)/len(races)


def tune(races,iterations):
    train=eligible_split(races,2023);models=[];decisions=[]
    for reg in PROTOCOL['regularization_candidates']:
        model=HierarchicalModel().fit(train,iterations=iterations,regularization=reg,feature_names=ENRICHED_FEATURE_NAMES)
        calibration=eligible_split(races,2024,model.train_end)
        report=model.calibrate(calibration,PROTOCOL['temperature_candidates'])
        decisions.append(dict(regularization=reg,**report));models.append((report['after_log_loss'],reg,model,calibration))
    _,reg,model,calibration=min(models,key=lambda v:v[0])
    options=[(mean_loss(model,calibration,w,s),w,s) for w,s in PROTOCOL['pace_candidates']]
    loss,w,strength=min(options,key=lambda v:v[0])
    return model,dict(regularization=reg,grid=decisions,pace_weights=w,pace_strength=strength,calibration_pace_log_loss=loss),len(train),len(calibration)


def settlement(rows,p):
    selected=sorted(range(len(p)),key=lambda i:(-p[i],int(rows[i]['horse_number'])))
    output={}
    payouts=rows[0].get('payouts',{})
    for kind,k in (('win',1),('wide',2),('trio',3)):
        indexes=selected[:k];ns=sorted([str(rows[i]['horse_number']) for i in indexes],key=int)
        hit=ticket_hit(rows,indexes,kind)
        key=kind+':'+','.join(ns)
        payout=(payouts.get(key,rows[0].get('win_payout_100') if kind=='win' else None) if hit else 0)
        blocked=kind!='win' and len(rows)<4
        output[kind]=dict(kind=kind,horse_numbers=ns,hit=hit,fully_settled=blocked or payout is not None,
                          stake_yen=0 if blocked else 100,payout_yen=0 if blocked else payout,
                          market_status='blocked_unverified_sale_start_field' if blocked else 'reference')
    return output


def interval(values):
    x=sorted(values)
    return [x[int(.025*len(x))],x[min(len(x)-1,int(.975*len(x)))]] if x else None


def day_interval(records):
    days=collections.defaultdict(list)
    for r in records:
        delta=metrics(r['candidate'],r['winner_index'])['log_loss']-metrics(r['baseline'],r['winner_index'])['log_loss']
        days[r['date']].append(delta)
    vals=list(days.values());rng=random.Random(48);draws=[]
    for _ in range(500):
        sample=[d for _ in vals for d in rng.choice(vals)];draws.append(sum(sample)/len(sample))
    return interval(draws)


def final_odds_stress(records,cap):
    decisions=[]
    for r in records:
        rows=r['rows'];p=r['probabilities'];eligible=[i for i,x in enumerate(rows) if cap is None or x['final_win_odds']<=cap]
        ranked=sorted(eligible,key=lambda i:(-p[i]*rows[i]['final_win_odds'],int(rows[i]['horse_number'])))
        i=ranked[0] if ranked and p[ranked[0]]*rows[ranked[0]]['final_win_odds']>=1.05 else None
        payout=r['win_payout_100'] if i==r['winner_index'] else 0
        decisions.append(dict(fully_settled=i is None or payout is not None,stake_yen=100 if i is not None else 0,payout_yen=payout))
    return risk_report(decisions)


def ablation(races,name):
    out=copy.deepcopy(races)
    for r in out:
        for f in r['features']:
            if name=='without_grade_hierarchy':f['groups']=[f['group']]
            elif name=='without_margin_opponent_speed':
                for i in (11,12,13,14,15,16):f['values'][i]=0
            elif name=='without_style':
                for i in (7,8,20,21):f['values'][i]=0
                f['front_rate']=.5;f['style_observed']=False
    return out


def evaluate(db_path,previous_path,output,lag,iterations=400,reference_path=None):
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    old_data=json.loads(Path(previous_path).read_text())
    if hashlib.sha256(canonical(old_data).encode()).hexdigest()!=PROTOCOL['previous_model_sha256']:raise ValueError('frozen baseline artifact mismatch')
    (folder/'frozen_previous_model.json').write_text(canonical(old_data))
    previous=HierarchicalModel.from_dict(old_data,allow_research=True)
    history,fields,data_audit=load_archive(db_path,lag)
    print(json.dumps(dict(lag=lag,stage='building_features',**data_audit)),flush=True)
    enriched=pack(history_index(history),fields)
    old={r['race_id']:r for r in pack(previous_contract_index(history),fields,False)}
    model,tuning,train_n,cal_n=tune(enriched,iterations)
    test=eligible_split(enriched,2025,model.calibration_end)
    print(json.dumps(dict(lag=lag,stage='fixed_candidate',training=train_n,calibration=cal_n,test=len(test),tuning=tuning)),flush=True)
    records=[];predictions=[];markets={name:{k:[] for k in ('win','wide','trio')} for name in ('previous','candidate')}
    capital={name:[] for name in markets};odds={name:[] for name in markets};segments=collections.defaultdict(list)
    for race in test:
        rs=race['rows'];fs=race['features'];prior=old[race['race_id']]
        old_p=pace_probabilities(previous,prior['features'],(1/3,1/3,1/3),.15).tolist()
        new_p=pace_probabilities(model,fs,tuning['pace_weights'],tuning['pace_strength']).tolist()
        rank,_,_=podium(new_p)
        record=dict(race_id=race['race_id'],date=rs[0]['race_date'],baseline=old_p,candidate=new_p,winner_index=race['winner_index'],
                    candidate_top3=[sum(x) for x in rank],observed_top3=[i for i,r in enumerate(rs) if finish(r) and finish(r)<=3])
        records.append(record)
        for name,p in (('previous',old_p),('candidate',new_p)):
            st=settlement(rs,p)
            for k,s in st.items():markets[name][k].append(s)
            capital[name].append(dict(race_id=race['race_id'],cutoff_timestamp=fs[0]['cutoff_timestamp'],result_available_at=race['result_available_at'],markets=list(st.values())))
            if all(r.get('final_win_odds') is not None for r in rs):
                odds[name].append(dict(race_id=race['race_id'],rows=rs,probabilities=p,winner_index=race['winner_index'],win_payout_100=rs[0]['win_payout_100']))
        predictions.append(dict(race_id=race['race_id'],off_timestamp=race['off_timestamp'],horse_numbers=[r['horse_number'] for r in rs],
                                previous=old_p,candidate=new_p,winner_horse_number=rs[race['winner_index']]['horse_number'],
                                history_starts=[f['history_starts'] for f in fs]))
        for key in ('class:'+rs[0].get('race_category','unknown'),'course:'+fs[0]['group'],'distance:'+str(int(rs[0]['distance_m'])//400*400),'month:'+rs[0]['race_date'][:7]):segments[key].append(record)
    report=paired_report(records)
    report.update(publication_lag_days=lag,training_races=train_n,calibration_races=cal_n,evaluation_races=len(test),
                  day_cluster_95pct_log_loss_delta=day_interval(records),tuning=tuning,data_audit=data_audit,
                  settlement={name:{k:risk_report(v) for k,v in kinds.items()} for name,kinds in markets.items()},
                  feature_history_coverage=sum(f['history_starts']>0 for r in test for f in r['features'])/sum(len(r['features']) for r in test),
                  segment_metrics={k:paired_report(v,bootstrap_samples=0) for k,v in segments.items()},
                  strict_historical_publication_verified=False,forward_observed_races=0,production_eligible=False,
                  promotion_decision='wait_for_both_lags',odds_basis='post_race_final_hindsight_reference',live_bet_generation=False)
    report['virtual_capital']={}
    for name,rows in capital.items():
        result,decisions=capital_replay(rows);report['virtual_capital'][name]=result
        (folder/f'capital_decisions_{name}_lag{lag}.json').write_text(canonical(decisions))
    report['final_odds_reference']={}
    for name,rows in odds.items():
        if rows:
            summary,_=summarize_final_odds(rows)
            summary['stress']={str(cap):final_odds_stress(rows,cap) for cap in (None,50,100)}
            report['final_odds_reference'][name]=summary
    report['diagnostic_ablations']={}
    for name in ('without_grade_hierarchy','without_margin_opponent_speed','without_style'):
        races=ablation(enriched,name);train=eligible_split(races,2023)
        ab=HierarchicalModel().fit(train,iterations=iterations,regularization=tuning['regularization'],feature_names=ENRICHED_FEATURE_NAMES)
        ab.calibrate(eligible_split(races,2024,ab.train_end),PROTOCOL['temperature_candidates'])
        abr=eligible_split(races,2025,ab.calibration_end)
        report['diagnostic_ablations'][name]=dict(log_loss=mean_loss(ab,abr,tuning['pace_weights'],tuning['pace_strength']),races=len(abr),role='diagnostic_only_not_a_2025_selection_rule')
    if reference_path and lag==2:
        prior_records=json.loads(Path(reference_path).read_text());now={r['race_id']:r for r in predictions};paired=[];missing=[]
        for r in prior_records:
            v=now.get(r['race_id'])
            if not v or set(v['horse_numbers'])!=set(r['horse_numbers']):missing.append(r['race_id']);continue
            perm=[v['horse_numbers'].index(n) for n in r['horse_numbers']]
            paired.append(dict(race_id=r['race_id'],baseline=r['probabilities'],candidate=[v['candidate'][i] for i in perm],winner_index=r['horse_numbers'].index(r['winner_horse_number'])))
        report['literal_previous_predictions']=dict(reference_sha256=sha(reference_path),missing_or_changed_fields=missing,comparison=paired_report(paired) if paired else None)
    artifact={**model.to_dict(), 'research_only':True,'allow_missing_jockey':True,'publication_lag_days':lag,
              'availability_basis':'assumed_calendar_day_lag_for_research_only','pace_weights':dict(zip(('slow','average','high'),tuning['pace_weights'])),'pace_strength':tuning['pace_strength']}
    report.update(input_db_sha256=sha(db_path),protocol_sha256=hashlib.sha256(canonical(PROTOCOL).encode()).hexdigest(),
                  model_artifact_sha256=hashlib.sha256(canonical(artifact).encode()).hexdigest(),prediction_rows_sha256=hashlib.sha256(canonical(predictions).encode()).hexdigest(),
                  probability_sum_max_error=max(abs(sum(p['candidate'])-1) for p in predictions),
                  source_code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')},
                  external_data_dependencies=['historical exact publication and pre-off going observation times unavailable','official rider code absent in some result rows: neutral prior','complete final wide/trio losing quotes unavailable: combination EV blocked','future forward results do not exist yet'])
    (folder/f'comparison_lag{lag}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (folder/f'paired_predictions_lag{lag}.json').write_text(canonical(predictions))
    (folder/f'candidate_model_lag{lag}.json').write_text(canonical(artifact))
    print(json.dumps(dict(lag=lag,evaluation_races=len(test),previous=report['baseline'],candidate=report['candidate'],day_ci=report['day_cluster_95pct_log_loss_delta'],settlement=report['settlement']),ensure_ascii=False),flush=True)
    return report


def adoption_decision(reports,lags):
    eligible=(set(lags)=={2,7} and all(r['log_loss_delta']<0 and r['day_cluster_95pct_log_loss_delta'][1]<0 for r in reports))
    # Additional operational veto under the user's final-odds judgement axis.
    # This is a deployment rejection after the initial experiment, not a
    # retrospectively changed model-selection or evaluation protocol.
    returns=[(r.get('final_odds_reference',{}).get('previous',{}).get('post_race_value_settlement',{}).get('return_pct'),
              r.get('final_odds_reference',{}).get('candidate',{}).get('post_race_value_settlement',{}).get('return_pct')) for r in reports]
    final_pass=bool(returns) and all(a is not None and b is not None and b>=a and b>=100 for a,b in returns)
    return dict(original_protocol_probability_eligibility=eligible,
                promote_experimental_probability_only=eligible and final_pass,
                user_final_odds_axis_passed=final_pass,
                operational_veto='candidate final-odds reference return must not deteriorate and must reach 100%; post-experiment deployment review',
                active_model_decision='candidate eligible for review' if eligible and final_pass else 'keep_previous_active_model',
                strict_production_validated=False,live_bet_generation=False,rule=PROTOCOL['promotion'],evaluated_lags=list(lags))


def run(db,previous,output,lags=(2,7),iterations=400,reference=None):
    if iterations!=PROTOCOL['iterations']:raise ValueError('optimizer iterations must match frozen protocol')
    reports=[evaluate(db,previous,output,lag,iterations,reference) for lag in lags]
    decision=adoption_decision(reports,lags)
    for lag,report in zip(lags,reports):
        report['live_model_promotion_approved']=decision['promote_experimental_probability_only']
        report['deployment_decision']=decision
        Path(output,f'comparison_lag{lag}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    Path(output,'adoption_decision.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2));print(json.dumps(decision),flush=True)
    return decision


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--previous',required=True);p.add_argument('--output',required=True);p.add_argument('--reference-predictions');p.add_argument('--lags',nargs='+',type=int,default=[2,7]);a=p.parse_args()
    run(a.db,a.previous,a.output,a.lags,reference=a.reference_predictions)
