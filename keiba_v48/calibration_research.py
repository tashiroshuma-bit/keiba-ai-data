"""Fit probability shrinkage on 2024 only; reuse immutable full-field rank evidence."""
import argparse
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from completion_validation import pack, sha
from enriched_features import load_archive, history_index
from historical_replay import eligible_split
from ranking_model import RankModel, augment, top3_labels
from ranking_research import record, save
from validation import canonical

ROOT = Path(__file__).resolve().parent


def adjusted(r, alpha):
    p = np.array(r['marginal_probabilities'], float); n = len(p)
    p = (1-alpha)*p + alpha/n
    target = [r['horse_numbers'].index(x) for x in r['target']]
    q = (1-alpha)*r['joint_target_probability'] + alpha/(n*(n-1)*(n-2))
    label = np.zeros(n); label[target[0]] = 1
    top = r['horse_numbers'].index(r['winner_pick'])
    return dict(winner_log_loss=-math.log(max(p[target[0],0],1e-300)),
                joint_log_loss=-math.log(max(q,1e-300)),
                winner_brier=float(np.square(p[:,0]-label).sum()),
                winner_confidence=float(p[top,0]), winner_hit=r['winner_hit'],
                ordered_all_hit=r['ordered_all_hit'], top3_all_hit=r['top3_all_hit'],
                marginal_probabilities=p.tolist(), joint_target_probability=q)


def metrics(rows, alpha):
    values = [adjusted(r, alpha) for r in rows]
    result = dict(races=len(values), **{k:float(np.mean([v[k] for v in values])) for k in
                  ('winner_log_loss','joint_log_loss','winner_brier','winner_hit','ordered_all_hit','top3_all_hit')})
    bins=[]
    for lo, hi in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.00000001)):
        group=[v for v in values if lo<=v['winner_confidence']<hi]
        bins.append(dict(lower=lo, upper=min(hi,1), races=len(group),
                    mean_probability=float(np.mean([v['winner_confidence'] for v in group])) if group else None,
                    hit_rate=float(np.mean([v['winner_hit'] for v in group])) if group else None))
    result['winner_reliability']=bins
    result['top_label_ece']=sum(b['races']*abs(b['mean_probability']-b['hit_rate']) for b in bins if b['races'])/len(values)
    return result


def run(db, output, lag, previous):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/f'calibration_lag{lag}.json').exists():raise ValueError('fresh output required')
    protocol=json.loads((ROOT/'CALIBRATION_PROTOCOL.json').read_text())
    dbhash=sha(db)
    selection=ROOT/f'reports/exact_rank/selection_lag{lag}.json'
    base=json.loads(selection.read_text())
    model_path=ROOT/f'reports/exact_rank/model_lag{lag}.json'
    if sha(model_path)!=base['model_sha256']:raise ValueError('base model mismatch')
    model=RankModel.from_dict(json.loads(model_path.read_text()))
    history,fields,_=load_archive(db,lag,allow_unlinked_fields=True)
    print(canonical(dict(stage='calibration_features',lag=lag)),flush=True)
    # Build 2024 only. Earlier histories remain available; evaluation labels do not enter fitting.
    races=[]
    for r in pack(history_index(history),[r for r in fields if r['race_date'].startswith('2024')]):
        try:top3_labels(r)
        except ValueError:continue
        races.append(augment(r))
    h1=[r for r in eligible_split(races,2024,model.train_end) if r['rows'][0]['race_date'][5:7]<='06']
    end=max(r['result_available_at'] for r in h1)
    h2=[r for r in eligible_split(races,2024,end) if r['rows'][0]['race_date'][5:7]>'06']
    def evidence(cohort):
        result=[]
        for r in cohort:
            # Frozen weights may be assessed on H1 before their previous calibration end.
            z=record(r,*model.predict(r['features'],enforce_time=False))
            result.append(dict(race_id=r['race_id'],date=r['rows'][0]['race_date'],
                        horse_numbers=[x['horse_number'] for x in r['rows']],**z))
        return result
    fit=evidence(h1);gate=evidence(h2)
    grid=[dict(alpha=a,fit=metrics(fit,a)) for a in protocol['alpha_grid']]
    candidate=min(grid,key=lambda r:(r['fit']['winner_log_loss'],r['alpha']))['alpha']
    before=metrics(gate,0);after=metrics(gate,candidate)
    passed=all(after[k]<=before[k]+1e-12 for k in ('winner_log_loss','joint_log_loss'))
    alpha=candidate if passed else 0
    artifact=dict(schema='keiba-rank-uniform-joint-calibration-v1',alpha=alpha,model_sha256=sha(model_path),
        base_selection_sha256=sha(selection),input_db_sha256=dbhash,selection_year=2024,
        fit_end=end,selection_end=max(r['result_available_at'] for r in h2),
        fit_races=len(fit),selection_races=len(gate),candidate_alpha=candidate,gate_passed=passed,
        gate_before=before,gate_after=after,grid=grid,research_only=True,active_model_promoted=False,
        protocol_sha256=sha(ROOT/'CALIBRATION_PROTOCOL.json'),
        source_sha256={p:sha(ROOT/p) for p in ('calibration_research.py','rank_calibration.py','CALIBRATION_PROTOCOL.json')})
    artifact_hash=save(out/f'calibration_lag{lag}.json',artifact)
    print(canonical(dict(stage='calibration_frozen',lag=lag,alpha=alpha,sha256=artifact_hash)),flush=True)
    # The evaluation source is read only after the artifact above has been frozen.
    prior=json.loads(gzip.decompress(Path(previous).read_bytes()))
    print(canonical(dict(stage='evaluation_shape',keys=list(prior[0]))),flush=True)
    evaluated=[]; years={}
    for year in protocol['exploratory_evaluation_years']:
        rows=[]
        for item in prior:
            if str(item['date'])[:4]!=str(year):continue
            old=item['candidate']
            rows.append(dict(race_id=item['race_id'],date=item['date'],horse_numbers=item['horse_numbers'],**old))
        years[str(year)]=dict(before=metrics(rows,0),after=metrics(rows,alpha))
        for r in rows:evaluated.append(dict(race_id=r['race_id'],date=r['date'],horse_numbers=r['horse_numbers'],
            target=r['target'],winner_pick=r['winner_pick'],ordered_pick=r['ordered_pick'],top3_pick=r['top3_pick'],
            before=adjusted(r,0),after=adjusted(r,alpha)))
    predhash=save(out/f'predictions_lag{lag}.json.gz',evaluated)
    save(out/f'fit_evidence_lag{lag}.json.gz',dict(fit=fit,gate=gate))
    report=dict(schema='keiba-rank-calibration-evaluation-v1',lag_days=lag,alpha=alpha,years=years,
        input_db_sha256=dbhash,input_predictions_sha256=sha(previous),calibration_sha256=artifact_hash,
        predictions_sha256=predhash,rank_decisions_changed=0,evaluation_role='2025/2026 retrospective exploratory',
        database_unchanged=sha(db)==dbhash,active_model_promoted=False,forward_races=0)
    save(out/f'evaluation_lag{lag}.json',report)
    print(canonical(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('db','output','previous'):p.add_argument('--'+k,required=True)
    p.add_argument('--lag',required=True,type=int,choices=(2,7));a=p.parse_args()
    run(a.db,a.output,a.lag,a.previous)
