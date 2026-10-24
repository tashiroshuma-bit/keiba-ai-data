"""Run an existing trained rank model on a complete, explicitly supplied pre-off roster.
Research shadow only: exact-name history aliases are not verified JRA horse identities.
No race outcomes, odds or post-off information are read.
"""
import argparse,datetime as dt,hashlib,itertools,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from enriched_features import load_archive,history_index,build_enriched
from ranking_model import RankModel,augment
from features import timestamp
from completion_validation import sha

JST=dt.timezone(dt.timedelta(hours=9))
def alias(name):
    return 'name:'+hashlib.sha256(name.encode('utf-8')).hexdigest()[:24]
def coverage(probs,target):
    ordered=sorted(probs.items(),key=lambda kv:(-kv[1],kv[0]))
    total=0.;out=[]
    for key,p in ordered:
        total+=p;out.append(dict(horses=list(key),probability=round(float(p),8)))
        if total+1e-12>=target:break
    return dict(target=target,count=len(out),cumulative=round(total,8),bets=out)

def run(db,roster,model_file,selection_file,output,allow_after_cutoff=False):
    now=dt.datetime.now(dt.timezone.utc)
    card=json.loads(Path(roster).read_text())
    off=timestamp(card['off_timestamp']);cutoff=off-dt.timedelta(minutes=5)
    if now>cutoff and not allow_after_cutoff:raise ValueError('CUTOFF_PASSED: no new live prediction after start cutoff')
    if now>cutoff and allow_after_cutoff:print('REPLAY_ONLY: no prospective forecast claim',file=sys.stderr)
    if len(card['runners'])!=card['expected_runners'] or len(card['runners'])<3:raise ValueError('INCOMPLETE_FIELD')
    numbers=[int(r['horse_number']) for r in card['runners']]
    names=[r['horse_name'] for r in card['runners']]
    if len(set(numbers))!=len(numbers) or len(set(names))!=len(names):raise ValueError('DUPLICATE_RUNNER')
    if not card.get('source_url','').startswith('https://'):raise ValueError('SOURCE_REQUIRED')
    if not card.get('roster_asof'):raise ValueError('ROSTER_TIMESTAMP_REQUIRED')
    if timestamp(card['roster_asof'])>min(now,cutoff):raise ValueError('ROSTER_FROM_FUTURE')
    model_art=json.loads(Path(model_file).read_text());selection=json.loads(Path(selection_file).read_text())
    if sha(model_file)!=selection['model_sha256']:raise ValueError('MODEL_HASH_MISMATCH')
    if timestamp(selection['selection_end'])>=cutoff:raise ValueError('MODEL_SELECTED_AFTER_RACE')
    if model_art.get('schema')!='keiba-rank-model-v1':raise ValueError('UNSUPPORTED_MODEL')
    model=RankModel.from_dict(model_art)
    history,_,audit=load_archive(db,lag_days=7,allow_unlinked_fields=True)
    con=sqlite3.connect(db)
    name_map={(str(rid),str(no)):name for rid,no,name in con.execute('SELECT race_id,horse_number,horse_name FROM annual_report_runners WHERE horse_name IS NOT NULL')}
    con.close()
    hist=[]
    matched=set()
    for h in history:
        name=h.get('horse_name') or name_map.get((str(h['race_id']),str(h['horse_number'])))
        if not name:continue
        if timestamp(h['result_available_at'])>cutoff:continue
        h=dict(h,horse_id=alias(name),horse_identity_missing=True)
        hist.append(h);matched.add(name)
    rows=[]
    for r in card['runners']:
        rows.append(dict(race_id=card['race_id'],race_date=off.astimezone(JST).date().isoformat(),
            off_timestamp=card['off_timestamp'],track=card['track'],surface=card['surface'],
            distance_m=card['distance_m'],going=None,horse_number=str(r['horse_number']),
            horse_id=alias(r['horse_name']),horse_identity_missing=True,
            jockey_id=None,sex_age=r.get('sex_age'),gate=r.get('gate'),
            carried_weight=None,field_size=len(numbers),expected_runners=len(numbers),
            source_url=card['source_url'],field_complete='yes',scratched='no'))
    idx=history_index(hist,assumed=True)
    feats=build_enriched(idx,rows)
    race=augment(dict(rows=rows,features=feats,race_id=card['race_id'],off_timestamp=card['off_timestamp']))
    p,q=model.predict(race['features'])
    win={ (numbers[i],):float(p[i,0]) for i in range(len(numbers))}
    pair={tuple(sorted((numbers[i],numbers[j]))):float(q[i,j,:].sum()+q[j,i,:].sum()) for i in range(len(numbers)) for j in range(i+1,len(numbers))}
    trio={tuple(sorted((numbers[i],numbers[j],numbers[k]))):float(sum(q[t] for t in itertools.permutations((i,j,k)))) for i,j,k in itertools.combinations(range(len(numbers)),3)}
    exact=max(((tuple(numbers[i] for i in ix),float(q[ix])) for ix in itertools.permutations(range(len(numbers)),3)),key=lambda v:v[1])
    ranks=sorted(range(len(numbers)),key=lambda i:(-float(p[i,0]),numbers[i]))
    out=dict(schema='keiba-v43-shadow-operational-v1',created_at=now.isoformat(),
        status='PROSPECTIVE_RESEARCH_SHADOW' if now<=cutoff else 'RETROSPECTIVE_REPLAY_ONLY',
        caveats=['Model artifact is research-only, not validated live','Horse history linked by exact name surrogate, NOT official verified ID','History result availability uses assumed seven-day lag','No current-day going, jockey, gate, carried weight or odds; missing fields neutral','Model probability calibration and real hit rates not guaranteed'],
        race=dict(card),model_sha256=sha(model_file),database_sha256=sha(db),
        history_rows=len(hist),history_name_matches=sum(name in matched for name in names),
        picks=dict(winner=numbers[ranks[0]],ordered=list(exact[0]),ordered_probability=exact[1]),
        runners=[dict(horse_number=numbers[i],horse_name=names[i],p_first=round(float(p[i,0]),8),p_second=round(float(p[i,1]),8),p_third=round(float(p[i,2]),8),p_top3=round(float(p[i,:].sum()),8),history_starts=feats[i]['history_starts']) for i in ranks],
        bets=dict(win=coverage(win,.8),quinella=coverage(pair,.5),trio=coverage(trio,.6)))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(out,ensure_ascii=False,indent=2))
    lines=['# 菊花賞 既存学習済み順位モデル・実行結果','',f"**実行区分：{out['status']}**",'','公式馬ID未連携につき馬名一致の暫定接続を使用。実運用検証済みモデルではありません。','',
      '| 印 | 馬番 | 馬名 | 1着 | 2着 | 3着 | 3着内 | 過去走数 |','|---|---:|---|---:|---:|---:|---:|---:|']
    for mark,r in zip(['◎','○','▲','☆']+['△']*len(ranks),out['runners']):
        lines.append(f"| {mark} | {r['horse_number']} | {r['horse_name']} | {r['p_first']:.2%} | {r['p_second']:.2%} | {r['p_third']:.2%} | {r['p_top3']:.2%} | {r['history_starts']} |")
    lines+=['',f"1〜3着の順序本線：{'→'.join(map(str,out['picks']['ordered']))}",'']
    for kind,title in [('win','単勝80%'),('quinella','馬連50%'),('trio','3連複60%')]:
        b=out['bets'][kind]
        lines += [f"## {title}：{b['count']}点、モデル内合算{b['cumulative']:.2%}",'',
                  '、'.join('－'.join(map(str,v['horses'])) for v in b['bets']),'']
    lines+=['','※累積値は未校正モデル内の合計であり、現実の的中率ではありません。']
    Path(output).with_suffix('.md').write_text('\n'.join(lines)+'\n')
    print('SUCCESS',out['status'],'horses',len(numbers),'history',len(hist),'matched',out['history_name_matches'],flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--db',default='jra_2023_2025.sqlite')
    a.add_argument('--roster',default='operations/20261025_kikuka_roster.json')
    a.add_argument('--model',default='keiba_v48/reports/exact_rank/model_lag7.json')
    a.add_argument('--selection',default='keiba_v48/reports/exact_rank/selection_lag7.json')
    a.add_argument('--output',default='reports/20261025_v43_shadow/prediction.json')
    a.add_argument('--allow-after-cutoff',action='store_true')
    x=a.parse_args();run(x.db,x.roster,x.model,x.selection,x.output,x.allow_after_cutoff)
