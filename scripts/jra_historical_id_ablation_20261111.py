"""Cutoff-safe retrospective rank experiment; not production v50/v51.
Sources: canonical v12 JRA SQLite and SHA-original reviewed-result rank overlay.
Train 2023-2024 validated-result; evaluate independent 2025 and 2026.
A/B uses the same fixed logistic learner; only historical horse ID availability changes.
No final odds, race-day outcomes or future data as model features.
"""
import sqlite3,json,hashlib,re,collections,math,datetime,os,argparse
from pathlib import Path
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

FEATURES=['field_size','distance_km','surface_turf','age','is_female','carried_weight','gate_fraction','horse_num_fraction',
    'horse_log_starts','horse_prior_win_rate','horse_prior_top3_rate','horse_last3_mean_strength','horse_last1_strength','horse_days_since','horse_surface_winrate','horse_surface_starts','horse_track_winrate','horse_track_starts','horse_dist_winrate','horse_dist_starts',
    'jockey_log_starts','jockey_prior_winrate','jockey_top3rate','jockey_track_winrate','jockey_surface_winrate','jockey_distance_winrate','jockey_last3_mean_strength',
    'field_mean_horse_starts','horse_strength_vs_field','jockey_strength_vs_field','field_fraction_new_horses']
ROOT=Path('/mnt/data')
DB=ROOT/'jra_recovery_20261111/roundtrip/jra_2023_2025_v12_horse_ids_full_20261111.sqlite'
OVER=ROOT/'jra_review_1975_result_grade_overlay_final_20261111.sqlite'
OUTPUT=ROOT/'jra_historical_ablation_results_20261111.json'
PRED=ROOT/'jra_historical_ablation_race_predictions_20261111.csv'

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def num(s,fallback):
 try:
  m=re.search(r'-?\d+(?:\.\d+)?',str(s))
  return float(m.group()) if m else fallback
 except: return fallback

def clamp(x,lo,hi):return max(lo,min(hi,x))

def rate(records,attr,alpha=8,prior=.07):
 n=len(records)
 return (sum(attr(x) for x in records)+alpha*prior)/(n+alpha)

def strength(pos,field):return 1-max(0,min(1,(pos-1)/max(1,field-1)))

def build_dataset(db=None,overlay=None):
 db = DB if db is None else Path(db)
 overlay = OVER if overlay is None else Path(overlay)
 c=sqlite3.connect(f'file:{db}?mode=ro',uri=True);o=sqlite3.connect(f'file:{overlay}?mode=ro',uri=True)
 rows_by_race=collections.defaultdict(list);meta={};mask=set(k for k in c.execute('select race_id,horse_number from horse_identity_backfill_20261111'))
 q="""select x.race_id,x.horse_number,x.finish_order,x.horse_name,x.jockey_name,x.horse_id,x.jockey_id,x.payload_json,r.race_date,r.track,r.surface,r.distance_m,r.expected_runners
 from annual_report_runners x join annual_report_races r using (race_id)
 where r.status='validated_result' and r.race_date is not null and r.track is not null and r.surface is not null and r.distance_m is not null"""
 for row in c.execute(q):
  rid,n,pos,name,jname,hid,jid,payload,date,track,surf,dist,expected=row
  if pos is None or pos<1:continue
  d=json.loads(payload)
  meta[rid]=(date,track,surf,dist,'validated_result')
  rows_by_race[rid].append({'race':rid,'date':date,'num':n,'rank':pos,'horse_id':hid,'mask_id':None if (rid,n) in mask else hid,
       'jockey_id':jid,'jockey_name':jname,'name':name,'age':num(d.get('sex_age'),-1),
       'female':1 if (d.get('sex_age') or '').startswith(('牝','メ')) else 0,
       'weight':num(d.get('carried_weight_raw'),55), 'gate':num(d.get('gate'),n),
       'track':track,'surface':surf,'dist':dist,'status':'validated_result'})
 # Safe review rank labels only: fully numeric, all names/metadata corroborated.
 grade={rid:record for rid,record in o.execute("select race_id,review_grade from review_race_evidence") if record=='OFFICIAL_FULL_NUMERIC_RESULT_VERIFIED'}
 review_ids={}
 for rid,n,hid,rank,status,namematch in o.execute('select race_id,horse_number,horse_id_official,official_rank,official_status,name_match from review_runner_evidence'):
  if rid in grade and status=='FINISHED' and namematch:
   review_ids[(rid,n)]=(hid,rank)
 review_races={rid:(date,track,surf,dist) for rid,date,track,surf,dist in c.execute("select race_id,race_date,track,surface,distance_m from annual_report_races where status='requires_review'") if rid in grade}
 for row in c.execute("""select x.race_id,x.horse_number,x.horse_name,x.jockey_name,x.horse_id,x.jockey_id,x.payload_json from annual_report_runners x join annual_report_races r using(race_id) where r.status='requires_review'"""):
  rid,n,name,jname,hid,jid,payload=row
  if rid not in review_races:continue
  source=review_ids.get((rid,n))
  if not source:continue
  official_hid,rank=source;date,track,surf,dist=review_races[rid];d=json.loads(payload)
  meta[rid]=(date,track,surf,dist,'review_official_full_numeric')
  rows_by_race[rid].append({'race':rid,'date':date,'num':n,'rank':rank,'horse_id':hid or official_hid,'mask_id':hid,
       'jockey_id':jid,'jockey_name':jname,'name':name,'age':num(d.get('sex_age'),-1),
       'female':1 if (d.get('sex_age') or '').startswith(('牝','メ')) else 0,
       'weight':num(d.get('carried_weight_raw'),55), 'gate':num(d.get('gate'),n),
       'track':track,'surface':surf,'dist':dist,'status':'review_official_full_numeric'})
 c.close();o.close()
 # Only one verified winner and at least 3 finishers. Exclude ambiguous first-place ties.
 valid={rid:rr for rid,rr in rows_by_race.items() if len(rr)>=3 and sum(x['rank']==1 for x in rr)==1 and all(x['horse_id'] for x in rr)}
 skipped=collections.Counter();
 for rid,rr in rows_by_race.items():
  if rid not in valid:
   skipped[meta[rid][-1]]+=1
 print('cohort',len(valid),'all',len(rows_by_race),'skipped',dict(skipped),'counts',collections.Counter(v[0]['status'] for v in valid.values()))
 return valid,skipped

class HistoricalStats:
 def __init__(self):
  self.n=0;self.wins=0;self.places=0
  self.last3=collections.deque(maxlen=3);self.last_date=None
  self.surface=collections.defaultdict(lambda:[0,0])
  self.track=collections.defaultdict(lambda:[0,0])
  self.distance=collections.defaultdict(lambda:[0,0])
 def update(self,r,quality):
  self.n+=1;self.wins+=int(r['rank']==1);self.places+=int(r['rank']<=3)
  self.last3.append(quality);self.last_date=r['date']
  for mapping,key in ((self.surface,r['surface']),(self.track,r['track']),(self.distance,r['dist'])):
   count=mapping[key];count[0]+=1;count[1]+=int(r['rank']==1)
 def winrate(self,which=None,key=None):
  if which is None:n,w=self.n,self.wins
  else:n,w=which.get(key,[0,0])
  return (w+8*.07)/(n+8)
 def top3rate(self):return (self.places+8*.21)/(self.n+8)
 def last3_strength(self):return sum(self.last3)/len(self.last3) if self.last3 else .5
 def last_strength(self):return self.last3[-1] if self.last3 else .5

def create_feature_rows(races,mode):
 bydate=collections.defaultdict(list)
 for rid,rr in races.items():bydate[rr[0]['date']].append(rr)
 horses=collections.defaultdict(HistoricalStats);jockeys=collections.defaultdict(HistoricalStats)
 empty=HistoricalStats()
 data=[];ranks=[];raceids=[];statuses=[];years=[];numbers=[];winner_nums=[]
 for date in sorted(bydate):
  today=[]
  for rows in bydate[date]:
   n=len(rows);features=[]
   for r in rows:
    hid=r['horse_id'] if mode=='full' else r['mask_id'];jid=r['jockey_id']
    hist=horses.get(hid,empty) if hid else empty
    jhist=jockeys.get(jid,empty) if jid else empty
    layoff=180 if not hist.last_date else clamp((datetime.date.fromisoformat(r['date'])-datetime.date.fromisoformat(hist.last_date)).days,0,365)
    hw=hist.winrate();jw=jhist.winrate()
    feats=[n,r['dist']/1000,float(r['surface']=='turf'),max(0,r['age']),r['female'],r['weight'],r['gate']/max(1,n),r['num']/max(1,n),
       math.log1p(hist.n),hw,hist.top3rate(),hist.last3_strength(),hist.last_strength(),layoff,
       hist.winrate(hist.surface,r['surface']),hist.surface[r['surface']][0] if r['surface'] in hist.surface else 0,
       hist.winrate(hist.track,r['track']),hist.track[r['track']][0] if r['track'] in hist.track else 0,
       hist.winrate(hist.distance,r['dist']),hist.distance[r['dist']][0] if r['dist'] in hist.distance else 0,
       math.log1p(jhist.n),jw,jhist.top3rate(),jhist.winrate(jhist.track,r['track']),jhist.winrate(jhist.surface,r['surface']),
       jhist.winrate(jhist.distance,r['dist']),jhist.last3_strength()]
    features.append(feats)
   hsum=sum(x[8] for x in features)/n;hwmean=sum(x[9] for x in features)/n;jmean=sum(x[21] for x in features)/n
   new_fraction=sum(x[8]==0 for x in features)/n
   for feat in features:feat.extend([hsum,feat[9]-hwmean,feat[21]-jmean,new_fraction])
   for r,feat in zip(rows,features):
    data.append(feat);ranks.append(r['rank']);raceids.append(r['race']);statuses.append(r['status']);years.append(int(r['date'][:4]));numbers.append(r['num']);winner_nums.append(next(z['num'] for z in rows if z['rank']==1))
   today.extend(rows)
  # Freeze all race-day features before updating any horse/jockey history.
  for r in today:
   quality=strength(r['rank'],len(races[r['race']]))
   hid=r['horse_id'] if mode=='full' else r['mask_id']
   if hid:horses[hid].update(r,quality)
   if r['jockey_id']:jockeys[r['jockey_id']].update(r,quality)
 return (np.array(data,dtype=np.float32),np.array(ranks),np.array(raceids),np.array(statuses),np.array(years),np.array(numbers),np.array(winner_nums))

def _group_race_indices(rid):
 groups=collections.defaultdict(list)
 for i,r in enumerate(rid):groups[r].append(i)
 return {r:np.asarray(indices,dtype=np.int64) for r,indices in groups.items()}

def race_pred_scores(X,years,raceids,learner):
 result=np.zeros(len(X),dtype=float)
 for sel in _group_race_indices(raceids).values():
  logits=learner.decision_function(X[sel]).astype(float)
  logits=np.clip(logits-np.max(logits),-40,0)
  exp=np.exp(logits); result[sel]=exp/exp.sum()
 return result

def evaluate(scores,rank,rid,nums,status,year):
 out=[]
 for race,sel in _group_race_indices(rid).items():
  sorted_i=sel[np.argsort(-scores[sel])]
  true_winners=sel[rank[sel]==1]
  if len(true_winners)!=1:raise RuntimeError('ambiguous winner')
  true_order=sel[np.argsort(rank[sel])]
  correct_top1=bool(sorted_i[0] in true_winners)
  top3=bool(true_winners[0] in sorted_i[:3])
  valid_podium=len(sel)>=3 and len(set(rank[true_order[:3]]))==3 and (3 not in rank[true_order[3:]] if len(sel)>3 else True)
  exact3=bool(valid_podium and set(sorted_i[:3])==set(true_order[:3]))
  ordered3=bool(valid_podium and list(sorted_i[:3])==list(true_order[:3]))
  winner_prob=float(scores[true_winners[0]])
  LL=-math.log(max(1e-12,winner_prob))
  brier=float(np.sum((scores[sel]-(sel==true_winners[0]).astype(float))**2))
  out.append({'race_id':race,'year':int(year[sel[0]]),'status':status[sel[0]],'field_size':len(sel),
       'top1':int(correct_top1),'winner_in_top3':int(top3),'unordered_podium':int(exact3), 'ordered_podium':int(ordered3),'podium_unique':int(valid_podium),
       'logloss':LL,'brier':brier,'pred_winner_horse_number':int(nums[sorted_i[0]]),'true_winner_horse_number':int(nums[true_winners[0]]),
       'pred_top3_horse_numbers':list(map(int,nums[sorted_i[:3]])),'true_top3_horse_numbers':list(map(int,nums[true_order[:3]])),'winner_probability':winner_prob,'top1_prediction_probability':float(scores[sorted_i[0]]),
       'normalized_entropy':float(-sum(float(z)*math.log(max(1e-15,float(z))) for z in scores[sel])/math.log(len(sel)))})
 return out

def metric(data):
 n=len(data)
 if not n:return {'races':0}
 return {'races':n,'top1_hit':sum(x['top1'] for x in data)/n,'winner_in_top3':sum(x['winner_in_top3'] for x in data)/n,
   'unordered_top3_exact':sum(x['unordered_podium'] for x in data)/sum(x['podium_unique'] for x in data) if sum(x['podium_unique'] for x in data) else None,
   'ordered_top3_exact':sum(x['ordered_podium'] for x in data)/sum(x['podium_unique'] for x in data) if sum(x['podium_unique'] for x in data) else None,
   'unique_podium_races':sum(x['podium_unique'] for x in data),'mean_log_loss':np.mean([x['logloss'] for x in data]).item(),
   'mean_brier':np.mean([x['brier'] for x in data]).item(),'avg_field':np.mean([x['field_size'] for x in data]).item()}

def paired_bootstrap(a,b,key,seed=20261111):
 left=np.array([z[key] for z in a]);right=np.array([z[key] for z in b]);diff=right-left
 rng=np.random.default_rng(seed);n=len(diff)
 samples=np.array([diff[rng.integers(n,size=n)].mean() for i in range(1200)])
 return {'observed_diff_full_minus_masked':float(diff.mean()),'bootstrap_ci95':[float(x) for x in np.quantile(samples,[.025,.975])]}

def run():
 races,skipped=build_dataset();results={};featuresets={}
 for mode in ('masked','full'):
  X,rank,rid,status,years,nums,winner_nums=create_feature_rows(races,mode)
  if X.shape[1]!=len(FEATURES):raise RuntimeError('feature mismatch: '+str(X.shape[1]))
  train=(years<=2024)&(status=='validated_result')
  clf=make_pipeline(StandardScaler(),LogisticRegression(C=1,solver='lbfgs',max_iter=300,class_weight=None))
  clf.fit(X[train],(rank[train]==1).astype(int))
  predictions=race_pred_scores(X,years,rid,clf)
  full=evaluate(predictions,rank,rid,nums,status,years)
  results[mode]={'train_races':len(np.unique(rid[train])),'train_runners':int(train.sum()),'holdouts':{},'race_details':{z['race_id']:z for z in full if z['year']>=2025}}
  for cohort,subset in [('2025_validated',[z for z in full if z['year']==2025 and z['status']=='validated_result']),
                        ('2026_validated',[z for z in full if z['year']==2026 and z['status']=='validated_result']),
                        ('2025_review_full_numeric',[z for z in full if z['year']==2025 and z['status']=='review_official_full_numeric']),
                        ('2026_review_full_numeric',[z for z in full if z['year']==2026 and z['status']=='review_official_full_numeric'])]:
   results[mode]['holdouts'][cohort]=metric(subset)
  print('mode',mode,'train',int(train.sum()),'summary',results[mode]['holdouts'])
 final={'schema':'jra-real-chronological-identity-ablation-v1','description':'Research baseline only; not trained v50/v51 and does not use historic model A preoff snapshots',
    'source_database_sha256':sha(DB),'source_review_overlay_sha256':sha(OVER),'feature_policy':'strictly previous calendar dates only, no final odds or bodyweights, fixed 2023-24 training; 2025/2026 never refit',
    'features':FEATURES,'skipped_ambiguous_races':dict(skipped),'models':{m:{k:v for k,v in x.items() if k!='race_details'} for m,x in results.items()},'paired_differences':{},'top1_calibration':{}}
 for cohort in results['masked']['holdouts']:
  aa=[v for v in results['masked']['race_details'].values() if (cohort.startswith(str(v['year'])) and v['status']==('validated_result' if 'validated' in cohort else 'review_official_full_numeric'))]
  bb=[results['full']['race_details'][z['race_id']] for z in aa]
  for key in ('top1','logloss','brier','unordered_podium'):
   final['paired_differences'][cohort+':'+key]=paired_bootstrap(aa,bb,key) if aa else None
 # No heldout-derived tuning. Calibration buckets were chosen before examining bins.
 for mode,by in results.items():
  for year in (2025,2026):
   raceset=[v for v in by['race_details'].values() if v['year']==year and v['status']=='validated_result']
   groups={};loss=0
   for lo,hi in ((0,.10),(.10,.15),(.15,.20),(.20,.30),(.30,.40),(.40,1.01)):
    group=[v for v in raceset if lo<=v['top1_prediction_probability']<hi]
    groups[f'{lo:.2f}-{hi:.2f}']={'races':len(group),'mean_pred_top1':float(np.mean([v['top1_prediction_probability'] for v in group])) if group else None,'observed_top1':float(np.mean([v['top1'] for v in group])) if group else None}
    if group:loss+=len(group)*abs(groups[f'{lo:.2f}-{hi:.2f}']['mean_pred_top1']-groups[f'{lo:.2f}-{hi:.2f}']['observed_top1'])
   final['top1_calibration'][f'{mode}:{year}']={'bins':groups,'ece':loss/max(1,len(raceset)),
        'high_entropy_races':sum(v['normalized_entropy']>=.85 for v in raceset)}
 with open(PRED,'w') as f:
  import csv
  writer=csv.writer(f);writer.writerow(['race_id','year','data_grade','field_size','true_winner_num','old_id_mask_pred_top1_num','new_v12_id_pred_top1_num','old_pred_winner_prob','new_pred_winner_prob','old_top1_hit','new_top1_hit','old_logloss','new_logloss'])
  for rid,a in sorted(results['masked']['race_details'].items()):
   b=results['full']['race_details'][rid];writer.writerow([rid,a['year'],a['status'],a['field_size'],a['true_winner_horse_number'],a['pred_winner_horse_number'],b['pred_winner_horse_number'],a['winner_probability'],b['winner_probability'],a['top1'],b['top1'],a['logloss'],b['logloss']])
 OUTPUT.write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')
 print('SAVED',OUTPUT,PRED,'SOURCE',final['source_database_sha256'],'RESULTSHA',sha(OUTPUT))

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description='Real JRA chronological horse-ID ablation: NOT production v50/v51')
 parser.add_argument('--database',default=str(DB))
 parser.add_argument('--review-overlay',default=str(OVER))
 parser.add_argument('--output-json',default=str(OUTPUT))
 parser.add_argument('--output-race-csv',default=str(PRED))
 options=parser.parse_args()
 DB=Path(options.database)
 OVER=Path(options.review_overlay)
 OUTPUT=Path(options.output_json)
 PRED=Path(options.output_race_csv)
 run()