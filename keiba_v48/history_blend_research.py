"""Separate data-repair effects from additional past-finish model effects."""
import argparse
import gzip
import json
import math
from pathlib import Path
import numpy as np
from completion_validation import pack,sha
from enriched_features import load_archive,history_index
from historical_replay import eligible_split
from ranking_model import RankModel,augment,top3_labels
from history_rank_model import HistoryRankModel
from history_blend_model import HistoryBlendModel,augment_blend
from ranking_research import record,save,aggregate,paired_intervals
from exact_rank_model import exact_set
from exact_rank_research import choose,calibration_loss
from rank_calibration import mix_joint
from validation import canonical

ROOT=Path(__file__).resolve().parent


def decision(r,p,q,policy):
    v=record(r,p,q)
    if policy=='exact_set':
        ix,mass=exact_set(q,[x['horse_number'] for x in r['rows']]);target=top3_labels(r)
        v.update(top3_pick=[r['rows'][i]['horse_number'] for i in ix],top3_all_hit=int(set(ix)==set(target)),
                 top3_recall=len(set(ix)&set(target))/3,predicted_set_probability=mass)
    elif policy!='marginal_recall':raise ValueError('unknown set policy')
    v['joint_log_loss']=-math.log(max(v['joint_target_probability'],1e-300))
    return v


def metrics(rows):return dict(aggregate(rows),joint_log_loss=float(np.mean([r['joint_log_loss'] for r in rows])))


def run(db,previous,output,lag):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/f'selection_lag{lag}.json').exists():raise ValueError('fresh experiment directory required')
    protocol=json.loads((ROOT/'HISTORY_BLEND_PROTOCOL.json').read_text());before=sha(db)
    state=json.loads((ROOT.parent/'PROJECT_STATE.json').read_text())
    if before!=state['database']['sha256'] or state['database']['version']!=10:raise ValueError('verified version 10 required')
    history,fields,_=load_archive(db,lag,allow_unlinked_fields=True)
    print(canonical(dict(stage='features',lag=lag)),flush=True)
    index=history_index(history);original={};extended=[];ties=[]
    for r in pack(index,fields):
        try:top3_labels(r)
        except ValueError:ties.append(r['race_id']);continue
        original[r['race_id']]=augment(r);extended.append(augment_blend(r,index))
    train=eligible_split(extended,2023);end=max(r['result_available_at'] for r in train)
    cal=[r for r in eligible_split(extended,2024,end) if r['rows'][0]['race_date'][5:7]<='06']
    cal_end=max(r['result_available_at'] for r in cal)
    selection=[r for r in eligible_split(extended,2024,cal_end) if r['rows'][0]['race_date'][5:7]>'06']
    base_path=ROOT/f'reports/exact_rank/model_lag{lag}.json';base=RankModel.from_dict(json.loads(base_path.read_text()))
    base_selection=ROOT/f'reports/exact_rank/selection_lag{lag}.json'
    policy=json.loads(base_selection.read_text())['prediction_set_policy']
    base_dist=[mix_joint(*base.predict(original[r['race_id']]['features']),.1) for r in selection]
    baseline=metrics([decision(r,p,q,policy) for r,(p,q) in zip(selection,base_dist)])
    grid=[dict(name='incumbent_repaired_data',metrics=baseline,alpha=.1,policy=policy)]
    models={'incumbent_repaired_data':base}
    for family in protocol['families']:
        for reg in protocol['regularization']:
            model=HistoryRankModel().fit(train,family=family,regularization=reg,iterations=protocol['iterations'])
            raw=[model.scores(r['features']) for r in cal]
            losses={str(t):calibration_loss(raw,cal,t) for t in protocol['temperatures']}
            model.temperature=min(protocol['temperatures'],key=lambda t:(losses[str(t)],abs(t-1)))
            model.calibration_end=cal_end
            dist=[model.predict(r['features'],enforce_time=False) for r in cal]
            alpha_losses={str(a):float(np.mean([-math.log(max((1-a)*p[top3_labels(r)[0],0]+a/len(p),1e-300))
                          for r,(p,q) in zip(cal,dist)])) for a in protocol['mixture_alpha']}
            alpha=min(protocol['mixture_alpha'],key=lambda a:(alpha_losses[str(a)],a))
            new_dist=[mix_joint(*model.predict(r['features']),alpha) for r in selection]
            for weight in protocol['mixture_weights']:
                blend=HistoryBlendModel(base,model,weight,.1,alpha)
                combined=[((1-weight)*a+weight*b,(1-weight)*qa+weight*qb) for (a,qa),(b,qb) in zip(base_dist,new_dist)]
                for candidate_policy in protocol['set_policies']:
                    name=f'{family}_reg{reg}_weight{weight}_{candidate_policy}';models[name]=blend
                    values=[decision(r,p,q,candidate_policy) for r,(p,q) in zip(selection,combined)]
                    grid.append(dict(name=name,family=family,regularization=reg,weight=weight,alpha=0,
                        component_alpha=alpha,temperature=model.temperature,policy=candidate_policy,
                        calibration_temperature_losses=losses,calibration_alpha_losses=alpha_losses,metrics=metrics(values)))
            print(canonical(dict(stage='model_fitted',lag=lag,family=family,reg=reg)),flush=True)
    picked,eligibility=choose(grid,baseline);model=models[picked['name']]
    model_hash=save(out/f'model_lag{lag}.json',model.to_dict())
    frozen=dict(schema='keiba-history-blend-selection-v1',protocol=protocol,input_db_sha256=before,lag_days=lag,
        selected=picked['name'],model_sha256=model_hash,alpha=picked['alpha'],prediction_set_policy=picked['policy'],
        base_model_sha256=sha(base_path),base_selection_sha256=sha(base_selection),grid=grid,eligibility=eligibility,
        train_races=len(train),calibration_races=len(cal),selection_races=len(selection),
        selection_end=max(r['result_available_at'] for r in selection),excluded_top_three_ties=ties,
        source_sha256={n:sha(ROOT/n) for n in ('history_rank_model.py','history_blend_model.py','history_blend_research.py','HISTORY_BLEND_PROTOCOL.json')})
    frozen_hash=save(out/f'selection_lag{lag}.json',frozen)
    print(canonical(dict(stage='selection_frozen',lag=lag,selected=picked['name'],sha256=frozen_hash)),flush=True)
    old={r['race_id']:r for r in json.loads(gzip.decompress(Path(previous).read_bytes()))}
    restored=HistoryBlendModel.from_dict(model.to_dict()) if isinstance(model,HistoryBlendModel) else RankModel.from_dict(model.to_dict())
    reports={};saved=[];error=0
    for year in protocol['evaluation_years']:
        cohort=eligible_split(extended,year,frozen['selection_end']);older=[];repaired=[];new=[]
        for r in cohort:
            legacy=original[r['race_id']];prior=old[r['race_id']];numbers=[x['horse_number'] for x in r['rows']]
            assert prior['horse_numbers']==numbers
            a=prior['candidate'].copy();n=len(numbers);pm=.9*np.array(a['marginal_probabilities'])+.1/n;labels=top3_labels(r)
            assert a['target']==[numbers[i] for i in labels]
            a['marginal_probabilities']=pm.tolist();a['joint_target_probability']=.9*a['joint_target_probability']+.1/(n*(n-1)*(n-2))
            a['joint_log_loss']=-math.log(a['joint_target_probability']);a['winner_log_loss']=-math.log(pm[labels[0],0])
            a['mean_rank_log_loss']=float(np.mean([-math.log(pm[labels[k],k]) for k in range(3)]))
            p,q=mix_joint(*base.predict(legacy['features']),.1);b=decision(r,p,q,policy)
            use=r if isinstance(restored,HistoryBlendModel) else legacy
            p,q=mix_joint(*restored.predict(use['features']),picked['alpha']);c=decision(r,p,q,picked['policy'])
            error=max(error,float(np.abs(restored.predict(use['features'])[0]-model.predict(use['features'])[0]).max()))
            older.append(a);repaired.append(b);new.append(c)
            saved.append(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=numbers,previous=a,repaired_baseline=b,candidate=c))
        reports[str(year)]=dict(previous=metrics(older),repaired_baseline=metrics(repaired),candidate=metrics(new),
            paired_data_repair_delta=paired_intervals(cohort,older,repaired),paired_model_delta=paired_intervals(cohort,repaired,new),
            full_coverage=True,races=len(cohort),evaluation_role=protocol['evaluation_role'])
        print(canonical(dict(stage='evaluation',lag=lag,year=year,report=reports[str(year)])),flush=True)
    pred_hash=save(out/f'predictions_lag{lag}.json.gz',saved)
    report=dict(schema='keiba-history-blend-evaluation-v1',input_db_sha256=before,selection_sha256=frozen_hash,
        model_sha256=model_hash,predictions_sha256=pred_hash,base_predictions_sha256=sha(previous),selected=picked['name'],years=reports,
        maximum_reload_error=error,database_unchanged=sha(db)==before,targets=protocol['targets'],
        all_targets_met=all(v['candidate'][k]>=t for v in reports.values() for k,t in protocol['targets'].items()),
        active_model_promoted=False,forward_races=0)
    if error or not report['database_unchanged']:raise ValueError('reload/input verification failed')
    save(out/f'evaluation_lag{lag}.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('db','previous','output'):p.add_argument('--'+k,required=True)
    p.add_argument('--lag',type=int,required=True,choices=(2,7));a=p.parse_args();run(a.db,a.previous,a.output,a.lag)
