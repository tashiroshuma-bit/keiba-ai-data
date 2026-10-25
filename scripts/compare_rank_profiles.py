"""Freeze incumbent and challenger research forecasts on exactly the same card."""
import argparse
import hashlib
import json
from pathlib import Path
from forecast_rank_profile import create,ROOT
from completion_validation import sha
from validation import Ledger,canonical


def compare(db,rows,baseline_profile,candidate_profile,lag):
    baseline=create(db,rows,baseline_profile,lag)
    candidate=create(db,rows,candidate_profile,lag)
    if (baseline['race_id']!=candidate['race_id'] or baseline['off_timestamp']!=candidate['off_timestamp'] or
        [r['horse_number'] for r in baseline['runners']]!=[r['horse_number'] for r in candidate['runners']]):
        raise ValueError('paired forecasts require the same complete active field')
    comparison_id=hashlib.sha256(canonical(dict(rows=rows,models=[baseline['model_sha256'],candidate['model_sha256']])).encode()).hexdigest()
    return dict(schema='paired-rank-shadow-v1',comparison_id=comparison_id,input_sha256=hashlib.sha256(canonical(rows).encode()).hexdigest(),
        status='RESEARCH_PAIR_NOT_PRODUCTION',baseline=baseline,candidate=candidate)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','runners','ledger','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--baseline-profile',default=str(ROOT/'operations/prediction_policy/observed_history_rank.json'))
    p.add_argument('--candidate-profile',default=str(ROOT/'operations/prediction_policy/evidence_rank_shadow.json'))
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();output=Path(a.output)
    if output.exists():raise ValueError('new immutable comparison output required')
    profiles=[json.loads(Path(path).read_text()) for path in (a.baseline_profile,a.candidate_profile)]
    result=compare(a.db,json.loads(Path(a.runners).read_text()),*profiles,a.lag)
    for label,profile in zip(('baseline','candidate'),profiles):
        model=json.loads((ROOT/profile['lags'][str(a.lag)]['model']['path']).read_text())
        key=Ledger(a.ledger).freeze(result[label],model,mode='forward');result[label]['prediction_id']=key
    with output.open('x') as f:f.write(canonical(result)+'\n')
    print(result['comparison_id'])
