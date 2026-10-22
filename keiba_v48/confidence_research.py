"""A predeclared high-confidence correction selected entirely within 2024."""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
from calibration_research import adjusted, metrics
from ranking_research import save
from completion_validation import sha
from confidence_calibration import alpha_for
from validation import canonical

ROOT=Path(__file__).resolve().parent


def transform(rows,artifact):
    output=[]
    for r in rows:
        alpha=alpha_for(artifact,r['marginal_probabilities'],artifact['model_sha256'],artifact['base_selection_sha256'])
        value=adjusted(r,alpha)
        output.append({**r,'marginal_probabilities':value['marginal_probabilities'],
                       'joint_target_probability':value['joint_target_probability'],'alpha':alpha})
    return output


def fixed_high_gap(rows,changed):
    ix=[i for i,r in enumerate(rows) if max(p[0] for p in r['marginal_probabilities'])>=.4]
    return abs(float(np.mean([max(p[0] for p in changed[i]['marginal_probabilities'])-rows[i]['winner_hit'] for i in ix])))


def run(lag,fit_dir,previous,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/f'confidence_lag{lag}.json').exists():raise ValueError('fresh output required')
    protocol=json.loads((ROOT/'CONFIDENCE_PROTOCOL.json').read_text())
    fit_path=Path(fit_dir)/f'fit_evidence_lag{lag}.json.gz'
    global_path=Path(fit_dir)/f'calibration_lag{lag}.json'
    evidence=json.loads(gzip.decompress(fit_path.read_bytes()))
    base=json.loads(global_path.read_text());fit,gate=evidence['fit'],evidence['gate']
    candidate=[];grid=[];cuts=protocol['base_probability_strata']
    for lo,hi in zip(cuts,cuts[1:]):
        part=[r for r in fit if lo<=max(p[0] for p in r['marginal_probabilities'])<hi]
        options=[dict(alpha=a,loss=metrics(part,a)['winner_log_loss']) for a in protocol['alpha_grid']] if part else []
        alpha=min(options,key=lambda v:(v['loss'],v['alpha']))['alpha'] if len(part)>=protocol['minimum_fit_races_per_stratum'] else base['alpha']
        candidate.append(dict(lower=lo,upper=hi,alpha=alpha,fit_races=len(part)));grid.append(options)
    artifact=dict(schema='keiba-rank-confidence-calibration-v1',bands=candidate,selection_year=2024,
        model_sha256=base['model_sha256'],base_selection_sha256=base['base_selection_sha256'],
        input_db_sha256=base['input_db_sha256'],fit_end=base['fit_end'],selection_end=base['selection_end'],
        fit_evidence_sha256=sha(fit_path),global_calibration_sha256=sha(global_path),research_only=True)
    global_rows=transform(gate,{**artifact,'bands':[dict(lower=0,upper=cuts[-1],alpha=base['alpha'])]})
    proposed=transform(gate,artifact);before=metrics(global_rows,0);after=metrics(proposed,0)
    passed=all(after[k]<=before[k]+1e-12 for k in ('winner_log_loss','joint_log_loss')) and fixed_high_gap(gate,proposed)<fixed_high_gap(gate,global_rows)
    artifact.update(candidate_bands=candidate,gate_passed=passed,gate_before=before,gate_after=after,
        grid=grid,protocol_sha256=sha(ROOT/'CONFIDENCE_PROTOCOL.json'),
        source_sha256={p:sha(ROOT/p) for p in ('confidence_research.py','confidence_calibration.py','CONFIDENCE_PROTOCOL.json')})
    if not passed:artifact['bands']=[dict(lower=0,upper=cuts[-1],alpha=base['alpha'])]
    artifact_hash=save(out/f'confidence_lag{lag}.json',artifact)
    print(canonical(dict(stage='confidence_frozen_before_evaluation',lag=lag,bands=artifact['bands'],gate_passed=passed,sha256=artifact_hash)),flush=True)
    records=json.loads(gzip.decompress(Path(previous).read_bytes()))
    rows=[dict(race_id=r['race_id'],date=r['date'],horse_numbers=r['horse_numbers'],**r['candidate']) for r in records]
    changed=transform(rows,artifact);years={}
    for year in ('2025','2026'):
        original=[r for r in rows if r['date'][:4]==year];new=[r for r in changed if r['date'][:4]==year]
        bands=[]
        for lo,hi in ((.4,.6),(.6,.8),(.8,1.00000001)):
            ix=[i for i,r in enumerate(original) if lo<=max(p[0] for p in r['marginal_probabilities'])<hi]
            bands.append(dict(original_lower=lo,original_upper=min(hi,1),races=len(ix),
                hit_rate=float(np.mean([original[i]['winner_hit'] for i in ix])) if ix else None,
                before_mean=float(np.mean([max(p[0] for p in original[i]['marginal_probabilities']) for i in ix])) if ix else None,
                after_mean=float(np.mean([max(p[0] for p in new[i]['marginal_probabilities']) for i in ix])) if ix else None))
        years[year]=dict(before=metrics(original,0),after=metrics(new,0),fixed_original_confidence_groups=bands)
    predictions=[]
    for original,new in zip(rows,changed):
        predictions.append(dict(race_id=original['race_id'],date=original['date'],horse_numbers=original['horse_numbers'],
            target=original['target'],winner_pick=original['winner_pick'],top3_pick=original['top3_pick'],ordered_pick=original['ordered_pick'],
            alpha=new['alpha'],before=adjusted(original,0),after=adjusted(new,0)))
    pred_hash=save(out/f'confidence_predictions_lag{lag}.json.gz',predictions)
    report=dict(schema='keiba-confidence-evaluation-v1',lag_days=lag,years=years,
        calibration_sha256=artifact_hash,predictions_sha256=pred_hash,base_predictions_sha256=sha(previous),
        input_db_sha256=base['input_db_sha256'],rank_decisions_changed=0,forward_races=0,
        active_model_promoted=False,high_confidence_fully_resolved=False,
        inference='Mixture corrects probability sharpness; it does not improve winner or exact-triple hits.')
    save(out/f'confidence_evaluation_lag{lag}.json',report)
    print(canonical(dict(stage='confidence_evaluation',lag=lag,
        scores={y:{k:v['after'][k] for k in ('winner_log_loss','joint_log_loss','top_label_ece')} for y,v in years.items()})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('fit-dir','previous','output'):p.add_argument('--'+k,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True);a=p.parse_args()
    run(a.lag,a.fit_dir,a.previous,a.output)
