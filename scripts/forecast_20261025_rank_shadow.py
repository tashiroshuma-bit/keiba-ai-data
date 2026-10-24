"""2026-10-25 all-race research shadow: existing trained rank artifact + publicly available pre-race career records.
This is NOT a validated V43 production forecast: most features are mean-imputed proxies.
"""
import datetime as dt,itertools,json,math,re,sys,time,urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from ranking_model import RankModel,NAMES
from completion_validation import sha
from v43_status_integration_smoke import cover
BASE=Path(__file__).resolve().parents[1]
TRACKS={'東京':'26050409','京都':'26080409','新潟':'26040404'}
# 0 = unknown, 1 = turf, 2 = dirt; obstacle races excluded.
SURFACE={'東京':'DDDTOOTTO DDD'.replace(' ',''),'京都':'DDTOOTTOODTD','新潟':'TDTDTDTOOTTD'}
# Official 2026-10-25 program distances; race numbers 1..12.
DISTANCES={'東京':[1600,2000,1600,3000,1800,1400,1400,1600,1600,1800,1400,1600],
'京都':[1800,1400,1600,1400,1800,1800,1800,1200,1800,1800,3000,1400],
'新潟':[1200,1800,2000,1200,1400,1800,2000,2500,1600,2000,1000,1200]}
# Explicitly set surfaces to avoid a silent off-by-one.
SURFACE={'東京':['dirt','turf','turf','obstacle','turf','turf','dirt','turf','dirt','turf','dirt','dirt'],
'京都':['dirt','dirt','turf','dirt','turf','dirt','turf','turf','turf','dirt','turf','dirt'],
'新潟':['turf','dirt','turf','dirt','turf','dirt','turf','dirt','turf','turf','turf','dirt']}
def get(url):
  last=None
  for attempt in range(4):
    try:
      req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
      return urllib.request.urlopen(req,timeout=24).read().decode('utf-8','replace')
    except Exception as e:
      last=e;time.sleep(attempt+1)
  raise last
def parse(track,code,race):
  url='https://sports.yahoo.co.jp/keiba/race/achievement/all/'+code+f'{race:02d}'
  soup=BeautifulSoup(get(url),'html.parser')
  txt=soup.get_text(' ',strip=True)
  if '2026年10月25日' not in txt:raise ValueError('DATE_MISMATCH')
  horses=[]
  for table in soup.select('table'):
    hdr=' '.join(x.get_text(' ',strip=True) for x in table.select('th'))
    if not ('馬番' in hdr and '馬名' in hdr and '全レース' in hdr):continue
    for tr in table.select('tr'):
      c=[x.get_text(' ',strip=True) for x in tr.find_all('td',recursive=False)]
      if len(c)<5 or not re.fullmatch(r'\d+',c[1]):continue
      rec=re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)',c[4])
      if not rec:continue
      wins,seconds,thirds,others=map(int,rec.groups())
      horses.append(dict(number=int(c[1]),name=c[2],starts=wins+seconds+thirds+others,wins=wins,seconds=seconds,thirds=thirds))
    if horses:break
  if not horses: # Debutants: roster only; no prior starts; not ranked among five
    url='https://sports.yahoo.co.jp/keiba/race/denma/'+code+f'{race:02d}'
    soup=BeautifulSoup(get(url),'html.parser')
    txt=soup.get_text(' ',strip=True)
    if '2026年10月25日' not in txt:raise ValueError('DATE_MISMATCH_ROSTER')
    for table in soup.select('table'):
      hdr=' '.join(x.get_text(' ',strip=True) for x in table.select('th'))
      if not ('馬番' in hdr and '馬名' in hdr):continue
      for tr in table.select('tr'):
        c=tr.find_all('td',recursive=False)
        if len(c)<3:continue
        no=c[1].get_text(' ',strip=True)
        if not re.fullmatch(r'\d+',no):continue
        a=c[2].find('a')
        name=a.get_text(' ',strip=True) if a else c[2].get_text(' ',strip=True).split(' ')[0]
        horses.append(dict(number=int(no),name=name,starts=0,wins=0,seconds=0,thirds=0))
      if horses:break
  if not 3<=len(horses)<=18 or len({x['number'] for x in horses})!=len(horses):
    raise ValueError('FIELD_INCOMPLETE '+str(len(horses)))
  return dict(track=track,race=race,source=url,field=horses,method='CAREER_TOTALS_PROXY' if any(x['starts'] for x in horses) else 'NO_HISTORY_TIE')
def model():
  path=BASE/'keiba_v48/reports/exact_rank/model_lag7.json'
  selection=json.loads((BASE/'keiba_v48/reports/exact_rank/selection_lag7.json').read_text())
  assert sha(path)==selection['model_sha256']
  return RankModel.from_dict(json.loads(path.read_text())),sha(path)
def predict(r,m):
  numbers=[h['number'] for h in r['field']];n=len(numbers)
  features=[];ix={name:i for i,name in enumerate(NAMES)}
  for h in r['field']:
    values=m.mean.tolist()
    starts=h['starts']
    for name,value in {'ability':(h['wins']+1)/(starts+4),
       'recent_quality':(h['wins']+h['seconds']+h['thirds']+1)/(starts+2),
       'history_log':math.log1p(starts)/5,
       'horse_identity_missing':1,'jockey_identity_missing':1,'age_missing':1}.items():
      if name in ix:values[ix[name]]=value
    features.append(dict(values=values,group=r['track']+'/'+SURFACE[r['track']][r['race']-1],cutoff_timestamp='2026-10-25T00:00:00+09:00'))
  p,q=m.predict(features);assert abs(float(q.sum())-1)<1e-8
  win={(numbers[i],):float(p[i,0]) for i in range(n)}
  pair={tuple(sorted((numbers[i],numbers[j]))):float(q[i,j,:].sum()+q[j,i,:].sum()) for i in range(n) for j in range(i+1,n)}
  trio={tuple(sorted((numbers[i],numbers[j],numbers[k]))):float(sum(q[t] for t in itertools.permutations((i,j,k)))) for i,j,k in itertools.combinations(range(n),3)}
  ranks=sorted(range(n),key=lambda i:(-float(p[i,0]),numbers[i]))
  exact=max(itertools.permutations(range(n),3),key=lambda t:float(q[t]))
  r['ranked']=[dict(number=numbers[i],name=r['field'][i]['name'],p1=round(float(p[i,0]),9),p2=round(float(p[i,1]),9),p3=round(float(p[i,2]),9)) for i in ranks]
  r['ordered_top3']=[numbers[i] for i in exact]
  r['tickets']={'win':cover(win,.8),'quinella':cover(pair,.5),'trio':cover(trio,.6)}
  r['eligible_for_top5']=r['method']=='CAREER_TOTALS_PROXY' and SURFACE[r['track']][r['race']-1]!='obstacle'
  r['max_model_p1']=float(p[ranks[0],0])
  return r
def main():
  m,h=model();races=[];failed=[]
  for track,code in TRACKS.items():
    for race in range(1,13):
      try:
        if SURFACE[track][race-1]=='obstacle':
          failed.append(dict(track=track,race=race,reason='OBSTACLE_OUT_OF_MODEL_DOMAIN'));continue
        r=parse(track,code,race)
        if track=='京都' and race==11:
          card=json.loads((BASE/'operations/20261025_kikuka_roster.json').read_text())
          assert len(card['runners'])==18
          assert {(x['number'],x['name']) for x in r['field']}=={(x['horse_number'],x['horse_name']) for x in card['runners']},'KIKUKA_CARD_MISMATCH'
        r=predict(r,m);races.append(r)
        print('OK',track,race,len(r['field']),round(r['max_model_p1'],4),flush=True)
      except Exception as e:
        failed.append(dict(track=track,race=race,reason=str(e)))
        print('FAIL',track,race,str(e),flush=True)
  selected=sorted((r for r in races if r['eligible_for_top5']),key=lambda r:-r['max_model_p1'])[:5]
  kik=next((r for r in races if r['track']=='京都' and r['race']==11),None)
  if not kik:raise RuntimeError('KIKUKA_MISSING')
  if len(races)<28:raise RuntimeError('TOO_FEW_RACES '+str(len(races)))
  data=dict(status='RESEARCH_SHADOW_UNCALIBRATED_NOT_V43_PRODUCTION',
    caveat='Career-total proxies + training mean imputation are NOT training-identical features; model probability is NOT real hit probability. Top 5 selected from available races, not proven highest actual accuracy.',
    created_at=dt.datetime.now(dt.timezone.utc).isoformat(),model_sha256=h,eligible=len([r for r in races if r['eligible_for_top5']]),
    covered=len(races),failures=failed,top5=[dict(track=r['track'],race=r['race']) for r in selected],
    races=races)
  out=BASE/'reports/20261025_allrace_rank_shadow';out.mkdir(parents=True,exist_ok=True)
  (out/'all_races.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
  lines=['# 2026-10-25 全レース：学習済み順位モデル研究用シャドー予測','',
    '**重要：学習時と同じ特徴量ではありません。全馬の通算成績から一部特徴量を近似し、他は学習平均で補完した技術実験です。的中率の高い5レースだと実証したものではありません。**','',
    f"取得・計算：{len(races)}/36R。除外/取得失敗：{len(failed)}R。上位5選定母集団：{data['eligible']}R。",'']
  for title,rs in [('上位5レース（モデル内1着最大値順）',selected),('菊花賞（上位5と重複しても別掲）',[kik])]:
    lines+=['## '+title,'']
    for r in rs:
      lines += [f"### {r['track']}{r['race']}R",'',f"◎ {r['ranked'][0]['number']} {r['ranked'][0]['name']}（モデル内1着割合 {r['ranked'][0]['p1']:.2%}）",
        '○ '+str(r['ranked'][1]['number'])+' '+r['ranked'][1]['name'],
        '▲ '+str(r['ranked'][2]['number'])+' '+r['ranked'][2]['name'],
        '☆ '+str(r['ranked'][3]['number'])+' '+r['ranked'][3]['name'],
        '1→2→3（順序最頻）: '+'→'.join(map(str,r['ordered_top3'])),'']
      for key,label in [('win','単勝80%'),('quinella','馬連50%'),('trio','3連複60%')]:
        b=r['tickets'][key]
        lines += [f"**{label}：{b['count']}点／モデル内累積{b['coverage']:.2%}**",
          '、'.join('-'.join(map(str,v['numbers'])) for v in b['tickets']),'']
  lines+=['## 未取得・対象外','',json.dumps(failed,ensure_ascii=False,indent=2)]
  (out/'report.md').write_text('\n'.join(lines)+'\n')
  print('FINISHED',len(races),'TOP5',[(r['track'],r['race']) for r in selected],flush=True)
if __name__=='__main__':main()
