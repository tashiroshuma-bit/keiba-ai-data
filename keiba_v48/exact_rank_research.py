"""Target exact rank hits with a frozen all-race, no-market protocol."""
import argparse
import collections
import json
import math
from pathlib import Path
import numpy as np
from completion_validation import pack, sha
from enriched_features import load_archive,history_index
from historical_replay import eligible_split
from ranking_model import RankModel,augment,top3_labels,joint_distribution
from ranking_research import save,record,aggregate,paired_intervals
from exact_rank_model import ExactRankTree,exact_set
from validation import canonical

ROOT=Path(__file__).resolve().parent
PROTOCOL=json.loads((ROOT/'EXACT_RANK_PROTOCOL.json').read_text())
KEYS=tuple(PROTOCOL['targets'])


def exact_record(r,scores,temperature,policy):
    p,q=joint_distribution(scores,temperature)
    v=record(r,p,q)
    if policy=='exact_set':
        ix,mass=exact_set(q,[x['horse_number'] for x in r['rows']])
        target=top3_labels(r)
        v.update(top3_pick=[r['rows'][i]['horse_number'] for i in ix],top3_all_hit=int(set(ix)==set(target)),
                 top3_recall=len(set(ix)&set(target))/3,predicted_set_probability=mass)
    elif policy!='marginal_recall':raise ValueError('invalid set decision policy')
    v['joint_log_loss']=-math.log(max(v['joint_target_probability'],1e-300))/3
    v['predicted_winner_probability']=float(p[:,0].max())
    v['predicted_order_probability']=float(q.max())
    return v


def summary(records):
    value=aggregate(records)
    value['joint_log_loss']=float(np.mean([r['joint_log_loss'] for r in records]))
    value['target_achievement']={k:value[k]/target for k,target in PROTOCOL['targets'].items()}
    value['all_targets_met']=all(value[k]>=target for k,target in PROTOCOL['targets'].items())
    return value


def calibration_loss(scores,races,temp):
    losses=[]
    for s,r in zip(scores,races):
        remain=list(range(s.shape[1])); value=0
        for k,i in enumerate(top3_labels(r)):
            a=s[k,remain]/temp;m=a.max()
            value+=m+np.log(np.exp(a-m).sum())-s[k,i]/temp;remain.remove(i)
        losses.append(value/3)
    return float(np.mean(losses))


def choose(grid,baseline):
    def eligible(g):
        return all(round(g['metrics'][k]*g['metrics']['races'])>=round(baseline[k]*baseline['races']) for k in KEYS)
    options=[g for g in grid if eligible(g)]
    def key(g):
        product=math.prod(g['metrics'][k]/PROTOCOL['targets'][k] for k in KEYS)
        return (-product,g['metrics']['joint_log_loss'],g['name'])
    return min(options,key=key),[dict(name=g['name'],eligible=eligible(g)) for g in grid]


def run(db,output,lag):
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    if (folder/f'selection_lag{lag}.json').exists():raise ValueError('fresh output required')
    dbhash=sha(db)
    history,fields,_=load_archive(db,lag,allow_unlinked_fields=True)
    print(canonical(dict(stage='packing',lag=lag)),flush=True)
    races=[];ties=[]
    for r in pack(history_index(history),fields):
        try:top3_labels(r)
        except ValueError:ties.append(r['race_id']);continue
        races.append(augment(r))
    train=eligible_split(races,2023); train_end=max(r['result_available_at'] for r in train)
    cal=[r for r in eligible_split(races,2024,train_end) if int(r['rows'][0]['race_date'][5:7])<=6]
    cal_end=max(r['result_available_at'] for r in cal)
    selection=[r for r in eligible_split(races,2024,cal_end) if int(r['rows'][0]['race_date'][5:7])>6]
    original=json.loads((ROOT/f'reports/ranking/model_lag{lag}.json').read_text())
    incumbent=RankModel.from_dict(original)
    raw=[incumbent.scores(r['features']) for r in selection]
    before=[exact_record(r,s,incumbent.temperature,'marginal_recall') for r,s in zip(selection,raw)]
    baseline=summary(before)
    grid=[];models={'incumbent_original':incumbent,'incumbent_exact_set':incumbent}
    policies={'incumbent_original':'marginal_recall','incumbent_exact_set':'exact_set'}
    for name in models:
        recs=[exact_record(r,s,incumbent.temperature,policies[name]) for r,s in zip(selection,raw)]
        grid.append(dict(name=name,metrics=summary(recs),temperature=incumbent.temperature))
    for config in PROTOCOL['models']:
        name=config['name']
        model=ExactRankTree().fit(train,config['family'],depth=config['depth'],trees=PROTOCOL['trees'],
            rate=PROTOCOL['learning_rate'],minimum_leaf=PROTOCOL['minimum_leaf'],regularization=PROTOCOL['leaf_regularization'],bins=PROTOCOL['bins'])
        raw_cal=model.raw(cal)
        loss={str(t):calibration_loss(raw_cal,cal,t) for t in PROTOCOL['temperatures']}
        model.temperature=min(PROTOCOL['temperatures'],key=lambda t:(loss[str(t)],abs(t-1)))
        model.calibration_end=cal_end
        predictions=[exact_record(r,s,model.temperature,'exact_set') for r,s in zip(selection,model.raw(selection))]
        g=dict(**config,temperature=model.temperature,calibration_joint_loss=loss,metrics=summary(predictions))
        grid.append(g);models[name]=model;policies[name]='exact_set'
        print(canonical(dict(stage='selection_candidate',lag=lag,name=name,metrics=g['metrics'])),flush=True)
    selected,eligibility=choose(grid,baseline);name=selected['name'];model=models[name];policy=policies[name]
    modelhash=save(folder/f'model_lag{lag}.json',model.to_dict())
    frozen=dict(protocol=PROTOCOL,lag_days=lag,input_db_sha256=dbhash,baseline_model_sha256=sha(ROOT/f'reports/ranking/model_lag{lag}.json'),
        selected=name,prediction_set_policy=policy,model_sha256=modelhash,grid=grid,eligibility=eligibility,
        train_races=len(train),calibration_races=len(cal),selection_races=len(selection),
        selection_end=max(r['result_available_at'] for r in selection),excluded_top_three_ties=ties,
        source_sha256={n:sha(ROOT/n) for n in ('exact_rank_model.py','exact_rank_research.py','EXACT_RANK_PROTOCOL.json')})
    frozenhash=save(folder/f'selection_lag{lag}.json',frozen)
    print(canonical(dict(stage='frozen_before_evaluation',lag=lag,selected=name,policy=policy)),flush=True)
    restored=(RankModel.from_dict(model.to_dict()) if isinstance(model,RankModel) else ExactRankTree.from_dict(model.to_dict()))
    reports={};saved=[];reload_error=0.
    for year in PROTOCOL['evaluation_years']:
        cohort=eligible_split(races,year,frozen['selection_end'])
        oldraw=[incumbent.scores(r['features']) for r in cohort]
        newraw=([restored.scores(r['features']) for r in cohort] if isinstance(restored,RankModel) else restored.raw(cohort))
        firstraw=([model.scores(r['features']) for r in cohort] if isinstance(model,RankModel) else model.raw(cohort))
        reload_error=max(reload_error,max(float(np.max(np.abs(a-b))) for a,b in zip(newraw,firstraw)))
        old=[exact_record(r,s,incumbent.temperature,'marginal_recall') for r,s in zip(cohort,oldraw)]
        new=[exact_record(r,s,model.temperature,policy) for r,s in zip(cohort,newraw)]
        reports[str(year)]=dict(baseline=summary(old),candidate=summary(new),
            paired_day_bootstrap_95pct_delta=paired_intervals(cohort,old,new),
            full_coverage=True,coverage_races=len(cohort),evaluation_role=PROTOCOL['evaluation_role'])
        saved.extend(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=[x['horse_number'] for x in r['rows']],
                          baseline=a,candidate=b) for r,a,b in zip(cohort,old,new))
        print(canonical(dict(stage='evaluation',lag=lag,year=year,report=reports[str(year)])),flush=True)
    predhash=save(folder/f'predictions_lag{lag}.json.gz',saved)
    report=dict(input_db_sha256=dbhash,selection_sha256=frozenhash,model_sha256=modelhash,predictions_sha256=predhash,
        selected=name,prediction_set_policy=policy,years=reports,maximum_reload_error=reload_error,
        database_unchanged=sha(db)==dbhash,targets=PROTOCOL['targets'],forward_races=0,live_model_promoted=False)
    if reload_error or not report['database_unchanged']:raise ValueError('reload/input verification failed')
    save(folder/f'evaluation_lag{lag}.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('db','output'):p.add_argument('--'+key,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();run(a.db,a.output,a.lag)
