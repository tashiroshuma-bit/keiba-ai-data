import ast,datetime as dt,hashlib,itertools,json,math,re,sys,unicodedata
from pathlib import Path
import argparse
args=argparse.ArgumentParser()
for key in ('db','baseline','evidence','output'):args.add_argument('--'+key,required=True)
a=args.parse_args()
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'keiba_v48'),str(REPO/'scripts')]
from ranking_model import RankModel,NAMES
from jockey_feature_overlay import overlay
old=json.loads(Path(a.baseline).read_text())
ev=json.loads(Path(a.evidence).read_text())
from enriched_features import load_observed_enriched
from features import HistoryIndex,timestamp
import sqlite3
asof=min(timestamp(r['jra']['at']) for r in ev['races'])
history=load_observed_enriched(a.db,asof)
index=HistoryIndex(history,allow_missing_jockey=True)
stats={}
for jid in index.groups['jockey']:
 value,samples=index.jockey_form(jid,'not_a_historical_race',asof+dt.timedelta(days=1),asof)
 stats[jid]={'value':value,'samples':samples}
with sqlite3.connect('file:'+str(Path(a.db).resolve())+'?mode=ro',uri=True) as c:
 catalog=c.execute('select distinct jockey_id,jockey_name from official_identity_evidence where jockey_id is not null').fetchall()
expected='5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc'
with open(a.db,'rb') as handle:assert hashlib.file_digest(handle,'sha256').hexdigest()==expected
modelpath=REPO/'keiba_v48/reports/exact_rank/model_lag7.json'
model=RankModel.from_dict(json.loads(modelpath.read_text()))
from jockey_overlay_ticket_math import calculate_model
def norm(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s)).lstrip('▲△☆★◇')
out={'status':'research_shadow_rider_overlay_not_calibrated','created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'model_sha256':hashlib.sha256(modelpath.read_bytes()).hexdigest(),'database_sha256':'5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc','history_asof':asof.isoformat(),'history_rows':len(history),'history_latest_race':max(r['race_date'] for r in history),'changed_features':['jockey_form','jockey_identity_missing'],'races':[]}
for race in ev['races']:
 baseline=next(r for r in old['races'] if r['race']==race['race'])
 horses=[dict(h) for h in baseline['runners']]
 rows=[r for r in race['jra']['rows'] if r['links'] and any('uma' in c['class'] for c in r['cells'])]
 assert len(rows)==len(horses)
 frame=None;features=[]
 for horse,row in zip(horses,rows):
  number=int(next(c['text'] for c in row['cells'] if 'uban' in c['class']))
  assert number==horse['number']
  assert row['links'][0]['text']==horse['name']
  explicit=next((c['text'] for c in row['cells'] if 'wban' in c['class']),None)
  if explicit:frame=int(explicit)
  horse['frame']=frame
  link=next(a for a in row['links'] if a.get('onclick') and 'accessK' in a['onclick'])
  rawcode=re.search(r'sw04kmk01(\d{4})/',link['onclick'])[1]
  # Require BOTH the official source code suffix and the official displayed name.
  # This crosswalk never manufactures a canonical ID absent from DB evidence.
  candidates={jid for jid,name in catalog if jid.endswith(rawcode) and norm(name)==norm(link['text'])}
  assert len(candidates)<=1
  horse['jockey_id']=next(iter(candidates),None)
  horse['jockey_source_code']='sw04kmk01'+rawcode
  horse['jockey_identity_basis']='official_mobile_code_suffix_and_name_match_direct_DB_evidence' if candidates else 'unmatched_official_mobile_identity_no_history_join'
  horse['jockey_history_samples']=stats.get(horse['jockey_id'],{}).get('samples',0)
  horse['jockey_form']=stats.get(horse['jockey_id'],{}).get('value',.25)
  horse['jockey_source_action']=link['onclick']
  values=model.mean.tolist();starts=horse['starts']
  updates={'ability':(horse['wins']+1)/(starts+4),'recent_quality':(horse['wins']+horse['seconds']+horse['thirds']+1)/(starts+2),'history_log':math.log1p(starts)/5,'horse_identity_missing':1,'jockey_identity_missing':1,'age_missing':1}
  for k,v in updates.items():values[NAMES.index(k)]=v
  features.append({'values':values,'group':baseline['track']+'/'+baseline['surface'],'cutoff_timestamp':race['jra']['at']})
 p,_=model.predict(features)
 oldmap={h['number']:h['p1'] for h in baseline['models']['A']['horses']}
 assert max(abs(float(p[i,0])-oldmap[h['number']]) for i,h in enumerate(horses))<1e-10
 modified=overlay(features,horses,NAMES,stats)
 p,_=model.predict(modified);internal=[float(v) for v in p[:,0]]
 extmap={r['number']:r['index'] for r in baseline['external_indices']}
 e=[math.exp((extmap[h['number']]-max(extmap.values()))/20) for h in horses];external=[v/sum(e) for v in e]
 models={k:calculate_model(horses,[a*x+(1-a)*y for x,y in zip(internal,external)]) for k,a in [('A',1),('B',.75),('C',.5),('D',.25)]}
 for m in models.values():
  for key in ('p1','p2','p3'):assert abs(sum(h[key] for h in m['horses'])-1)<1e-10
 out['races'].append({'race':race['race'],'runners':horses,'models':models,'old_A':baseline['models']['A']['horses'],'source':race['jra']['url'],'source_asof':race['jra']['at'],'source_sha256':race['jra']['sha256']})
dest=Path(a.output)
if dest.exists():raise ValueError('immutable output already exists')
dest.parent.mkdir(exist_ok=True,parents=True);dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{'race':r['race'],'old':r['old_A'][0],'new':r['models']['A']['horses'][0],'unmatched':[h['jockey'] for h in r['runners'] if not h['jockey_id']]} for r in out['races']],ensure_ascii=False,indent=2))
