"""Recount the saved horse/jockey catalogue and verify source identities."""
import argparse
import json
import math
from pathlib import Path
from completion_validation import sha
from validation import canonical

ROOT=Path(__file__).resolve().parent


def verify(folder):
    folder=Path(folder).resolve();snapshot=json.loads((folder/'snapshot.json').read_text())
    counts={};support={};rows={}
    for kind in ('horse','jockey'):
        entities=[]
        for name,item in snapshot['inventory'].items():
            path=(folder/name).resolve()
            if not path.is_relative_to(folder) or sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
                raise ValueError('catalogue changed')
            if not name.startswith(kind+'_indices_'):continue
            part=json.loads(path.read_text())
            if len(part)!=item['entities']:raise ValueError('shard count differs')
            entities.extend(part)
        if len({r['id'] for r in entities})!=len(entities):raise ValueError('duplicate entity ID')
        for r in entities:
            n=r['adjusted_starts'];penalty=snapshot['audit']['settings'][kind+'_penalty']
            if not 0<=n<=r['observed_starts'] or abs(r['sample_support']-n/(n+penalty))>1e-12:
                raise ValueError('sample support differs')
            if bool(n)!=(r['indices'] is not None):raise ValueError('unknown index was fabricated')
            for value in (r['indices'] or {}).values():
                if not math.isfinite(value) or not 0<=value<=100:raise ValueError('invalid score')
            for key in ('win_rate','top2_rate','top3_rate'):
                if not 0<=r['overall'][key]<=1:raise ValueError('invalid observed rate')
        actual=dict(entities=len(entities),adjusted_entities=sum(r['indices'] is not None for r in entities))
        if actual!=snapshot['counts'][kind]:raise ValueError('saved counts differ')
        counts[kind]=actual;support[kind]=sum(r['adjusted_starts'] for r in entities)
        rows[kind]=sum(r['observed_starts'] for r in entities)
    if support['horse']!=support['jockey'] or support['horse']!=snapshot['audit']['adjusted_starts']:
        raise ValueError('paired adjustment support differs')
    if sha(ROOT/'ACTOR_INDICES_PROTOCOL.json')!=snapshot['protocol_sha256']:raise ValueError('protocol changed')
    for name,digest in snapshot['code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('source changed')
    if snapshot['new_probability_features_activated'] or snapshot['probability_performance_improvement_claimed']:
        raise ValueError('indices have not been prediction-validated')
    result=dict(status='PASS',snapshot_sha256=sha(folder/'snapshot.json'),counts=counts,
        descriptive_rows=rows,adjusted_support=support,solver_within_1e_4=snapshot['audit']['solver_within_1e_4'],
        unknown_indices_preserved=True,score_scale_not_probability=True)
    (folder/'verification.json').write_text(canonical(result)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True)
    print(canonical(verify(p.parse_args().folder)))
