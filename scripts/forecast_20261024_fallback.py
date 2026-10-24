import csv,json,math,re,time,datetime,pathlib,urllib.request
from bs4 import BeautifulSoup
T={'東京':'26050408','京都':'26080408','新潟':'26040403'}
U='https://sports.yahoo.co.jp/keiba/race/achievement/all/'
out=pathlib.Path('reports/20261024_manual_fallback');out.mkdir(parents=True,exist_ok=True)
def read_with_retries(req):
 last=None
 for attempt in range(5):
  try:
   return urllib.request.urlopen(req,timeout=30).read().decode('utf-8','replace')
  except Exception as e:
   last=e
   time.sleep(1.5*(attempt+1))
 raise last

rows=[];failed=[]
for track,code in T.items():
 for race in range(1,13):
  url=U+code+f'{race:02d}'
  try:
   if track=='京都' and race==4:raise ValueError('obstacle race career table unavailable; roster-only uniform fallback')
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
   html=read_with_retries(req)
   soup=BeautifulSoup(html,'html.parser');text=soup.get_text(' ',strip=True)
   if '2026年10月24日' not in text:raise ValueError('date mismatch')
   horses=[]
   for table in soup.select('table'):
    hdr=' '.join(th.get_text(' ',strip=True) for th in table.select('th'))
    if not ('馬番' in hdr and '馬名' in hdr and '本賞金' in hdr and '全レース' in hdr):continue
    for tr in table.select('tr'):
     c=[td.get_text(' ',strip=True) for td in tr.find_all('td',recursive=False)]
     if len(c)<5 or not re.fullmatch(r'\d+',c[1]):continue
     m=re.search(r'([\d,.]+)\s*万',c[3]);p=re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)',c[4])
     if not m or not p:raise ValueError('bad horse row')
     w,s,t,o=map(int,p.groups());e=float(m.group(1).replace(',',''))
     strength=math.exp((.35*math.log1p(e)+(3*w+1.5*s+.7*t)/(w+s+t+o+4)+.7)/1.6)
     horses.append(dict(number=int(c[1]),name=c[2],earnings=e,record=[w,s,t,o],strength=strength))
    if horses:break
   if not 5<=len(horses)<=18 or len({h['number'] for h in horses})!=len(horses):raise ValueError('incomplete field')
   total=sum(h['strength'] for h in horses)
   for h in horses:h['relative_weight_pct']=round(100*h.pop('strength')/total,3)
   horses.sort(key=lambda h:(-h['relative_weight_pct'],h['number']))
   rows.append(dict(track=track,race=race,horses=horses,source=url))
   print('OK',track,race,len(horses),flush=True)
  except Exception as e:
   # All-debutant races lack career statistics. Read pre-race entry list only.
   # Never read the result page, betting odds, or finishing positions.
   try:
    debut_url='https://sports.yahoo.co.jp/keiba/race/denma/'+code+f'{race:02d}'
    req=urllib.request.Request(debut_url,headers={'User-Agent':'Mozilla/5.0'})
    html=read_with_retries(req)
    soup=BeautifulSoup(html,'html.parser');txt=soup.get_text(' ',strip=True)
    if '2026年10月24日' not in txt:raise ValueError('date mismatch in pre-race entry page')
    horses=[]
    for table in soup.select('table'):
     hdr=' '.join(th.get_text(' ',strip=True) for th in table.select('th'))
     if not ('馬番' in hdr and '馬名' in hdr):continue
     for tr in table.select('tr'):
      c=tr.find_all('td',recursive=False)
      if len(c)<3:continue
      no=c[1].get_text(' ',strip=True)
      if not re.fullmatch(r'\d+',no):continue
      a=c[2].find('a');name=a.get_text(' ',strip=True) if a else c[2].get_text(' ',strip=True).split(' ')[0]
      horses.append(dict(number=int(no),name=name,earnings=0,record=[0,0,0,0]))
     if horses:break
    if not 5<=len(horses)<=18 or len({h['number'] for h in horses})!=len(horses):raise ValueError('incomplete debut field')
    for h in horses:h['relative_weight_pct']=round(100/len(horses),3)
    horses.sort(key=lambda h:h['number'])
    rows.append(dict(track=track,race=race,horses=horses,source=debut_url,method=('UNIFORM_DEBUT_TIE_no_prior_performance' if '新馬' in txt else 'UNIFORM_NO_VERIFIED_HISTORY_no_rank_discrimination')))
    print('UNIFORM DEBUT',track,race,len(horses),flush=True)
   except Exception as e2:
    failed.append(dict(track=track,race=race,error=str(e)+'; fallback: '+str(e2),source=url))
    print('FAIL',track,race,str(e2),flush=True)
  time.sleep(.2)
data=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind='retrospective_20261024_uncalibrated_baseline_NOT_V43',races=rows,failures=failed)
(out/'predictions.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
by={(x['track'],x['race']):x for x in rows}
lines=['# 2026年10月24日 全36R 事後・独自簡易評価','', '**V43学習済みモデルの予測ではありません。結果・オッズを使わずレース前の通算成績だけで事後計算した未校正の相対評価割合です。発走前の的中率には算入できません。**','', '| 指標 | 目標 | 現在（ユーザー提示の既報値） |','|---|---:|---:|','| 1着指名的中率 | 80% | 20.13〜20.24% |','| 1〜3着順序完全一致 | 50% | 0.81〜0.85% |','| 順不同3頭完全一致 | 60% | 3.47〜3.62% |','', '| 場 | R | ◎ | ○ | ▲ | ☆ | 1→2→3 |','|---|---:|---|---|---|---|---|']
for track in T:
 for race in range(1,13):
  r=by.get((track,race))
  if r:
   h=r['horses'][:4];c=[f"{x['number']} {x['name']} ({x['relative_weight_pct']:.2f}%)" for x in h]
   lines.append(f"| {track} | {race} | {' | '.join(c)} | {'→'.join(str(x['number']) for x in h[:3])} |")
  else:lines.append(f"| {track} | {race} | 未算出 | 未算出 | 未算出 | 未算出 | 未算出 |")
lines+=['',f"取得・計算 {len(rows)}/36R、未取得 {len(failed)}/36R。",'','新馬戦と京都4Rは実績データがなく全馬同点。馬番順の◎○▲☆は便宜上の順序であり、優劣を予測していません。各馬の1/2/3着確率、期待値、当日馬場適性、3着穴適性は未算出。']
(out/'report.md').write_text('\n'.join(lines)+'\n')
if len(rows)!=36:raise SystemExit('Incomplete: '+str(len(rows))+'/36')
