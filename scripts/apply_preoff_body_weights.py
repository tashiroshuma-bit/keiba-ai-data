"""Attach observed preoff references to a NEW snapshot, never edit fixed p's."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from preoff_body_weight import attach


def apply(data, observations, now, final=False, date=None):
    records=observations['races']; by_key={(r['date'],r['race']):r for r in records}
    if len(by_key)!=len(records):raise ValueError('duplicate race observation')
    out=dict(data); out['races']=[]
    targets=[r for r in data['races'] if date is None or r['date']==date]
    if not targets:raise ValueError('no races for requested date')
    known={(r['date'],r['race']) for r in targets}
    if set(by_key)-known:raise ValueError('observations outside selected races')
    for race in targets:
        observation=by_key.get((race['date'],race['race']),{})
        out['races'].append(attach(race,observation.get('runners',[]),now,require_final=final))
    out['body_weight_review_policy']='reference_only_no_probability_coefficient'
    out['body_weight_review_created_at']=now.isoformat()
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('prediction','observations','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--date');p.add_argument('--final-reference',action='store_true')
    a=p.parse_args()
    if a.output.exists():raise ValueError('immutable output exists')
    data=json.loads(a.prediction.read_text());obs=json.loads(a.observations.read_text())
    out=apply(data,obs,dt.datetime.now(dt.timezone.utc),a.final_reference,a.date)
    out['parent_prediction_sha256']=hashlib.sha256(a.prediction.read_bytes()).hexdigest()
    out['body_weight_observations_sha256']=hashlib.sha256(a.observations.read_bytes()).hexdigest()
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
