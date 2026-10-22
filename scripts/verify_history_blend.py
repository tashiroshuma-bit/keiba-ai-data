"""Rebuild source features and independently replay coefficients and joint math."""
import argparse
import functools
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from completion_validation import pack
from enriched_features import load_archive,history_index
from history_blend_model import augment_blend
from ranking_model import top3_labels

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@functools.lru_cache(None)
def geometry(n):
    i,j,k=np.indices((n,n,n));u=((i!=j)&(i!=k)&(j!=k))/(n*(n-1)*(n-2))
    return u,np.array(list(itertools.combinations(range(n),3)))


def uniform(p,q,a):return (1-a)*p+a/len(p),(1-a)*q+a*geometry(len(p))[0]


def independent(artifact,features):
    if artifact['schema']=='keiba-history-blend-model-v1':
        legacy=[{**f,'values':f['legacy_values']} for f in features]
        a,qa=uniform(*independent(artifact['base'],legacy),artifact['base_alpha'])
        b,qb=uniform(*independent(artifact['specialist'],features),artifact['specialist_alpha'])
        w=artifact['weight'];return (1-w)*a+w*b,(1-w)*qa+w*qb
    matrix=(np.array([f['values'] for f in features])-artifact['mean'])/artifact['scale'];out=[]
    for x,f in zip(matrix,features):
        coef=np.array(artifact['weights'])
        for group in f.get('groups',[f['group']]):
            if group in artifact['offsets']:coef+=np.array(artifact['offsets'][group])
        out.append([float(np.dot(w,x)) for w in coef])
    s=np.array(out).T/artifact['temperature']
    if len(s)==1:s=np.repeat(s,3,axis=0)
    n=s.shape[1];q=np.zeros((n,n,n));first=np.exp(s[0]-s[0].max());first/=first.sum()
    for i in range(n):
        mask=np.arange(n)!=i;v=np.where(mask,s[1],-np.inf)
        second=np.where(mask,np.exp(np.clip(v-v.max(),-300,None)),0);second/=second.sum()
        mask3=mask[None,:] & ~np.eye(n,dtype=bool);v=np.where(mask3,s[2][None,:],-np.inf)
        third=np.where(mask3,np.exp(np.clip(v-v.max(axis=1,keepdims=True),-300,None)),0)
        third/=third.sum(axis=1,keepdims=True);q[i]=first[i]*second[:,None]*third
    p=np.column_stack((q.sum(axis=(1,2)),q.sum(axis=(0,2)),q.sum(axis=(0,1))))
    return p,q


def check(value,p,q,numbers,target,policy):
    actual=np.array(value['marginal_probabilities']);err=float(np.abs(actual-p).max())
    assert err<1e-11 and np.allclose(actual.sum(axis=0),1) and np.all(actual.sum(axis=1)<=1+1e-12)
    winner=numbers.index(value['winner_pick']);ordered=[numbers.index(x) for x in value['ordered_pick']]
    trio=[numbers.index(x) for x in value['top3_pick']]
    assert len(set(ordered))==len(set(trio))==3 and p[:,0].max()-p[winner,0]<1e-11
    assert q.max()-q[tuple(ordered)]<1e-11
    if policy=='exact_set':
        combinations=geometry(len(p))[1];masses=np.zeros(len(combinations))
        for perm in itertools.permutations(range(3)):masses+=q[combinations[:,perm[0]],combinations[:,perm[1]],combinations[:,perm[2]]]
        chosen=sum(q[x] for x in itertools.permutations(trio));assert masses.max()-chosen<1e-11
    else:
        sums=p.sum(axis=1);assert sum(sorted(sums,reverse=True)[:3])-sum(sums[trio])<1e-11
    assert value['target']==[numbers[i] for i in target]
    assert value['winner_hit']==int(winner==target[0])
    assert value['ordered_all_hit']==int(ordered==target)
    assert value['top3_all_hit']==int(set(trio)==set(target))
    assert abs(value['top3_recall']-len(set(trio)&set(target))/3)<1e-12
    assert abs(value['joint_target_probability']-q[tuple(target)])<1e-12
    assert abs(value['joint_log_loss']+math.log(q[tuple(target)]))<1e-10
    assert abs(value['winner_log_loss']+math.log(p[target[0],0]))<1e-10
    assert abs(value['mean_rank_log_loss']+np.mean([math.log(p[target[k],k]) for k in range(3)]))<1e-10
    return err


def verify(db,folder,previous,lag):
    folder=Path(folder);before=sha(db)
    selection=json.loads((folder/f'selection_lag{lag}.json').read_text())
    report=json.loads((folder/f'evaluation_lag{lag}.json').read_text())
    artifact=json.loads((folder/f'model_lag{lag}.json').read_text())
    assert before==selection['input_db_sha256']==report['input_db_sha256']
    for name,key in (('model','model_sha256'),('selection','selection_sha256'),('predictions','predictions_sha256')):
        path=folder/(f'{name}_lag{lag}.json'+('.gz' if name=='predictions' else ''))
        assert sha(path)==report[key]
    assert sha(previous)==report['base_predictions_sha256']
    values=json.loads(gzip.decompress((folder/f'predictions_lag{lag}.json.gz').read_bytes()))
    old={r['race_id']:r for r in json.loads(gzip.decompress(Path(previous).read_bytes()))}
    saved={r['race_id']:r for r in values};assert len(saved)==len(values)==6036
    base=json.loads((ROOT/f'keiba_v48/reports/exact_rank/model_lag{lag}.json').read_text())
    policy=json.loads((ROOT/f'keiba_v48/reports/exact_rank/selection_lag{lag}.json').read_text())['prediction_set_policy']
    history,fields,_=load_archive(db,lag,allow_unlinked_fields=True);index=history_index(history)
    error=0;checked=set();changed=0;counts={key:0 for key in ('repair_winner','repair_order','repair_set','model_winner','model_order','model_set')}
    for race in pack(index,fields):
        if race['rows'][0]['race_date'][:4] not in ('2025','2026'):continue
        try:target=top3_labels(race)
        except ValueError:continue
        r=augment_blend(race,index);v=saved[r['race_id']];checked.add(r['race_id'])
        numbers=[x['horse_number'] for x in r['rows']];assert v['horse_numbers']==numbers
        legacy=[{**f,'values':f['legacy_values']} for f in r['features']]
        p,q=uniform(*independent(base,legacy),.1)
        op=.9*np.array(old[r['race_id']]['candidate']['marginal_probabilities'])+.1/len(p)
        assert np.allclose(op,np.array(v['previous']['marginal_probabilities']),atol=1e-14,rtol=0)
        error=max(error,check(v['repaired_baseline'],p,q,numbers,target,policy));changed+=int(np.abs(op-p).max()>1e-12)
        if artifact==base:pp,qq=p,q
        else:pp,qq=uniform(*independent(artifact,r['features']),selection['alpha'])
        error=max(error,check(v['candidate'],pp,qq,numbers,target,selection['prediction_set_policy']))
        for label,a,b in (('repair','previous','repaired_baseline'),('model','repaired_baseline','candidate')):
            for short,key in (('winner','winner_pick'),('order','ordered_pick'),('set','top3_pick')):
                aa=v[a][key];bb=v[b][key]
                counts[label+'_'+short]+=int((set(aa)!=set(bb)) if short=='set' else aa!=bb)
        if len(checked)%1000==0:print(json.dumps(dict(lag=lag,checked=len(checked))),flush=True)
    assert checked==set(saved) and sha(db)==before
    for year,annual in report['years'].items():
        rows=[r for r in values if r['date'][:4]==year]
        for stage in ('previous','repaired_baseline','candidate'):
            for key in ('winner_hit','ordered_all_hit','top3_all_hit','top3_recall','winner_log_loss','mean_rank_log_loss','joint_log_loss'):
                assert abs(np.mean([r[stage][key] for r in rows])-annual[stage][key])<1e-11
    result=dict(verified=True,races=len(checked),input_db_sha256=before,selected=selection['selected'],
        model_sha256=report['model_sha256'],selection_sha256=report['selection_sha256'],predictions_sha256=report['predictions_sha256'],
        largest_independent_probability_error=error,features_rebuilt_from_canonical=True,independent_feature_implementation=False,
        independent_coefficient_and_joint_math=True,MAP_checked_with_tolerance=1e-11,repair_probability_changed_races=changed,
        changed_picks=counts,database_unchanged=True)
    (folder/f'verification_lag{lag}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('db','folder','previous'):p.add_argument('--'+k,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True);a=p.parse_args();verify(a.db,a.folder,a.previous,a.lag)
