import os,sys,re,sqlite3,json,hashlib,collections,datetime,time,math,importlib.util
from pathlib import Path
import numpy as np
BASE=Path('/mnt/data/files');OUT=Path('/mnt/data/v51_fouraxis_fullrun_20261113')
DB=BASE/'jra_2023_2025_v12_horse_ids_full_20261111.sqlite';OVER=BASE/'jra_review_1975_verified_v2_20261111.sqlite'
EXPECTED=[('5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd',362139648),('5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea',6254592)]
NAMES=['past_race_class_last3','past_rivals_prior_strength_last3','prior_class_missing','prior_rival_strength_missing','prior_corner4_fraction_last3','prior_early_style_last3','prior_corner_finish_gain_last3','prior_style_missing','jockey_track_surface_distance_residual','jockey_course_count_log','jockey_condition_missing','previous_reported_weight_delta_pct_last3','previous_weight_count_log','previous_weight_missing']
def log(*a):print(datetime.datetime.now().isoformat(timespec='seconds'),*a,flush=True)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def cls(raw):
 if not isinstance(raw,str):return None
 head=raw[:raw.find('本 賞')] if '本 賞' in raw else raw[:850]
 for pattern,k in [(r'GⅠ|ＧⅠ|\bGI\b|\bG1\b',9),(r'GⅡ|ＧⅡ|\bGII\b|\bG2\b',8),(r'GⅢ|ＧⅢ|\bGIII\b|\bG3\b',7),(r'リステッド|Listed',6),(r'3勝クラス|３勝クラス|1600万下',4),(r'2勝クラス|２勝クラス|1000万下',3),(r'1勝クラス|１勝クラス|500万下',2),(r'オープン|OPEN',5),(r'未勝利',1),(r'新馬|メイクデビュー',0)]:
  if re.search(pattern,head,re.I):return k
 return None

def pos4(raw,n):
 if not isinstance(raw,str):return None
 i=raw.find('通過順位')
 if i<0:return None
 seg=raw[i+4:].split('勝馬の')[0].replace('・',' ')
 markers=list(re.finditer(r'(?<![\d,])4\s+(?=[\d(])',seg))
 for m in reversed(markers):
  text=seg[m.end():].split('市場取引馬')[0]
  xs=[int(k) for k in re.findall(r'(?<!\d)\d{1,2}(?!\d)',text)]
  if len(xs)==n and set(xs)==set(range(1,n+1)):
   return {v:i+1 for i,v in enumerate(xs)}
 return None

def weight(p):
 try:
  w=float(str(p.get('body_weight_raw')).replace(' ','').replace('＋','+'))
  d=float(str(p.get('body_weight_change_raw')).replace(' ','').replace('＋','+').replace('－','-'))
  if 250<=w<=700 and -100<=d<=100 and 250<=w-d<=700:return d/(w-d)*100
 except (TypeError,ValueError):pass
 return None

def source(races):
 c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
 metadata={};w={};cnt=collections.Counter()
 for rid,payload,n in c.execute('select race_id,metadata_json,expected_runners from annual_report_races'):
  if rid not in races:continue
  t=json.loads(payload or '{}').get('raw_text','');k=cls(t);co=pos4(t,n if n is not None else len(races[rid]))
  metadata[rid]=(k,co)
  cnt['races']+=1
  cnt['class_detected_races']+=int(k is not None)
  cnt['full_corner_detected_races']+=int(co is not None)
 for rid,no,payload in c.execute('select race_id,horse_number,payload_json from annual_report_runners'):
  if rid not in races:continue
  x=weight(json.loads(payload or '{}'))
  if x is not None:w[(rid,int(no))]=x;cnt['bodyweight_delta_rows']+=1
 c.close()
 return metadata,w,dict(cnt)

def avg(x):return sum(x)/len(x) if x else None

def build(races,metadata,w):
 byday=collections.defaultdict(list)
 for rid,rr in races.items():byday[rr[0]['date']].append((rid,rr))
 horse=collections.defaultdict(list);jockey=collections.defaultdict(list);vectors={};coverage=collections.defaultdict(collections.Counter); embargo=collections.deque()
 for step,(day,race_groups) in enumerate(sorted(byday.items())):
  d=datetime.date.fromisoformat(day);pending=[]
  while embargo and (d-embargo[0][0]).days>=2:
   _,older=embargo.popleft()
   for rr,zz in older:
    horse[rr['horse_id']].append(zz)
    if rr.get('jockey_id'):jockey[rr['jockey_id']].append(zz)
  for rid,rr in race_groups:
   n=len(rr);k,corner=metadata.get(rid,(None,None));strength={}
   for r in rr:
    history=horse[r['horse_id']]
    strength[r['num']]=(sum(z['rank']==1 for z in history)+.56)/(len(history)+8) if history else None
   rival={r['num']:avg([v for num,v in strength.items() if num!=r['num'] and v is not None]) for r in rr}
   for r in rr:
    hh=horse[r['horse_id']]
    jj=jockey[r['jockey_id']] if r.get('jockey_id') else []
    last=hh[-3:];classes=[z['cls'] for z in last if z['cls'] is not None];rv=[z['rival'] for z in last if z['rival'] is not None]
    cc=[z for z in last if z['corner'] is not None and z['field']>1]
    fractions=[(z['corner']-1)/(z['field']-1) for z in cc]
    changes=[(z['corner']-z['rank'])/(z['field']-1) for z in cc]
    ww=[z['delta'] for z in last if z['delta'] is not None]
    match=[z for z in jj if z['track']==r['track'] and z['surface']==r['surface'] and abs(z['dist']-r['dist'])<=200]
    gp=(sum(z['rank']<=3 for z in jj)+20*.21)/(len(jj)+20) if jj else None
    cp=(sum(z['rank']<=3 for z in match)+20*gp)/(len(match)+20) if match else None
    vec=np.array([avg(classes)/9 if classes else 0,avg(rv) if rv else 0,float(not classes),float(not rv),avg(fractions) if fractions else 0,avg([float(q<=.33) for q in fractions]) if fractions else 0,avg(changes) if changes else 0,float(not cc),(cp-gp) if cp is not None else 0,math.log1p(len(match)),float(not match),avg(ww)/10 if ww else 0,math.log1p(len(ww)),float(not ww)],dtype=float)
    if not np.isfinite(vec).all():raise ValueError('nonfinite feature')
    key=(str(rid),int(r['num']))
    if key in vectors:raise ValueError('duplicate race runner')
    vectors[key]=vec
    cv=coverage[day[:4]];cv['runners']+=1
    for name,ind in [('prior_class',2),('prior_rival',3),('prior_corner',7),('jockey_conditional',10),('prior_weight',13)]:
     if vec[ind]==0:cv[name+'_observed']+=1
    pending.append((r,{'date':d,'rank':r['rank'],'field':n,'track':r['track'],'surface':r['surface'],'dist':r['dist'],'cls':k,'corner':corner.get(r['num']) if corner else None,'delta':w.get((rid,int(r['num']))),'rival':rival[r['num']]}))
  embargo.append((d,pending))
  if step and step%100==0:log('history date',day,'races',sum(len(x) for x in byday.values()),'vectors',len(vectors))
 return vectors,{k:dict(v) for k,v in coverage.items()}

def main():
 for path,(expected,size) in zip((DB,OVER),EXPECTED):
  assert path.stat().st_size==size
  assert sha(path)==expected
  c=sqlite3.connect(f'file:{path}?mode=ro',uri=True);assert c.execute('pragma quick_check').fetchone()[0]=='ok';c.close()
 log('real source SHA256 + integrity checked')
 h=module('source_historical',BASE/'jra_historical_ablation.py')
 races,skipped=h.build_dataset(db=DB,overlay=OVER)
 log('loaded',len(races),'real races')
 X,rank,rids,status,years,nums,winners=h.create_feature_rows(races,'full')
 log('31 existing historical features',X.shape)
 meta,w,counts=source(races);log('official source fields',counts)
 vect,cover=build(races,meta,w)
 feature=np.stack([vect[(str(r),int(n))] for r,n in zip(rids,nums)])
 np.savez_compressed(OUT/'v51_fouraxis_features_20261113.npz',X=X,rank=rank,rids=rids,status=status,years=years,nums=nums,feature=feature)
 (OUT/'source_coverage.json').write_text(json.dumps({'source':counts,'years':cover,'source_db_sha256':EXPECTED[0][0],'overlay_sha256':EXPECTED[1][0],'feature_names':NAMES,'bodyweight_current_race_used':False,'max_history_cutoff_days':-2},ensure_ascii=False,indent=2))
 log('DONE feature arrays',feature.shape,cover)
if __name__=='__main__':main()