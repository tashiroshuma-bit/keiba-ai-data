"""Frozen historical comparison of relative-form conditional rank trees."""
import argparse
import copy
import gzip
import hashlib
import json
import math
import pickle
from pathlib import Path
import numpy as np
from completion_validation import pack,sha
from enriched_features import load_archive,history_index
from historical_replay import eligible_split
from ranking_model import RankModel,top3_labels,joint_distribution
from relative_rank_model import RelativeRankTree,RelativeRankBlend,augment_relative
from rank_calibration import mix_joint
from ranking_research import save,paired_intervals
from history_blend_research import decision,metrics
from exact_rank_research import choose,calibration_loss
from validation import canonical

ROOT=Path(__file__).resolve().parent


def prepare(db,lag,cache):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    identity=dict(db=sha(db),lag=lag,sources={n:sha(ROOT/n) for n in
        ('relative_rank_model.py','history_rank_model.py','enriched_features.py','features.py','completion_validation.py')})
    path=cache/f'features_lag{lag}.pkl'
    if path.exists():
        with path.open('rb') as f:stored=pickle.load(f)
        if stored['identity']==identity:return stored['races'],stored['excluded'],stored['audit']
    history,fields,audit=load_archive(db,lag,allow_unlinked_fields=True)
    print(canonical(dict(stage='building_history',lag=lag,fields=len(fields))),flush=True)
    index=history_index(history);races=[];excluded=[]
    for r in pack(index,fields):
        try:top3_labels(r)
        except ValueError:excluded.append(r['race_id']);continue
        races.append(augment_relative(r,index))
    with path.open('wb') as f:pickle.dump(dict(identity=identity,races=races,excluded=excluded,audit=audit),f)
    return races,excluded,audit


def report_metrics(records):
    result=metrics(records)
    bins=[]
    for lo,hi in [(0,.1),(.1,.2),(.2,.3),(.3,.5),(.5,1.00001)]:
        group=[r for r in records if lo<=max(x[0] for x in r['marginal_probabilities'])<hi]
        if group:bins.append(dict(range=[lo,min(hi,1)],races=len(group),
            mean_forecast=np.mean([max(x[0] for x in r['marginal_probabilities']) for r in group]),
            observed_winner_hit=np.mean([r['winner_hit'] for r in group])))
    result['top1_calibration']=bins
    result['winner_brier_sum']=float(np.mean([sum((p[0]-int(n==r['target'][0]))**2
        for n,p in zip(r['horse_numbers'],r['marginal_probabilities'])) for r in records]))
    return result


def run(db,out,cache,lag):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/f'selection_lag{lag}.json').exists():raise ValueError('fresh experiment output required')
    protocol=json.loads((ROOT/'RELATIVE_RANK_PROTOCOL.json').read_text())
    state=json.loads((ROOT.parent/'PROJECT_STATE.json').read_text());before=sha(db)
    if before!=state['database']['sha256'] or state['database']['version']!=10:raise ValueError('canonical version 10 required')
    races,excluded,audit=prepare(db,lag,cache)
    train=eligible_split(races,2023);end=max(r['result_available_at'] for r in train)
    cal=[r for r in eligible_split(races,2024,end) if r['rows'][0]['race_date'][5:7]<='06']
    cal_end=max(r['result_available_at'] for r in cal)
    selection=[r for r in eligible_split(races,2024,cal_end) if r['rows'][0]['race_date'][5:7]>'06']
    base_path=ROOT/f'reports/exact_rank/model_lag{lag}.json';base=RankModel.from_dict(json.loads(base_path.read_text()))
    base_selection=ROOT/f'reports/exact_rank/selection_lag{lag}.json'
    policy=json.loads(base_selection.read_text())['prediction_set_policy'];alpha=protocol['uniform_joint_mixture']
    def base_dist(cohort):
        return [mix_joint(*base.predict([{**f,'values':f['legacy_values']} for f in r['features']]),alpha) for r in cohort]
    baseline_dist=base_dist(selection)
    baseline=metrics([decision(r,p,q,policy) for r,(p,q) in zip(selection,baseline_dist)])
    grid=[dict(name='incumbent',metrics=baseline,policy=policy,weight=0)]
    models={'incumbent':base}
    print(canonical(dict(stage='training_start',lag=lag,train=len(train),calibration=len(cal),selection=len(selection))),flush=True)
    for config in protocol['models']:
        model=RelativeRankTree().fit(train,config['family'],depth=config['depth'],
            trees=protocol['trees'],rate=protocol['rate'],minimum_leaf=protocol['minimum_leaf'],
            regularization=protocol['regularization'],bins=protocol['bins'])
        raw=model.raw(cal,enforce_time=False)
        losses={str(t):calibration_loss(raw,cal,t) for t in protocol['temperatures']}
        model.temperature=min(protocol['temperatures'],key=lambda t:(losses[str(t)],abs(t-1)))
        model.calibration_end=cal_end
        save(out/f"component_{config['name']}_lag{lag}.json",model.to_dict())
        new=[mix_joint(*joint_distribution(s,model.temperature),alpha) for s in model.raw(selection)]
        for weight in protocol['mixture_weights']:
            for candidate_policy in protocol['set_policies']:
                name=f"{config['name']}_w{weight}_{candidate_policy}"
                blend=RelativeRankBlend(base,model,weight,alpha);models[name]=blend
                values=[decision(r,(1-weight)*p+weight*b,(1-weight)*q+weight*qb,candidate_policy)
                    for r,(p,q),(b,qb) in zip(selection,baseline_dist,new)]
                grid.append(dict(name=name,metrics=metrics(values),policy=candidate_policy,weight=weight,
                    config=config,temperature=model.temperature,calibration_losses=losses))
        print(canonical(dict(stage='candidate_complete',lag=lag,name=config['name'])),flush=True)
    picked,eligibility=choose(grid,baseline);selected=models[picked['name']]
    model_hash=save(out/f'model_lag{lag}.json',selected.to_dict())
    frozen=dict(schema='keiba-relative-rank-selection-v1',protocol=protocol,input_db_sha256=before,lag_days=lag,
        selected=picked['name'],model_sha256=model_hash,prediction_set_policy=picked['policy'],
        alpha=alpha if picked['name']=='incumbent' else 0,
        train_races=len(train),calibration_races=len(cal),selection_races=len(selection),
        selection_end=max(r['result_available_at'] for r in selection),grid=grid,eligibility=eligibility,
        base_model_sha256=sha(base_path),base_selection_sha256=sha(base_selection),excluded_top_three_ties=excluded,
        source_sha256={n:sha(ROOT/n) for n in ('relative_rank_model.py','relative_rank_research.py','RELATIVE_RANK_PROTOCOL.json')})
    frozen_hash=save(out/f'selection_lag{lag}.json',frozen)
    print(canonical(dict(stage='selection_frozen_before_evaluation',lag=lag,selected=picked['name'],sha256=frozen_hash)),flush=True)
    restored=(RankModel.from_dict(selected.to_dict()) if picked['name']=='incumbent'
              else RelativeRankBlend.from_dict(selected.to_dict()))
    reports={};inventory={};maximum_reload_error=0
    for year in protocol['evaluation_years']:
        cohort=eligible_split(races,year,frozen['selection_end']);old=base_dist(cohort)
        new=old if picked['name']=='incumbent' else restored.predict_races(cohort)
        # Reload equivalence on the entire evaluated cohort, not one hand-picked example.
        original=old if picked['name']=='incumbent' else selected.predict_races(cohort)
        before_rows=[];after_rows=[];saved=[]
        for r,(p,q),(b,qb),(c,qc) in zip(cohort,old,new,original):
            maximum_reload_error=max(maximum_reload_error,float(np.abs(b-c).max()),float(np.abs(qb-qc).max()))
            numbers=[row['horse_number'] for row in r['rows']]
            a={**decision(r,p,q,policy),'horse_numbers':numbers}
            v={**decision(r,b,qb,picked['policy']),'horse_numbers':numbers}
            before_rows.append(a);after_rows.append(v)
            saved.append(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=numbers,
                features_sha256=hashlib.sha256(canonical(r['features']).encode()).hexdigest(),baseline=a,candidate=v))
        reports[str(year)]=dict(races=len(cohort),baseline=report_metrics(before_rows),candidate=report_metrics(after_rows),
            paired_day_bootstrap_95pct_delta=paired_intervals(cohort,before_rows,after_rows),
            role=protocol['evaluation_role'],full_coverage=True)
        # Bounded shards keep the full saved probability evidence inspectable and transferable.
        for start in range(0,len(saved),250):
            path=out/f'predictions_lag{lag}_{year}_{start//250:02d}.json.gz'
            digest=save(path,saved[start:start+250]);inventory[path.name]=dict(sha256=digest,bytes=path.stat().st_size,races=len(saved[start:start+250]))
        print(canonical(dict(stage='evaluation',lag=lag,year=year,report=reports[str(year)])),flush=True)
    report=dict(schema='keiba-relative-rank-evaluation-v1',selected=picked['name'],years=reports,
        model_sha256=model_hash,selection_sha256=frozen_hash,input_db_sha256=before,
        maximum_reload_error=maximum_reload_error,database_unchanged=sha(db)==before,
        all_targets_met=all(v['candidate'][k]>=target for v in reports.values() for k,target in protocol['targets'].items()),
        production_model_changed=False,forward_count_added=0,source_audit=audit)
    if maximum_reload_error or not report['database_unchanged']:raise ValueError('verification failed')
    save(out/f'prediction_inventory_lag{lag}.json',inventory)
    save(out/f'evaluation_lag{lag}.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','output','cache'):p.add_argument('--'+name,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();run(a.db,a.output,a.cache,a.lag)
