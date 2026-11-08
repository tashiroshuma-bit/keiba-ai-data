#!/usr/bin/env python3
"""Reproducible independent horse/jockey point-in-time research retraining.

Results of a race are added to features only on dates at least two calendar days
later. No same-day results, race-final odds, race-final speed or post-race going
are used for the forecast target itself. Race static entries known pre-off are
sourced from results PDFs and their publication timing is not independently
proven; all outputs are experimental, not canonical v50 production.
"""
from __future__ import annotations
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sqlite3,json,datetime as dt,math,hashlib,collections,random
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

DB=Path(os.environ.get('KEIBA_CANONICAL_DB','/mnt/data/keiba/jra_2023_2025.sqlite'))
OUT=Path(os.environ.get('KEIBA_RETRAIN_OUTPUT_DIR','/mnt/data/keiba'))
# v11 appends postrace Nov8 podium audit only, without touching historical training tables.
EXPECTED_DB_SHA256='7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627'
PREVIOUS_DB_SHA256='5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc'
def verify_canonical_database():
    digest=hashlib.sha256()
    with DB.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):
            digest.update(chunk)
    if digest.hexdigest()!=EXPECTED_DB_SHA256:
        raise ValueError('canonical DB SHA256 mismatch; abort retraining')
FEATURES=['horse_win','horse_place','horse_recent','horse_n_log', 'horse_surface_place','horse_surface_n_log',
 'horse_distance_place','horse_distance_n_log','horse_track_place','horse_track_n_log',
 'horse_rest_log','horse_speed_prior','horse_speed_observed','horse_prior_corner_front',
 'jockey_place','jockey_n_log','jockey_residual','horse_identity_present','jockey_identity_present',
 'horse_novice','horse_prior_top3_recent','horse_prev_grade_relative',
 'age','sex_female','gate_fraction']
JST=dt.timezone(dt.timedelta(hours=9))

def blank():return dict(n=0,wins=0,place=0,score=0.,lastdate=None,recent=collections.deque(maxlen=5),
   bysurface=collections.defaultdict(lambda:[0,0]),bydist=collections.defaultdict(lambda:[0,0]),
   bytrack=collections.defaultdict(lambda:[0,0]),speed_n=0,speed_sum=0.,corner_n=0,corner_sum=0.)

def d_band(distance):return int(distance//400) if distance else None

def safe_payload(s):
 try:return json.loads(s)
 except:return {}

def fetch():
    cx=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
    cx.execute('PRAGMA query_only=ON')
    matches={}
    for raceid,payload in cx.execute('SELECT race_id,payload_json FROM pdf_performance_evidence'):
        try:
            parsed=json.loads(payload)
            matches[raceid]={int(z['horse_number']):z for z in parsed['runners']}
        except (ValueError,TypeError,KeyError):pass
    grouped=collections.defaultdict(list)
    query='''SELECT r.race_id,r.race_date,r.track,r.surface,r.distance_m,r.expected_runners,
           x.horse_number,x.horse_id,x.jockey_id,x.finish_order,x.payload_json
           FROM annual_report_races r JOIN annual_report_runners x ON r.race_id=x.race_id
           WHERE r.status='validated_result' AND r.surface IN ('turf','dirt')
           AND r.race_date>='2023-01-01' AND r.race_date<='2026-12-31'
           ORDER BY r.race_date,r.race_id,x.horse_number'''
    for rid,date,track,surface,dist,field,num,hid,jid,finish,payload in cx.execute(query):
        z=safe_payload(payload);supp=matches.get(rid,{}).get(num,{})
        grouped[(date,rid,track,surface,dist,field)].append({
            'num':int(num),'horse_id':hid,'jockey_id':jid,'finish':finish,
            'sex_age':z.get('sex_age'),'gate':z.get('gate'),
            'speed_z':supp.get('relative_speed_z'),
            'corner4':supp.get('corner4_position'),
            'final_odds':supp.get('final_win_odds')})
    cx.close()
    events=[];reasons=collections.Counter()
    for (date,rid,track,surface,dist,field),horses in sorted(grouped.items()):
        if not isinstance(field,int) or not 3<=field<=18 or len(horses)!=field:
            reasons['incomplete_roster']+=1;continue
        if len({h['num'] for h in horses})!=field:
            reasons['duplicate_horse_number']+=1;continue
        if not isinstance(dist,(int,float)) or dist<=0:
            reasons['distance_absent']+=1;continue
        winners=[k for k,h in enumerate(horses) if h['finish']==1]
        if len(winners)!=1 or not all(isinstance(h['finish'],int) and 1<=h['finish']<=field for h in horses):
            reasons['winner_or_nonfinish_invalid']+=1;continue
        if not {1,2,3}.issubset({h['finish'] for h in horses}):
            reasons['top3_invalid']+=1;continue
        events.append({'date':date,'race_id':rid,'track':track,'surface':surface,'dist':dist,
                       'horses':horses,'winner':winners[0], 'field':field})
    print('DB racing events',len(events),'skip',dict(reasons),flush=True)
    return events,dict(reasons)

def horse_feature(h,ctx,hm,jm,cut_date):
    hid=h['horse_id'];jid=h['jockey_id']
    hs=hm.get(hid) if hid else None
    js=jm.get(jid) if jid else None
    n=hs['n'] if hs else 0
    hn=lambda d,k:(d.get(k,[0,0])[1]+2)/(d.get(k,[0,0])[0]+10) if d else .2
    sn=(hs['bysurface'].get(ctx['surface'],[0,0]) if hs else [0,0])
    dn=(hs['bydist'].get(d_band(ctx['dist']),[0,0]) if hs else [0,0])
    tn=(hs['bytrack'].get(ctx['track'],[0,0]) if hs else [0,0])
    recent=list(hs['recent']) if hs else []
    rest=(cut_date-hs['lastdate']).days if hs and hs['lastdate'] else 90
    rest=max(0,min(rest,365))
    age=0;sex_f=0
    sex_age=h.get('sex_age') or ''
    import re
    age_m=re.search(r'[牡牝せ騙](\d{1,2})',sex_age)
    if age_m:age=int(age_m[1]);age=min(age,15)
    sex_f=int(sex_age.startswith('牝'))
    jp=(js['place']+3)/(js['n']+15) if js else .2
    jr=js['res_sum']/(js['n']+30) if js else 0.
    f=[(hs['wins']+1)/(n+15) if hs else 1/15,
       (hs['place']+3)/(n+15) if hs else 3/15,
       (sum(recent)+1)/(len(recent)+5) if recent else .2,
       math.log1p(n),
       (sn[1]+2)/(sn[0]+10),math.log1p(sn[0]),
       (dn[1]+2)/(dn[0]+10),math.log1p(dn[0]),
       (tn[1]+2)/(tn[0]+10),math.log1p(tn[0]),
       math.log1p(rest),
       hs['speed_sum']/hs['speed_n'] if hs and hs['speed_n'] else 0.,
       1. if hs and hs['speed_n'] else 0.,
       hs['corner_sum']/hs['corner_n'] if hs and hs['corner_n'] else 0.,
       jp,math.log1p(js['n'] if js else 0),jr,
       1. if hid else 0.,1. if jid else 0.,
       1. if n<=1 else 0.,
       sum(recent[-3:])/max(len(recent[-3:]),1) if recent else 0.,
       (hs['score']/n if n else 0.) if hs else 0.,
       age,sex_f, h['num']/ctx['field']]
    return f

def add_event(ev,hm,jm):
    # rider residual is computed from the pre-off horse expectation saved at
    # feature extraction, NOT from the newly observed result itself.
    for h in ev['horses']:
        hid=h['horse_id'];jid=h['jockey_id'];finish=h['finish']
        win=int(finish==1);top=int(finish<=3)
        weighted={1:1.,2:.5,3:.25}.get(finish,0.)
        if jid:
            if jid not in jm:jm[jid]=dict(n=0,place=0,res_sum=0.)
            j=jm[jid];j['n']+=1;j['place']+=top
            j['res_sum']+=top-h['prehorse_place']
        if hid:
            if hid not in hm:hm[hid]=blank()
            t=hm[hid];t['n']+=1;t['wins']+=win;t['place']+=top;t['score']+=weighted
            t['recent'].append(weighted);t['lastdate']=dt.date.fromisoformat(ev['date'])
            for key,bucket in ((ev['surface'],t['bysurface']),
                                (d_band(ev['dist']),t['bydist']),
                                (ev['track'],t['bytrack'])):
                bucket[key][0]+=1;bucket[key][1]+=top
            z=h.get('speed_z')
            if z is not None:
                try:
                    z=float(z)
                    if math.isfinite(z):t['speed_n']+=1;t['speed_sum']+=z
                except (TypeError,ValueError):pass
            z=h.get('corner4')
            if z is not None:
                try:
                    z=float(z)/ev['field']
                    if math.isfinite(z):t['corner_n']+=1;t['corner_sum']+=1-z
                except (TypeError,ValueError):pass

def create_rows(events):
    hm={};jm={};queue=collections.deque();rows=[];audit=collections.Counter()
    for ev in events:
        at=dt.date.fromisoformat(ev['date'])
        boundary=at-dt.timedelta(days=2)
        while queue and dt.date.fromisoformat(queue[0]['date'])<=boundary:
            add_event(queue.popleft(),hm,jm)
        X=[]
        for h in ev['horses']:
            X.append(horse_feature(h,ev,hm,jm,at))
            hs=hm.get(h['horse_id']) if h['horse_id'] else None
            h['prehorse_place']=(hs['place']+3)/(hs['n']+15) if hs else .2
            h['known_prior_starts']=hs['n'] if hs else 0
            audit['horse_linked']+=bool(h['horse_id'])
            audit['jockey_linked']+=bool(h['jockey_id'])
            audit['horse_history_observed']+=bool(hs and hs['n']>0)
        queue.append(ev)
        X=np.asarray(X,dtype=float)
        if not np.isfinite(X).all():raise ValueError('nonfinite')
        # Relative features inside a race; group-constant metadata is not
        # useful in a conditional multinomial regression without interactions.
        X=X-X.mean(axis=0)
        field=ev['field'];post_odds=[h['final_odds'] for h in ev['horses']]
        ranks=None
        if all(isinstance(x,(int,float)) and x>0 for x in post_odds):
            ranks=sorted(range(field),key=lambda i:(post_odds[i],ev['horses'][i]['num']))
        rows.append({'date':ev['date'],'race_id':ev['race_id'],'track':ev['track'],
             'surface':ev['surface'],'field':field,'winner':ev['winner'],'X':X,
             'postrace_winner_popularity':ranks.index(ev['winner'])+1 if ranks else None,
             'horse_unknown_frac':sum(h['horse_id'] is None for h in ev['horses'])/field,
             'juvenile_or_new_frac':sum(h['known_prior_starts']<=1 for h in ev['horses'])/field})
    print('rows with leak guard',len(rows),dict(audit),flush=True)
    return rows,dict(audit)

def arrays(rows,mean=None,scale=None):
    n=len(rows);s=max(len(r['X']) for r in rows);d=len(FEATURES)
    m=np.zeros((n,s,d),dtype=np.float64);mask=np.zeros((n,s),dtype=bool)
    target=np.array([r['winner'] for r in rows]);Xtrain=np.concatenate([r['X'] for r in rows],axis=0)
    if mean is None:mean=Xtrain.mean(axis=0)
    if scale is None:scale=np.maximum(Xtrain.std(axis=0),.05)
    for i,r in enumerate(rows):
        k=len(r['X']);m[i,:k,:]=(r['X']-mean)/scale;mask[i,:k]=True
    return (m,mask,target,np.asarray(mean),np.asarray(scale))

def run_fit(train,ridge,features=None,scale_params=None):
    base=arrays(train) if scale_params is None else arrays(train,*scale_params)
    x,mask,winner,mean,scale=base
    if features is not None:
        x=x[:,:,features]
    dims=x.shape[-1]
    def loss(w):
        scores=x@w
        scores=np.where(mask,scores,-1e6)
        scores-=scores.max(axis=1,keepdims=True)
        expo=np.exp(scores)*mask
        p=expo/expo.sum(axis=1,keepdims=True)
        ll=-np.log(np.maximum(p[np.arange(len(winner)),winner],1e-30)).mean()
        diff=p.copy();diff[np.arange(len(winner)),winner]-=1
        gradient=np.einsum('ns,nsd->d',diff,x)/len(winner)
        return float(ll+.5*ridge*np.dot(w,w)),gradient+ridge*w
    opt=minimize(loss,np.zeros(dims),jac=True,method='L-BFGS-B',options={'maxiter':170,'ftol':1e-11})
    if not opt.success and np.linalg.norm(opt.jac)>1e-4:raise RuntimeError('fit failure '+str(opt.message))
    return {'weights':opt.x,'mean':mean,'scale':scale,'features':features,
      'iterations':int(opt.nit),'objective':float(opt.fun),'ridge':ridge}

def predict(rows,model):
    x,mask,w,_,_=arrays(rows,model['mean'],model['scale'])
    if model['features'] is not None:x=x[:,:,model['features']]
    v=x@model['weights'];v=np.where(mask,v,-1e6)
    v-=v.max(axis=1,keepdims=True)
    ex=np.exp(v)*mask
    return ex/ex.sum(axis=1,keepdims=True)

def score(rows,p):
    w=np.array([r['winner'] for r in rows]);a=np.arange(len(w))
    ranks=np.argsort(-p,axis=1,kind='stable')
    top1=int(np.sum(ranks[:,0]==w));top3=int(np.sum((ranks[:,:3]==w[:,None]).any(axis=1)))
    logloss=float(-np.log(np.maximum(p[a,w],1e-12)).mean())
    brier=float(np.sum(p*p,axis=1).mean()+1-2*p[a,w].mean())
    return {'n':len(rows),'top1':top1,'top1_rate':top1/len(rows),
      'winner_top3':top3,'winner_top3_rate':top3/len(rows),
      'logloss':round(logloss,6),'brier':round(brier,6),
      'predicted_favorite_mean':round(float(p[a,ranks[:,0]].mean()),6)}

def strata(rows,p):
    rank=np.argsort(-p,axis=1,kind='stable')
    groups=collections.defaultdict(list)
    for i,r in enumerate(rows):
        n=r['field'];scores=p[i,:n]
        ent=-sum(x*math.log(x) for x in scores if x>0)/math.log(n)
        top=float(scores[rank[i,0]]);gap=top-float(scores[rank[i,1]])
        flagged=[('field', '14+' if n>=14 else '<=9' if n<=9 else '10-13'),
         ('model_top1_probability','<15%' if top<.15 else '15-30%' if top<.30 else '>=30%'),
         ('model_gap','<2pp' if gap<.02 else '2-6pp' if gap<.06 else '>=6pp'),
         ('model_entropy','>=.95' if ent>=.95 else '.85-.95' if ent>=.85 else '<.85'),
         ('track',r['track']),('surface',r['surface']),
         ('no_verified_horse_ids','>=50%' if r['horse_unknown_frac']>=.5 else '<50%'),
         ('prior_history_missing','>=50%' if r['juvenile_or_new_frac']>=.5 else '<50%'),
         ('winner_final_popularity','1st' if r['postrace_winner_popularity']==1 else
          '2nd-3rd' if r['postrace_winner_popularity'] and r['postrace_winner_popularity']<=3 else
          '4th+' if r['postrace_winner_popularity'] else 'unknown')]
        for label,b in flagged:groups[(label,b)].append(i)
    result={}
    for (k,b),ids in groups.items():
        selected=[rows[i] for i in ids]
        v=score(selected,np.asarray(p)[ids]);result.setdefault(k,{})[b]=v
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    verify_canonical_database()
    events,skips=fetch();rows,coverage=create_rows(events)
    peryear=collections.defaultdict(list)
    for r in rows:peryear[r['date'][:4]].append(r)
    print('year counts', {k:len(v) for k,v in peryear.items()},flush=True)
    first=peryear['2023'];inner=peryear['2024'];validation=peryear['2025'];test=peryear['2026']
    if min(map(len,(first,inner,validation,test)))<1800:raise ValueError('historical coverage insufficient')
    # Fixed hyperparam search from 2023 training to 2024 validation only.
    tuning=[]
    for ridge in (.01,.05,.20,1.):
        for subset in ('horse_jockey','full'):
            fields=list(range(0,18)) if subset=='horse_jockey' else None
            model=run_fit(first,ridge,fields)
            metric=score(inner,predict(inner,model))
            tuning.append({'ridge':ridge,'subset':subset,'metrics':metric})
    selected=max(tuning,key=lambda x:(x['metrics']['top1'],x['metrics']['winner_top3'],-x['metrics']['logloss']))
    train=first+inner
    fidx=list(range(0,18)) if selected['subset']=='horse_jockey' else None
    selected_model=run_fit(train,selected['ridge'],fidx)
    simple=run_fit(train,.20,list(range(0,18)))
    uniform={'weights':np.zeros(len(FEATURES)),'mean':np.zeros(len(FEATURES)),
      'scale':np.ones(len(FEATURES)),'features':None,'ridge':0}
    metrics={}
    outliers={}
    for year,cohort in [('2025',validation),('2026',test)]:
        metrics[year]={}
        for label,model in [('uniform',uniform),('historical_horse_jockey',simple),('retrained_candidate',selected_model)]:
            prob=predict(cohort,model)
            metrics[year][label]=score(cohort,prob)
        prob=predict(cohort,selected_model)
        outliers[year]=strata(cohort,prob)
        ranks=np.argsort(-prob,axis=1,kind='stable')
        details=[]
        for i,r in enumerate(cohort):
            n=r['field'];y=r['winner'];p=prob[i,:n]
            details.append({'race_id':r['race_id'],'date':r['date'],'venue':r['track'],
              'surface':r['surface'],'field':n,'winner_model_rank':int(np.where(ranks[i,:n]==y)[0][0])+1,
              'top1_probability':round(float(max(p)),6),'winning_probability':round(float(p[y]),6),
              'winner_final_popularity':r['postrace_winner_popularity'],
              'horse_ids_missing_fraction':round(float(r['horse_unknown_frac']),3)})
        (OUT/f'retrained_asof_{year}_race_errors.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
    # Important: this is NOT a genuine replay of the old v50: different feature
    # construction, training dates, and research-only publication assumptions.
    payload={'schema':'jra-canonical-db-v10-temporal-horse-jockey-retrain-v1',
      'source_db_sha256':EXPECTED_DB_SHA256,
      'validated_source_races_by_year':{y:len(v) for y,v in peryear.items()},
      'roster_skips':skips,'training_coverage':coverage,
      'training_period':['2023','2024'], 'hyperparameter_selection':'2023 train, 2024 selection only',
      'model_selection_grid':tuning,'selected':selected,
      'research_model':{'feature_names':FEATURES,'selected_features':fidx,
        'coefficients':list(map(float,selected_model['weights'])),
        'mean':list(map(float,selected_model['mean'])),
        'scale':list(map(float,selected_model['scale'])),
        'ridge':selected_model['ridge'],'iterations':selected_model['iterations']},
      'validation_holdout_metrics':metrics,'weak_race_categories':outliers,
      'probability_status':'research_only_not_independently_calibrated',
      'canonical_v50_production_modified':False,
      'limitations':['Same canonical v10 DB as PROJECT_STATE, hashed exact.',
          'Publication of source races assumed two calendar days later, not original PDF publication proven.',
          'Some horse IDs are missing; no names-only inferred horse linkage.',
          'Rider official IDs may have been attached in later 2026 evidence, research only.',
          'Current race live odds, final odds, result speed, finish, current going excluded from inputs.',
          'Current race distance/gate/field taken from postrace archive, independently preoff capture not proven.',
          'This is newly trained experimental horse-jockey model, not actual v50 base feature replay.',
          '2025 and 2026 datasets used as independent held-out evaluations only.']}
    file=OUT/'retrained_canonical_db_v10_horse_jockey_research.json'
    file.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    lines=['# JRA 正本DB v10｜馬・騎手能力モデル再学習と苦手レース診断','',
      '正本SHA256: '+payload['source_db_sha256'],'',
      '研究用再学習。2023学習→2024係数選択→2023-24で再学習→2025/2026で固定評価。','',
      f'対象レース：{payload["validated_source_races_by_year"]}。','',
      f'選択された設定：{selected["subset"]}, L2={selected["ridge"]}。','',
      '## 未学習年度別の精度','',
      '|年度|方式|件数|本命的中|勝馬上位3捕捉|LogLoss|Brier|',
      '|---|---|---:|---:|---:|---:|---:|']
    for year,d in metrics.items():
        for name,v in d.items():
            lines.append(f'|{year}|{name}|{v["n"]}|{v["top1"]}/{v["n"]} ({v["top1_rate"]:.1%})|{v["winner_top3"]}/{v["n"]} ({v["winner_top3_rate"]:.1%})|{v["logloss"]:.3f}|{v["brier"]:.3f}|')
    for year,cuts in outliers.items():
        lines+=['',f'## {year}年の研究モデルが苦手な条件','',
                '|条件項目|区分|件数|1着的中|勝ち馬上位3捕捉|モデルの本命平均勝率|',
                '|---|---|---:|---:|---:|---:|']
        for k in ('field','model_top1_probability','model_gap','model_entropy','no_verified_horse_ids','prior_history_missing','surface','track','winner_final_popularity'):
            for band,v in sorted(cuts[k].items()):
                lines.append(f'|{k}|{band}|{v["n"]}|{v["top1"]}/{v["n"]} ({v["top1_rate"]:.1%})|{v["winner_top3"]}/{v["n"]} ({v["winner_top3_rate"]:.1%})|{v["predicted_favorite_mean"]:.1%}|')
    lines+=['','## 制約','']+['- '+v for v in payload['limitations']]
    (OUT/'retrained_canonical_db_v10_horse_jockey_research.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':'trained_real_canonical_db','model_selection':selected,
       'metrics':metrics,'coverage':payload['validated_source_races_by_year']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
