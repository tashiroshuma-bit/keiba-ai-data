"""Select runner-evidence calibration on 2024 only, then freeze and replay."""
import argparse
import gzip
import hashlib
import json
import math
import pickle
from pathlib import Path
import numpy as np
from completion_validation import sha
from evidence_rank_model import EvidenceRankModel
from ranking_model import RankModel
from historical_replay import eligible_split
from rank_calibration import mix_joint
from history_blend_research import decision,metrics
from relative_rank_research import report_metrics
from exact_rank_research import choose
from ranking_research import save,paired_intervals
from identity_recovery import causes
from validation import canonical

ROOT=Path(__file__).resolve().parent


def run(db,cache,output,lag):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/f'selection_lag{lag}.json').exists():raise ValueError('fresh experiment output required')
    state=json.loads((ROOT.parent/'PROJECT_STATE.json').read_text());digest=sha(db)
    if digest!=state['database']['sha256']:raise ValueError('canonical DB required')
    protocol=json.loads((ROOT/'EVIDENCE_RANK_PROTOCOL.json').read_text())
    with (Path(cache)/f'features_lag{lag}.pkl').open('rb') as f:stored=pickle.load(f)
    if stored['identity']['db']!=digest or stored['identity']['lag']!=lag:raise ValueError('cached features belong to different DB/lag')
    for name,expected in stored['identity']['sources'].items():
        if sha(ROOT/name)!=expected:raise ValueError('cached feature source differs')
    races=stored['races'];coverage={}
    for year in ('2023','2024'):
        fs=[(row,f) for r in races if r['rows'][0]['race_date'][:4]==year for row,f in zip(r['rows'],r['features'])]
        coverage[year]=dict(runners=len(fs),zero_observed_history=sum(f['history_starts']==0 for _,f in fs),
            under_three_starts=sum(f['history_starts']<3 for _,f in fs),unlinked_horse=sum(bool(row.get('horse_identity_missing')) for row,_ in fs),
            missing_jockey=sum(not bool(row.get('jockey_id')) for row,_ in fs))
    import sqlite3
    conn=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True)
    identity_causes=causes(conn);conn.close()
    save(output/f'input_audit_lag{lag}.json',dict(input_db_sha256=digest,coverage=coverage,
        unlinked_causes=identity_causes,additional_attested_keys_ready=identity_causes['rows'].get('attested_key_not_applied',0),
        inferred_ids_added=0,network_requests=0))
    base_path=ROOT/f'reports/exact_rank/model_lag{lag}.json';base=RankModel.from_dict(json.loads(base_path.read_text()))
    base_selection=ROOT/f'reports/exact_rank/selection_lag{lag}.json';policy=json.loads(base_selection.read_text())['prediction_set_policy']
    def baseline(r):
        return mix_joint(*base.predict([{**f,'values':f['legacy_values']} for f in r['features']]),protocol['base_uniform_joint_mixture'])
    train=eligible_split(races,2023);end=max(r['result_available_at'] for r in train)
    cal=[r for r in eligible_split(races,2024,end) if r['rows'][0]['race_date'][5:7]<='06']
    cal_end=max(r['result_available_at'] for r in cal)
    selection=[r for r in eligible_split(races,2024,cal_end) if r['rows'][0]['race_date'][5:7]>'06']
    base_records=[decision(r,*baseline(r),policy) for r in selection]
    base_metrics=metrics(base_records)
    grid=[dict(name='incumbent',policy=policy,metrics=base_metrics)];models={}
    print(canonical(dict(stage='fit_start',lag=lag,calibration=len(cal),selection=len(selection))),flush=True)
    for reg in protocol['regularization']:
        model=EvidenceRankModel.fit(base,cal,reg,protocol['iterations'],protocol['learning_rate'],protocol['base_uniform_joint_mixture'])
        save(output/f'component_reg{reg}_lag{lag}.json',model.to_dict())
        predictions=[model.predict(r['features']) for r in selection]
        for option in protocol['set_policies']:
            name=f'evidence_reg{reg}_{option}';models[name]=model
            values=[decision(r,p,q,option) for r,(p,q) in zip(selection,predictions)]
            grid.append(dict(name=name,policy=option,regularization=reg,beta=model.beta.tolist(),metrics=metrics(values)))
        print(canonical(dict(stage='fit_complete',lag=lag,regularization=reg,beta=model.beta.tolist())),flush=True)
    picked,eligibility=choose(grid,base_metrics);selected=models.get(picked['name'])
    model_hash=save(output/f'model_lag{lag}.json',(selected or base).to_dict())
    frozen=dict(schema='keiba-evidence-rank-selection-v1',protocol=protocol,input_db_sha256=digest,lag_days=lag,
        selected=picked['name'],model_sha256=model_hash,prediction_set_policy=picked['policy'],
        alpha=protocol['base_uniform_joint_mixture'] if selected is None else 0,
        calibration_races=len(cal),selection_races=len(selection),selection_end=max(r['result_available_at'] for r in selection),
        grid=grid,eligibility=eligibility,source_sha256={name:sha(ROOT/name) for name in ('evidence_rank_model.py','evidence_rank_research.py','EVIDENCE_RANK_PROTOCOL.json')},
        base_model_sha256=sha(base_path),base_selection_sha256=sha(base_selection))
    frozen_hash=save(output/f'selection_lag{lag}.json',frozen)
    print(canonical(dict(stage='selection_frozen_before_evaluation',lag=lag,selected=picked['name'],sha256=frozen_hash)),flush=True)
    restored=EvidenceRankModel.from_dict(selected.to_dict()) if selected else None
    years={};inventory={};reload_error=0
    for year in protocol['evaluation_years']:
        cohort=eligible_split(races,year,frozen['selection_end']);old=[];new=[];saved=[]
        for r in cohort:
            p,q=baseline(r);b,qb=restored.predict(r['features']) if restored else (p,q)
            if selected:
                c,qc=selected.predict(r['features']);reload_error=max(reload_error,float(np.max(np.abs(b-c))),float(np.max(np.abs(qb-qc))))
            numbers=[row['horse_number'] for row in r['rows']]
            before={**decision(r,p,q,policy),'horse_numbers':numbers};after={**decision(r,b,qb,picked['policy']),'horse_numbers':numbers}
            old.append(before);new.append(after)
            saved.append(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],horse_numbers=numbers,
                features_sha256=hashlib.sha256(canonical(r['features']).encode()).hexdigest(),baseline=before,candidate=after))
        years[str(year)]=dict(races=len(cohort),baseline=report_metrics(old),candidate=report_metrics(new),
            paired_day_bootstrap_95pct_delta=paired_intervals(cohort,old,new),full_coverage=True,role=protocol['evaluation_role'])
        for start in range(0,len(saved),250):
            path=output/f'predictions_lag{lag}_{year}_{start//250:02d}.json.gz';h=save(path,saved[start:start+250])
            inventory[path.name]=dict(sha256=h,bytes=path.stat().st_size,races=len(saved[start:start+250]))
        print(canonical(dict(stage='evaluation',lag=lag,year=year,
            metrics={name:{k:years[str(year)][name][k] for k in ('winner_hit','ordered_all_hit','top3_all_hit','winner_log_loss')} for name in ('baseline','candidate')})),flush=True)
    report=dict(schema='keiba-evidence-rank-evaluation-v1',selected=picked['name'],years=years,input_db_sha256=digest,
        model_sha256=model_hash,selection_sha256=frozen_hash,maximum_reload_error=reload_error,database_unchanged=sha(db)==digest,
        production_model_changed=False,forward_count_added=0,
        all_targets_met=all(v['candidate'][k]>=t for v in years.values() for k,t in protocol['targets'].items()))
    if reload_error or not report['database_unchanged']:raise ValueError('reload/input verification failed')
    save(output/f'prediction_inventory_lag{lag}.json',inventory);save(output/f'evaluation_lag{lag}.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','cache','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True);a=p.parse_args();run(a.db,a.cache,a.output,a.lag)
