import sqlite3, json, base64, zlib, re, pathlib, csv, collections
import pandas as pd
ROOT=pathlib.Path('/mnt/data'); OUT=ROOT/'keiba_v48_audit_20261019';OUT.mkdir(exist_ok=True)
db=sqlite3.connect(ROOT/'jra_2023_2025.sqlite');db.row_factory=sqlite3.Row
sums={}
for t in ['races','documents','runner_results']:
 sums[t]={str(y):n for y,n in db.execute(f'SELECT year,count(*) FROM {t} GROUP BY year')}
sums['races_without_pdf']={str(y):n for y,n in db.execute('select year,count(*) from races where pdf_url is null group by year')}
sums['race_primary_key_duplicates']=db.execute('select count(*) from (select year,race_key,count(*) n from races group by year,race_key having n>1)').fetchone()[0]
sums['runner_primary_key_duplicates']=db.execute('select count(*) from (select year,race_key,horse_number,count(*) n from runner_results group by year,race_key,horse_number having n>1)').fetchone()[0]
sums['duplicate_document_hashes']=db.execute("SELECT COUNT(*)-COUNT(DISTINCT sha256) FROM documents WHERE status='text_extracted'").fetchone()[0]
pat=re.compile(r'^\s*(\d{1,2})\s+([①-⑳]|\d{1,2})\s+(.+?)\s+([牡牝セ#][０-９0-9]+)\s+(\d+(?:\.\d+)?)\s+(\S+)\s+(.+)$')
counts=[]
for r in db.execute('select d.year,d.race_key,d.extracted_text,r.race_name from documents d join races r on d.year=r.year and d.race_key=r.race_key'):
 t=r['extracted_text'] or ''; n=sum(bool(pat.match(line)) for line in t.splitlines());counts.append((r['year'],r['race_key'],r['race_name'],len(t),n))
sums['regex_candidate_total']=sum(x[4] for x in counts);sums['documents_with_regex_candidates']=sum(x[4]>0 for x in counts)
with open(OUT/'pdf_extraction_audit.csv','w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f);w.writerow(['year','race_key','race_name','text_length','pattern_candidate_rows_NOT_verified']);w.writerows(counts)
nb=json.loads((ROOT/'files'/'JRA重賞3年分_予測システム_v6.ipynb').read_text());source=''.join(nb['cells'][1]['source']);m=re.search(r"b64decode\('([^']+)'\)",source);bundle=json.loads(zlib.decompress(base64.b64decode(m.group(1))))
rr=pd.DataFrame(bundle['data']['runners']);gr=pd.DataFrame(bundle['data']['races']);non=pd.read_csv(ROOT/'files'/'full_non_graded_results.csv',low_memory=False)
for d in [rr,non]:d['date']=pd.to_datetime(d['date'])
print('GRADE ROWS',len(rr),'race',rr.race_id.nunique(),'YEARS',rr.groupby(rr.date.dt.year).size().to_dict())
print('NON ROWS',len(non),'race',non.race_id.nunique(),'dates',non.date.min(),non.date.max())
# Join only on provisional key and strictly earlier date; note identifier is not official.
non_by_key=collections.defaultdict(list)
for r in non[['horse_key_provisional','date','race_id','finish_order']].itertuples(index=False,name=None):
 if pd.notna(r[0]):non_by_key[str(r[0])].append((r[1],r[2],r[3]))
for key in non_by_key:non_by_key[key].sort(key=lambda r:r[0])
rows=[]
for r in rr.itertuples(index=False):
 h=non_by_key.get(r.horse_key,[])
 past=[x for x in h if x[0]<r.date]
 rows.append([r.race_id,r.date.date().isoformat(),r.horse_key,len(past),len(h)])
with open(OUT/'graded_non_graded_linkage_diagnostic.csv','w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['race_id','graded_race_date','provisional_horse_key','non_graded_prior_starts','non_graded_observed_all_dates']);w.writerows(rows)
links=pd.DataFrame(rows,columns=['race_id','date','key','prior','all'])
link2025=links[links.date.str.startswith('2025')]
late=link2025[link2025.date>='2025-10-04']
metrics=bundle['report']['test_2025']
summary={
  'fresh_sqlite_audit':sums,
  'older_graded_archived':{'race_count':len(gr),'runner_rows':len(rr),'per_year_race_count':gr.groupby('year').size().to_dict()},
  'non_graded_archived':{'race_count':int(non.race_id.nunique()),'runner_rows':len(non),'range_start':str(non.date.min().date()),'range_end':str(non.date.max().date()),'horse_ids_verified':int((non.horse_id_verified==1).sum()),'jockey_ids_verified':int((non.jockey_verified==1).sum())},
  'cross_dataset_provisional_links':{'graded_runner_rows_with_prior_non_graded_in_observation_window':int((links.prior>0).sum()),'graded_runner_rows_2025_with_prior_non_graded':int((link2025.prior>0).sum()),'graded_2025_rows_after_observation_starts':len(late),'graded_2025_rows_after_observation_with_prior_non_graded':int((late.prior>0).sum())},
  'older_2025_historical_backtest_NOT_new_holdout':metrics,
  'limits':['2025 model test already informed later development and is not unseen for v4.8','non-graded file only starts 2025-10-04; cannot be used for most 2025 graded races','horse_key_provisional is not a verified JRA horse ID','PDF regex candidate lines are not certified full-field runner rows','pre-race odds snapshots unavailable; EV not validated']}
(OUT/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=int),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2,default=int))

