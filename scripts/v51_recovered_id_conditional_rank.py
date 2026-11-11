"""V51 research: conditional rank model on canonical v12 horse identities.

Historical learner uses previous calendar dates only; not a frozen v50 forecast.
Train 2023-24, calibrate 2025, held-out evaluate 2026. The conditional
second and third choice stages are *learned separately* (not PL p1 proxy).
No automatic promotion, no production v50 coefficient changes.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from scipy.optimize import minimize, minimize_scalar
import numpy as np

SCHEMA="jra-v51-recovered-id-learned-conditional-rank-research-v1"
FEATURE_NAMES = None

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
    return h.hexdigest()

def history_module(path):
    spec=importlib.util.spec_from_file_location('jra_historical_ablation_source',str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def groups_for(rids,rank,years,states,races,train=False):
    groups=collections.defaultdict(list)
    for index,rid in enumerate(rids):groups[str(rid)].append(index)
    result=[]
    for rid,indices in groups.items():
        ind=np.array(indices,dtype=int)
        if train and (years[ind[0]]>2024 or states[ind[0]]!='validated_result'):continue
        num={pos:ind[rank[ind]==pos].tolist() for pos in (1,2,3)}
        if len(num[1])!=1:continue
        unique_triple=len(num[2])==1 and len(num[3])==1 and len({num[1][0],*(num[2]+num[3])})==3
        result.append({'race':rid,'date':races[rid][0]['date'],'year':int(years[ind[0]]),
                       'status':str(states[ind[0]]),'indices':ind,
                       'first':num[1][0],'second':num[2][0] if unique_triple else None,
                       'third':num[3][0] if unique_triple else None,
                       'podium_valid':unique_triple})
    return result

def stage_samples(groups,stage):
    result=[]
    for g in groups:
        if stage>1 and not g['podium_valid']:continue
        ex=[] if stage==1 else ([g['first']] if stage==2 else [g['first'],g['second']])
        inds=np.array([i for i in g['indices'] if i not in ex],dtype=np.int64)
        actual=g[('first','second','third')[stage-1]]
        if actual not in inds:raise ValueError('stage winner not eligible')
        result.append((inds,actual))
    return result

def standardized(X,train_groups):
    rows=np.concatenate([g['indices'] for g in train_groups])
    mu=X[rows].astype(np.float64).mean(axis=0)
    scale=X[rows].astype(np.float64).std(axis=0)
    scale=np.where(scale>1e-6,scale,1.0)
    return (X-mu)/scale,mu,scale

def fit_conditional_stage(X, samples, ridge=.01,maxiter=150):
    eligible=np.concatenate([ind for ind,target in samples]); actual=np.array([target for ind,target in samples])
    offsets=np.cumsum(np.r_[0,[len(ind) for ind,target in samples]])
    lengths=np.diff(offsets)
    chosen=X[actual].sum(axis=0)
    full=X[eligible]
    n=len(samples)
    def objective(w):
        z=full@w
        maximum=np.maximum.reduceat(z,offsets[:-1])
        ex=np.exp(z-np.repeat(maximum,lengths))
        totals=np.add.reduceat(ex,offsets[:-1]);prob=ex/np.repeat(totals,lengths)
        nll=(np.sum(maximum+np.log(totals))-np.sum(X[actual]@w))/n+0.5*ridge*sum(w*w)
        grad=(full.T@prob-chosen)/n+ridge*w
        return float(nll),grad
    opt=minimize(objective,np.zeros(X.shape[1]),jac=True,method='L-BFGS-B',options={'maxiter':maxiter,'ftol':1e-9})
    if not opt.success and opt.jac.dot(opt.jac)>1e-7:
        raise RuntimeError('conditional rank optimizer failed '+opt.message)
    return opt.x, {'race_sets':n,'eligible_rows':len(eligible),'optimization_nll_penalized':float(opt.fun),
                   'optimizer_success':bool(opt.success),'iterations':int(opt.nit),'gradient_norm':float(np.linalg.norm(opt.jac))}

def softmax(z,temp=1.0):
    z=np.asarray(z,dtype=np.float64)/float(temp)
    m=z.max();p=np.exp(z-m);return p/p.sum()

def entropy(probs):return float(-np.sum(probs*np.log(np.maximum(1e-15,probs)))/np.log(len(probs)))

def bucket(probs):
    e=entropy(probs)
    return ('high_entropy' if e>=.94 else 'other_entropy')+'__'+('close_field' if max(probs)<.25 else 'clear_favorite')

def prepared_scores(X,group,stage_coefs):
    return [X[group['indices']]@coef for coef in stage_coefs]

def stage_ce(Z,g,stage,temp):
    if stage>1 and not g['podium_valid']:return None
    indices=g['indices'];ex=[] if stage==1 else ([g['first']] if stage==2 else [g['first'],g['second']])
    allowed=[k for k,ind in enumerate(indices) if ind not in ex]
    selected=g[('first','second','third')[stage-1]]
    local=np.where(indices==selected)[0][0];probs=softmax(Z[stage-1][allowed],temp)
    return -math.log(max(probs[allowed.index(local)],1e-15))

def temp_fit(records,stage,subset=None,base_temp=None):
    arr=[(z,g) for z,g in records if (subset is None or bucket(softmax(z[0]))==subset) and (stage==1 or g['podium_valid'])]
    if len(arr)<75:return base_temp if base_temp is not None else 1.0,len(arr)
    reg=0.0 if base_temp is None else 125
    def loss(logt):
        temp=math.exp(float(logt))
        errors=sum(stage_ce(z,g,stage,temp) for z,g in arr)
        if base_temp is not None:errors+=reg*(logt-math.log(base_temp))**2
        return errors/len(arr)
    opt=minimize_scalar(loss,bounds=(math.log(.5),math.log(3.0)),method='bounded',options={'xatol':1e-4})
    return float(math.exp(opt.x)),len(arr)

def calibrate(records):
    global_t={}
    for stage in (1,2,3):global_t[str(stage)]=temp_fit(records,stage)[0]
    group_t={}
    for key in ('high_entropy__close_field','high_entropy__clear_favorite',
                'other_entropy__close_field','other_entropy__clear_favorite'):
        t,n=temp_fit(records,1,key,global_t['1'])
        group_t[key]={'temp':t,'calibration_races':n,'fallback':n<75}
    return {'fitted_on':'2025_validated_results_only_no_2026_reuse',
            'global_stage_temperatures':global_t,'winner_entropy_confidence_groups':group_t,
            'group_entropy_cutoff':.94,'group_favorite_cutoff':.25,'minimum_group_count':75,
            'penalty_pseudoraces':125}

def make_race_probabilities(z,calibration=None):
    n=len(z[0]);raw=softmax(z[0]);cls=bucket(raw)
    if calibration:
        t1=calibration['winner_entropy_confidence_groups'][cls]['temp']
        t2=calibration['global_stage_temperatures']['2'];t3=calibration['global_stage_temperatures']['3']
    else:t1=t2=t3=1.0
    p1=softmax(z[0],t1);p2=np.zeros(n);p3=np.zeros(n);exact_unordered=collections.defaultdict(float)
    topjoint=(-1,None)
    for i in range(n):
        remaining2=np.array([j for j in range(n) if j!=i],dtype=int)
        stage2=softmax(z[1][remaining2],t2)
        for jj,j in enumerate(remaining2):
            path2=p1[i]*stage2[jj];p2[j]+=path2
            remaining3=np.array([k for k in range(n) if k!=i and k!=j],dtype=int)
            stage3=softmax(z[2][remaining3],t3)
            for kk,k in enumerate(remaining3):
                joint=path2*stage3[kk];p3[k]+=joint
                exact_unordered[tuple(sorted((i,j,k)))]+=joint
                if joint>topjoint[0]+1e-16:topjoint=(joint,(i,j,k))
    best_set=max(exact_unordered,key=lambda k:(exact_unordered[k],tuple(-i for i in k)))
    return {'p1':p1,'p2':p2,'p3':p3,'top3_sum':p1+p2+p3,
            'ordered_pick':topjoint[1],'ordered_pick_probability':topjoint[0],
            'unordered_pick':best_set,'unordered_pick_probability':exact_unordered[best_set],
            'entropy':entropy(p1),'calibration_stratum':cls,
            'joint_normalization':float(p3.sum())}

def score_group(z,g,prob,numbers):
    local={global_idx:i for i,global_idx in enumerate(g['indices'])}
    winner=local[g['first']]
    p1=prob['p1'];best=int(np.argmax(p1))
    truth=None
    if g['podium_valid']:truth=(local[g['first']],local[g['second']],local[g['third']])
    hit=int(best==winner)
    brier=float(np.sum((p1-np.eye(1,len(p1),winner)[0])**2))
    out={'race_id':g['race'],'date':g['date'],'status':g['status'],'year':g['year'],
         'field_size':len(g['indices']),'winner_num':int(numbers[g['first']]),
         'pred_winner_num':int(numbers[g['indices'][best]]),
         'p1_winner':float(p1[winner]),'pred_top1_confidence':float(p1[best]),
         'top1_hit':hit,'winner_logloss':float(-math.log(max(1e-15,p1[winner]))),
         'winner_brier':brier,'winner_in_top3_set':int(winner in prob['unordered_pick']),
         'conditional_second_logloss':stage_ce(z,g,2,1.0) if g['podium_valid'] else None,
         'podium_valid':bool(g['podium_valid']),
         'ordered_podium_hit':int(truth==prob['ordered_pick']) if truth else None,
         'unordered_podium_hit':int(set(truth)==set(prob['unordered_pick'])) if truth else None,
         'pred_ordered_numbers':[int(numbers[g['indices'][x]]) for x in prob['ordered_pick']],
         'pred_unordered_numbers':sorted(int(numbers[g['indices'][x]]) for x in prob['unordered_pick']),
         'actual_ordered_numbers':[int(numbers[g['indices'][x]]) for x in truth] if truth else None,
         'normalized_entropy':prob['entropy'],'stratum':prob['calibration_stratum'],
         'joint_sum':prob['joint_normalization']}
    return out

def summarize(recs):
    n=len(recs);valid=[r for r in recs if r['podium_valid']]
    return {'n_races':n,'unique_podium_races':len(valid),
       'top1_accuracy':sum(r['top1_hit'] for r in recs)/n,
       'top1_hits':sum(r['top1_hit'] for r in recs),
       'winner_in_recommended_trio':sum(r['winner_in_top3_set'] for r in recs)/n,
       'unordered_podium_exact':sum(r['unordered_podium_hit'] for r in valid)/len(valid) if valid else None,
       'ordered_podium_exact':sum(r['ordered_podium_hit'] for r in valid)/len(valid) if valid else None,
       'mean_logloss':sum(r['winner_logloss'] for r in recs)/n,
       'mean_brier':sum(r['winner_brier'] for r in recs)/n}

def reliability(recs):
    out={};labels=[('confidence',lambda r:next((b for b in (0.10,0.15,0.20,0.30,0.40,0.50,1.01)
                               if r['pred_top1_confidence']<b),1.01)),
                  ('entropy',lambda r:'high' if r['normalized_entropy']>=.94 else 'lower'),
                  ('mixed',lambda r:r['stratum'])]
    for axis,fun in labels:
        groups=collections.defaultdict(list)
        for r in recs:groups[str(fun(r))].append(r)
        out[axis]=[]
        for label,sub in sorted(groups.items()):
            mu=sum(r['pred_top1_confidence'] for r in sub)/len(sub)
            hit=sum(r['top1_hit'] for r in sub)/len(sub)
            out[axis].append({'bin':label,'n':len(sub),'mean_pred_confidence':mu,'observed_hit':hit,
                              'calibration_gap':hit-mu,'mean_logloss':sum(r['winner_logloss'] for r in sub)/len(sub)})
    out['ece_confidence']=sum(x['n']*abs(x['calibration_gap']) for x in out['confidence'])/len(recs)
    return out

def day_bootstrap(left,right,races_key='top1_hit',seed=20261111,iterations=1200):
    pairs=[(a['date'],float(b[races_key])-float(a[races_key])) for a,b in zip(left,right)]
    d=collections.defaultdict(list)
    for date,delta in pairs:d[date].append(delta)
    days=list(d);rng=np.random.default_rng(seed)
    samples=[]
    for _ in range(iterations):
        draw=rng.integers(len(days),size=len(days));values=[x for idx in draw for x in d[days[int(idx)]]]
        samples.append(sum(values)/len(values))
    return {'delta':float(np.mean([v for _,v in pairs])),
            'day_cluster_bootstrap95':[float(x) for x in np.quantile(samples,[.025,.975])],
            'n_dates':len(days)}

def save_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def run(database,overlay,history_script,output_dir):
    import time
    begin=time.time();hist=history_module(history_script)
    if sha(database)!='5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd':
        raise ValueError('canonical JRA v12 SHA mismatch')
    if sha(overlay)!='5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea':
        raise ValueError('1,975 official research overlay SHA mismatch')
    races,skipped=hist.build_dataset(db=database,overlay=overlay)
    selections={}
    for mode in ('masked','full'):
        X,rank,rids,states,years,numbers,winner_nums=hist.create_feature_rows(races,mode)
        allgroups=groups_for(rids,rank,years,states,races)
        traingroups=groups_for(rids,rank,years,states,races,train=True)
        feature,mean,scale=standardized(X,traingroups)
        stage_models=[];train_audit={}
        for stage in (1,2,3):
            coef,diag=fit_conditional_stage(feature,stage_samples(traingroups,stage))
            stage_models.append(coef);train_audit[str(stage)]=diag
        groups25=[g for g in allgroups if g['year']==2025 and g['status']=='validated_result']
        grouped25=[(prepared_scores(feature,g,stage_models),g) for g in groups25]
        cal=calibrate(grouped25)
        group26=[g for g in allgroups if g['year']==2026 and g['status']=='validated_result']
        details={};metrics={}
        for year,grps in ((2025,groups25),(2026,group26)):
            for cal_name,cal_obj in (('uncalibrated',None),('calibrated_on_2025',cal)):
                rec=[]
                for g in grps:
                    z=prepared_scores(feature,g,stage_models)
                    p=make_race_probabilities(z,cal_obj)
                    if abs(p['joint_normalization']-1)>1e-8 or max(abs(p['p2'].sum()-1),abs(p['p1'].sum()-1))>1e-8:
                        raise ValueError('joint podium normalization failure')
                    rec.append(score_group(z,g,p,numbers))
                tag=f'{year}_{cal_name}';details[tag]=rec
                metrics[tag]={**summarize(rec),'calibration_reliability':reliability(rec)}
        selections[mode]={'artifact':{
                'schema':SCHEMA,'mode':mode,'model_family':'conditional-three-stage-softmax-choice',
                'production_enabled':False,'v50_model_modified':False,'strict_real_preoff_forecasts_already_compared':False,
                'trained_2023_2024_validated_only':True,'calibration_2025_only':True,
                'feature_names':hist.FEATURES,'feature_count':len(hist.FEATURES),
                'feature_mean':mean.tolist(),'feature_scale':scale.tolist(),
                'stage_coefficients':[x.tolist() for x in stage_models],
                'training_stage_audit':train_audit,'calibration':cal,
                'canonical_db_sha256':sha(database),'review_overlay_sha256':sha(overlay),
                'disallowed_features':['future_same_day_results','odds_final','race_outcome_at_prediction','body_weight_postoff']},
            'metrics':metrics,'race_details':details}
        print('MODEL',mode,'training',train_audit,'2026 cal',metrics['2026_calibrated_on_2025']['top1_accuracy'],'elapsed',round(time.time()-begin,2),flush=True)
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    for mode in ('masked','full'):
        save_new(root/f'v51_rank_{mode}_trained_2023_2024_cal2025.json',selections[mode]['artifact'])
    report={'schema':'jra-real-v51-horse-id-conditional-podium-research-20261111-v1',
       'status':'RESEARCH_ONLY_NOT_V50_V51_PREOFF_PAIRED',
       'source_db_sha256':sha(database),'review_overlay_sha256':sha(overlay),
       'training':'2023-2024 validated, identical 31 features, independently fit 3 conditional stages',
       'calibration':'2025 strictly only; winner-temperature by entropy/confidence, second/third stage global temp',
       'evaluation':'2026 validated heldout, never refit or select weights/temperature on 2026',
       'modes':{m:selections[m]['metrics'] for m in selections},
       'paired_2026_calibrated':{},'limitations':[
           'The masked and full research models share feature engineering and reference data, but are not production v50. No historical same-asof source A full-field snapshots for all 2025-2026 races.',
           'Identity recovery retrospectively connects stable horses but historical PDF publication timestamps are not known; preoff availability is approximated by earlier calendar date.',
           '2025 calibration is in-sample for calibration parameters; 2026 is independent model/temperature evaluation.',
           'Cancelled / scratched / DNF and ambiguous exact podiums excluded from conditional podium training.',
           'Research 2026 evaluation is retrospective; must not claim prospective v51 live superiority.']}
    for tag in ('2026_uncalibrated','2026_calibrated_on_2025'):
        left=selections['masked']['race_details'][tag];right=selections['full']['race_details'][tag]
        if [x['race_id'] for x in left]!=[x['race_id'] for x in right]:raise ValueError('not exact matched races')
        diffs={}
        for key in ('top1_hit','winner_logloss','winner_brier'):
            diffs[key]=day_bootstrap(left,right,key,seed=20261111)
        report['paired_2026_calibrated'][tag]=diffs
    rows=[]
    for g in selections['full']['race_details']['2026_calibrated_on_2025']:
        rows.append({**g,'mode':'full'})
    with (root/'2026_v51_research_race_predictions.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save_new(root/'v51_rank_recovered_id_2026_holdout_report.json',report)
    print('DONE',time.time()-begin,'full2016',report['modes']['full']['2026_calibrated_on_2025']['top1_accuracy'])
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',required=True)
    parser.add_argument('--review-overlay',required=True)
    parser.add_argument('--historical-feature-script',required=True)
    parser.add_argument('--output-dir',required=True)
    a=parser.parse_args()
    run(a.database,a.review_overlay,a.historical_feature_script,a.output_dir)