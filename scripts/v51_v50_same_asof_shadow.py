"""Strict same-race, same-source-A, same-asof v50 vs fitted v51 research shadow.

Fail closed on absent actual frozen v50 source A, identity proof, future/final
historical inputs, roster mismatch, data leakage or untrained stage model.
Accept independently archived JRA official outcomes for postrace evaluation.
No v51 production promotion and no v50 output mutation.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np
try:
    from scripts.v51_recovered_id_conditional_rank import make_race_probabilities,softmax
except ModuleNotFoundError:
    from v51_recovered_id_conditional_rank import make_race_probabilities,softmax

EXPECTED_MODEL_SCHEMA='jra-v51-recovered-id-learned-conditional-rank-research-v1'
EXPECTED_DB='5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd'
def timestamp(s):
    t=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('timezone required')
    return t.astimezone(dt.timezone.utc)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for x in iter(lambda:f.read(2**20),b''):h.update(x)
    return h.hexdigest()
def immutable_write(path,content):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8') as f:json.dump(content,f,ensure_ascii=False,indent=2);f.write('\n')
    return sha(p)
def roster(rows,key):
    if not isinstance(rows,list) or len(rows)<3:raise ValueError('full field of three or more horses')
    d={str(x[key]):x for x in rows}
    if len(d)!=len(rows):raise ValueError('duplicated horse in field')
    return d

def forecast(v50,features,artifact):
    if artifact.get('schema')!=EXPECTED_MODEL_SCHEMA or artifact.get('mode')!='full' or artifact.get('production_enabled') is not False:
        raise ValueError('must use fitted v51 v12 restored-ID research artifact')
    if artifact.get('canonical_db_sha256')!=EXPECTED_DB:
        raise ValueError('fitted model provenance DB mismatch')
    if v50.get('version')!='v50' or v50.get('standard_forecast') is not True or v50.get('canonical_database_sha256')!=EXPECTED_DB:
        raise ValueError('official v50 version and v12 canonical SHA required')
    if not isinstance(v50.get('forecast_sha256'),str) or len(v50['forecast_sha256'])!=64:
        raise ValueError('frozen original A source SHA required')
    if features.get('schema')!='jra-v51-same-asof-full-field-features-v1':raise ValueError('feature manifest schema invalid')
    if features.get('source_A_sha256')!=v50['forecast_sha256'] or features.get('canonical_database_sha256')!=EXPECTED_DB:
        raise ValueError('v51 features and v50 base A or database do not share exact source')
    if timestamp(v50['forecast_asof'])!=timestamp(features['forecast_asof']):
        raise ValueError('feature asof differs from original v50 asof')
    asof=timestamp(v50['forecast_asof'])
    inputs=features.get('races')
    if not isinstance(inputs,list):raise ValueError('features missing complete race list')
    by={r['race']:r for r in inputs}
    base={r['race']:r for r in v50['races']}
    if len(by)!=len(inputs) or len(base)!=len(v50['races']) or set(by)!=set(base):
        raise ValueError('exact race sets required')
    dim=len(artifact['feature_names']);mu=np.asarray(artifact['feature_mean']);scale=np.asarray(artifact['feature_scale'])
    weights=np.asarray(artifact['stage_coefficients'])
    if dim!=31 or weights.shape!=(3,dim) or mu.shape!=(dim,) or scale.shape!=(dim,) or not np.all(np.isfinite(weights)) or (scale<=0).any():
        raise ValueError('v51 learned rank artifact malformed')
    out=[]
    for race in sorted(by):
        bb=base[race];ff=by[race]
        off=timestamp(ff['race_off_at'])
        if not asof<off:raise ValueError('prediction cannot be frozen after race off')
        if timestamp(ff['features_generated_at'])>asof:
            raise ValueError('research features were only generated after v50 freeze')
        source_rows=roster(ff['horses'],'number');brows=roster(bb['v50']['horses'],'number')
        if set(source_rows)!=set(brows):raise ValueError('horse field mismatch')
        numbers=sorted(source_rows,key=lambda s:int(s));vec=[];p50=[]
        for num in numbers:
            r=source_rows[num];b=brows[num]
            if r['name']!=b['name']:raise ValueError('horse name mismatch')
            proof=r.get('official_identity_proof')
            if not isinstance(proof,dict) or proof.get('horse_id')!=r.get('horse_id') or proof.get('horse_number')!=int(num):
                raise ValueError('horse ID evidence missing or mismatched')
            if not str(proof.get('source_url','')).startswith('https://www.jra.go.jp/') or len(str(proof.get('source_sha256','')))!=64:
                raise ValueError('official JRA original identity source URL and sha required')
            if timestamp(proof['observed_at'])>asof or timestamp(r['features_observed_at'])>asof:
                raise ValueError('identity or features observed after v50 original asof')
            if str(r['latest_history_date'])>=off.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat():
                raise ValueError('same-day or future race result in horse features')
            v=r.get('feature_values');
            if not isinstance(v,list) or len(v)!=dim or any(type(x) not in (float,int) or not math.isfinite(x) for x in v):
                raise ValueError('complete finite learned feature vector required')
            vec.append(v);p50.append(float(b['p1']))
        if any(x<=0 or not math.isfinite(x) for x in p50) or abs(sum(p50)-1)>1e-5:
            raise ValueError('v50 full probability field invalid')
        feats=(np.array(vec,dtype=float)-mu)/scale
        stage=[feats@row for row in weights]
        prob=make_race_probabilities(stage,artifact['calibration'])
        out.append({'race':race,'original_off_at':ff['race_off_at'],
             'runners':[{'number':int(n),'name':source_rows[n]['name'],'horse_id':source_rows[n]['horse_id'],
                         'v50_p1':p50[i], 'v51_p1':float(prob['p1'][i]),
                         'v51_p2':float(prob['p2'][i]), 'v51_p3':float(prob['p3'][i]),
                         'v51_top3_probability':float(prob['top3_sum'][i])}
                        for i,n in enumerate(numbers)],
             'v50_p1_sorted_top3':[int(n) for n in sorted(numbers,key=lambda n:(-p50[numbers.index(n)],int(n)))[:3]],
             'v51_p1_winner':int(numbers[np.argmax(prob['p1'])]),
             'v51_learned_ordered_top3':[int(numbers[i]) for i in prob['ordered_pick']],
             'v51_learned_unordered_top3':sorted(int(numbers[i]) for i in prob['unordered_pick']),
             'v51_ordered_top3_probability':prob['ordered_pick_probability'],
             'v51_unordered_top3_probability':prob['unordered_pick_probability'],
             'v51_normalized_entropy':prob['entropy'],
             'v51_calibration_stratum':prob['calibration_stratum']})
    return {'schema':'jra-v50-v51-real-preoff-same-asof-research-shadow-v1',
        'status':'RESEARCH_ONLY_V50_UNCHANGED_NO_PROMOTION','v50_original_asof':v50['forecast_asof'],
        'original_A_source_sha256':v50['forecast_sha256'],'v51_features_source_A_sha256':features['source_A_sha256'],
        'canonical_db_sha256':EXPECTED_DB,'model_identity':'v51-recovered-ids-learned-conditional-3-stage',
        'models_share_same_asof':True,'production_model':'v50','v51_promoted':False,
        'races':out}

def postrace(paired,results):
    if paired.get('schema')!='jra-v50-v51-real-preoff-same-asof-research-shadow-v1':
        raise ValueError('only signed freeze-paired v50 and v51 forecast')
    base={r['race']:r for r in paired['races']};actual={r['race']:r for r in results['races']}
    if set(base)!=set(actual) or len(actual)!=len(results['races']):raise ValueError('result set mismatch')
    rows=[]
    for key in sorted(base):
        race=base[key];result=actual[key]
        if not timestamp(paired['v50_original_asof'])<timestamp(race['original_off_at'])<timestamp(results['observed_at']):
            raise ValueError('real prediction and official result timing mismatch')
        horses=roster(race['runners'],'number')
        order=[str(x) for x in result['finish_order']]
        if len(order)!=len(horses) or len(set(order))!=len(horses) or set(order)!=set(horses):
            raise ValueError('complete official result full horse roster required')
        winner=order[0];topthree=order[:3]
        p50={k:float(h['v50_p1']) for k,h in horses.items()}
        p51={k:float(h['v51_p1']) for k,h in horses.items()}
        ordered51=[str(x) for x in race['v51_learned_ordered_top3']]
        set51=[str(x) for x in race['v51_learned_unordered_top3']]
        set50=[str(x) for x in race['v50_p1_sorted_top3']]
        row={'race':key,'date':race['original_off_at'][:10]}
        for label,p,top1,three,ordered in (
            ('v50',p50,max(sorted(p50,key=int),key=p50.get),set50,set50),
            ('v51',p51,str(race['v51_p1_winner']),set51,ordered51)):
            confidence=max(p.values());ent=-sum(v*math.log(v) for v in p.values())/math.log(len(p))
            row[label]={'winner_hit':int(top1==winner),
               'winner_in_top3':int(winner in three),'unordered_podium_exact':int(set(three)==set(topthree)),
               'ordered_podium_exact':int(ordered==topthree),
               'winner_logloss':-math.log(max(1e-15,p[winner])),
               'winner_brier':sum((v-int(k==winner))**2 for k,v in p.items()),
               'confidence':confidence,'entropy':ent}
        rows.append(row)
    summary={}
    for label in ('v50','v51'):
        summary[label]={k:sum(x[label][k] for x in rows)/len(rows)
                        for k in ('winner_hit','winner_in_top3','unordered_podium_exact',
                                  'ordered_podium_exact','winner_logloss','winner_brier')}
        groups=defaultdict(list)
        for x in rows:
            for a,b in (('confidence','<0.15' if x[label]['confidence']<.15 else '<0.25' if x[label]['confidence']<.25 else '>=0.25'),
                        ('entropy','high' if x[label]['entropy']>=.94 else 'other')):
                groups[(a,b)].append(x[label])
        summary[label]['calibration_by_band']=[{'axis':a,'bucket':b,'n':len(v),
              'forecast_confidence':sum(y['confidence'] for y in v)/len(v),
              'observed_winner_hit':sum(y['winner_hit'] for y in v)/len(v)}
              for (a,b),v in sorted(groups.items())]
    return {'schema':'jra-v50-v51-real-paired-postrace-audit-v1','n_races':len(rows),
        'v50_is_standard':True,'v51_research_only':True,
        'metrics':summary,'v51_minus_v50':{k:summary['v51'][k]-summary['v50'][k]
          for k in ('winner_hit','winner_in_top3','unordered_podium_exact',
                                  'ordered_podium_exact','winner_logloss','winner_brier')},
        'race_audit':rows,
        'limits':['v50 ordered trio is p1 sorting proxy, v51 uses learned conditional ordered podium',
                  'comparing historical identity and actual source asof is not inferred from postrace timestamps',
                  'no promotion or new betting claim']}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--v50',required=True);p.add_argument('--features',required=True)
    p.add_argument('--model',required=True);p.add_argument('--output',required=True)
    p.add_argument('--official-results');p.add_argument('--postrace-output')
    a=p.parse_args()
    v50=json.loads(Path(a.v50).read_bytes());feat=json.loads(Path(a.features).read_bytes());model=json.loads(Path(a.model).read_bytes())
    s=forecast(v50,feat,model)
    h=immutable_write(a.output,s)
    print(json.dumps({'v51_research_shadow':'FROZEN','races':len(s['races']),'sha256':h}))
    if a.official_results:
        if not a.postrace_output:raise ValueError('postrace output required')
        results=json.loads(Path(a.official_results).read_bytes())
        t=postrace(s,results);print(json.dumps({'postrace':immutable_write(a.postrace_output,t),'n':t['n_races']}))
if __name__=='__main__':main()