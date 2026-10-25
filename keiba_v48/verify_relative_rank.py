"""Independently recount saved predictions and check the selected artifact identity."""
import argparse
import gzip
import json
import math
from pathlib import Path
import numpy as np
from completion_validation import sha
from validation import canonical


def verify(folder,lag):
    folder=Path(folder)
    selection=json.loads((folder/f'selection_lag{lag}.json').read_text())
    evaluation=json.loads((folder/f'evaluation_lag{lag}.json').read_text())
    inventory=json.loads((folder/f'prediction_inventory_lag{lag}.json').read_text())
    if sha(folder/f'model_lag{lag}.json')!=selection['model_sha256']:raise ValueError('model changed')
    if sha(folder/f'selection_lag{lag}.json')!=evaluation['selection_sha256']:raise ValueError('selection changed')
    rows=[]
    for name,item in inventory.items():
        path=folder/name
        if path.parent.resolve()!=folder.resolve() or sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
            raise ValueError('prediction shard changed')
        part=json.loads(gzip.decompress(path.read_bytes()))
        if len(part)!=item['races']:raise ValueError('prediction count changed')
        rows.extend(part)
    if len({r['race_id'] for r in rows})!=len(rows):raise ValueError('duplicate saved race')
    checks={}
    for year,report in evaluation['years'].items():
        cohort=[r for r in rows if r['date'][:4]==year]
        if len(cohort)!=report['races']:raise ValueError('incomplete evaluation coverage')
        checks[year]={}
        for variant in ('baseline','candidate'):
            counts=dict(winner_hit=0,ordered_all_hit=0,top3_all_hit=0)
            losses=[];briers=[]
            for row in cohort:
                r=row[variant];target=list(map(int,r['target']));numbers=list(map(int,row['horse_numbers']))
                p=np.array(r['marginal_probabilities'])
                if p.shape!=(len(numbers),3) or not np.isfinite(p).all() or (p<0).any():raise ValueError('invalid probabilities')
                if not np.allclose(p.sum(axis=0),1,atol=1e-9) or np.max(p.sum(axis=1))>1+1e-9:
                    raise ValueError('incoherent placing distribution')
                counts['winner_hit']+=int(int(r['winner_pick'])==target[0])
                counts['ordered_all_hit']+=int(list(map(int,r['ordered_pick']))==target)
                counts['top3_all_hit']+=int(set(map(int,r['top3_pick']))==set(target))
                losses.append(-math.log(p[numbers.index(target[0]),0]))
                briers.append(sum((p[i,0]-int(n==target[0]))**2 for i,n in enumerate(numbers)))
            expected=report[variant]
            for name,count in counts.items():
                if count!=round(expected[name]*len(cohort)):raise ValueError('hit recount differs')
            for name,actual in [('winner_log_loss',np.mean(losses)),('winner_brier_sum',np.mean(briers))]:
                if abs(expected[name]-actual)>1e-12:raise ValueError('probability score recount differs')
            checks[year][variant]=dict(races=len(cohort),**counts)
    result=dict(status='PASS',lag_days=lag,races=len(rows),checks=checks,
        selected=selection['selected'],model_sha256=selection['model_sha256'],
        full_saved_probability_coverage=True,independent_counts_match=True)
    (folder/f'verification_lag{lag}.json').write_text(canonical(result)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();print(canonical(verify(a.folder,a.lag)))
