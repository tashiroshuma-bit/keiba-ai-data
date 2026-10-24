"""Technical integration smoke: compact status -> existing trained rank model -> all bets.
DO NOT USE AS A FORECAST: this does not reconstruct the trained feature pipeline.
"""
import datetime as dt,itertools,json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from ranking_model import RankModel,NAMES
from completion_validation import sha
def cover(items,target):
    ordered=sorted(items.items(),key=lambda z:-z[1]);total=0.;out=[]
    for numbers,p in ordered:
        out.append(dict(numbers=list(numbers),p=round(float(p),9)))
        total+=p
        if total>=target:break
    return dict(target=target,coverage=round(float(total),9),count=len(out),tickets=out)
def main():
    started=time.perf_counter()
    base=Path(__file__).resolve().parents[1]
    card=json.loads((base/'operations/20261025_kikuka_roster.json').read_text())
    stat=json.loads((base/'operations/20261025_kikuka_status_compact.json').read_text())
    selection=json.loads((base/'keiba_v48/reports/exact_rank/selection_lag7.json').read_text())
    path=base/'keiba_v48/reports/exact_rank/model_lag7.json'
    assert sha(path)==selection['model_sha256']
    model=RankModel.from_dict(json.loads(path.read_text()))
    assert len(card['runners'])==len(stat['rows'])==18
    assert dt.datetime.fromisoformat(stat['asof']) <= dt.datetime.fromisoformat(card['off_timestamp'])-dt.timedelta(minutes=5)
    assert stat['source_last_race_before'] < card['off_timestamp'][:10]
    features=[]
    for h,st in zip(card['runners'],stat['rows']):
        starts,wins,seconds,thirds,last5,date,turf,kyoto=st
        values=model.mean.tolist() # Impute all unavailable features to TRAINING MEAN; not a validated reconstruction.
        ix={name:i for i,name in enumerate(NAMES)}
        values[ix['ability']]=(wins+1)/(starts+4)
        values[ix['recent_quality']]=(last5+1)/(min(5,starts)+2)
        values[ix['history_log']]=math.log1p(starts)/5
        values[ix['course_form']]=(kyoto[2]+1)/(kyoto[0]+4) if kyoto else .25
        values[ix['distance_form']]=.25 # No 3000m experience in compact status
        values[ix['rest_log']]=math.log1p(max(0,(dt.date.fromisoformat(card['off_timestamp'][:10])-dt.date.fromisoformat(date)).days))/7
        values[ix['horse_identity_missing']]=1.
        values[ix['jockey_identity_missing']]=1.
        values[ix['age_missing']]=1.
        features.append(dict(values=values,group='京都/turf',cutoff_timestamp='2026-10-25T15:35:00+09:00'))
    p,q=model.predict(features)
    n=len(features);numbers=[int(r['horse_number']) for r in card['runners']]
    assert abs(float(p[:,0].sum())-1)<1e-8 and abs(float(q.sum())-1)<1e-8
    win={(numbers[i],):float(p[i,0]) for i in range(n)}
    pair={(numbers[i],numbers[j]):float(q[i,j,:].sum()+q[j,i,:].sum()) for i in range(n) for j in range(i+1,n)}
    trio={(numbers[i],numbers[j],numbers[k]):float(sum(q[t] for t in itertools.permutations((i,j,k)))) for i,j,k in itertools.combinations(range(n),3)}
    top=sorted(range(n),key=lambda i:-float(p[i,0]))
    exact=max(itertools.permutations(range(n),3),key=lambda t:float(q[t]))
    out=dict(status='INTEGRATION_SMOKE_ONLY_NOT_VALIDATED_PREDICTION',
      warning='Model input features are mean-imputed / status approximations, not the feature extractor used in training; probabilities are not trustworthy',
      model_sha256=sha(path),source='2026-10-24 canonical DB compact status',
      run_seconds=round(time.perf_counter()-started,4),
      first_three=[numbers[i] for i in exact],
      ranked=[dict(number=numbers[i],name=card['runners'][i]['horse_name'],p1=float(p[i,0]),p2=float(p[i,1]),p3=float(p[i,2])) for i in top],
      coverage=dict(win=cover(win,.8),pair=cover(pair,.5),trio=cover(trio,.6)))
    assert all(out['coverage'][k]['coverage']>=out['coverage'][k]['target']-1e-8 for k in out['coverage'])
    target=base/'reports/20261025_v43_status_smoke';target.mkdir(parents=True,exist_ok=True)
    (target/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('INTEGRATION_PASS',out['run_seconds'],'seconds',len(out['ranked']),'horses', {k:v['count'] for k,v in out['coverage'].items()},flush=True)
if __name__=='__main__':main()
