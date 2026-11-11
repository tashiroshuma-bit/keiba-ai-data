"""SHA-check 16 newly sourced JRA official result dates and reconcile the last 69 dated review races.
Nine undated empty panels are classified as original PDF race-cancellation records,
not as normal result races, subject to independent JRA PDF source proof.
"""
import zipfile,json,glob,hashlib,sqlite3,re,unicodedata,collections
from lxml import html
from pathlib import Path
ROOT=Path('/mnt/data')
DB=ROOT/'jra_recovery_20261111/roundtrip/jra_2023_2025_v12_horse_ids_full_20261111.sqlite'
BASE=ROOT/'jra_review_official_rank_audit.json'
OUT=ROOT/'jra_review_all1975_reconciled_20261111.json'
d=json.loads(BASE.read_text());missing=set(d['no_source']);review=d['records'];c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
rows=collections.defaultdict(dict)
for rid,num,name,hid,rank in c.execute("select x.race_id,x.horse_number,x.horse_name,x.horse_id,x.finish_order from annual_report_runners x join annual_report_races r using(race_id) where r.status='requires_review'"):
 rows[rid][num]={'horse_name':name,'horse_id':hid,'rank':rank}
info={rid:{'date':date,'expected':expected,'issues':json.loads(issues),'track':track,'surface':surface,'distance':distance} for rid,date,expected,issues,track,surface,distance in c.execute("select race_id,race_date,expected_runners,issues_json,track,surface,distance_m from annual_report_races where status='requires_review'")}

def normalize(s):return re.sub(r'\(cid:\d+\)','',unicodedata.normalize('NFKC',s or '')).replace(' ','').replace('　','').replace('・','')
new=0;source_verified=0;alerts=[]
for zip_path in sorted(ROOT.glob('jra-review-missing16-shard-*-20261111.zip')):
 with zipfile.ZipFile(zip_path) as z:
  for manifest in [n for n in z.namelist() if n.endswith('official_race_horse_ids.json')]:
   d0=json.loads(z.read(manifest));pref=manifest.rsplit('/',1)[0]+'/' if '/' in manifest else ''
   for r in d0['records']:
    rid=r['race_id']
    if rid not in missing:continue
    if rid in review:raise RuntimeError('duplicate same review race from multiple new archives '+rid)
    raw=z.read(pref+'raw/'+r['source_sha256']+'.bin')
    if hashlib.sha256(raw).hexdigest()!=r['source_sha256']:raise ValueError('original JRA source SHA mismatch '+rid)
    source_verified+=1
    tree=html.fromstring(raw.decode('cp932','replace'))
    entries=[];seen=set()
    horse_lookup={x['horse_number']:x for x in r['horses']}
    for a in tree.xpath('//a[contains(@href,"pw01dud")]'):
     tr=a.xpath('ancestor::tr[1]')
     if not tr:continue
     td=tr[0].xpath('./td')
     if len(td)<4:continue
     n=''.join(td[2].itertext()).strip()
     if not n.isdigit():continue
     num=int(n)
     if num in seen:continue
     seen.add(num)
     if num not in horse_lookup:raise ValueError('profile URL parsed official runner not in evidence manifest')
     entries.append({'num':num,'official_rank_text':''.join(td[0].itertext()).strip(),
                     'official_name':''.join(td[3].itertext()).strip(),'horse_id':horse_lookup[num]['horse_id']})
    if len(entries)!=len(r['horses']):raise ValueError('official HTML full field size mismatch '+rid)
    old=rows[rid];name_diffs=[];rank_diffs=[];missing_numbers=[]
    for position,rr in enumerate(entries,1):
     p=old.get(rr['num']);
     if p is None:missing_numbers.append(rr['num']);continue
     if normalize(p['horse_name'])!=normalize(rr['official_name']):
      name_diffs.append({'horse_number':rr['num'],'db_name':p['horse_name'],'official_name':rr['official_name']})
     o=rr['official_rank_text'];
     if (o.isdigit() and int(o)!=p['rank']) or (not o.isdigit() and p['rank'] is not None):
      rank_diffs.append({'horse_number':rr['num'],'db_rank':p['rank'],'official_rank':o})
     if p['horse_id'] and p['horse_id']!=rr['horse_id']:raise ValueError('horse-ID conflict '+rid)
    actual=info[rid]
    review[rid]={**actual,'official_url':r['source_url'],'source_sha256':r['source_sha256'],
                'source_archive':zip_path.name,'runners':entries,
                'non_finish_codes':sorted(set(x['official_rank_text'] for x in entries if not x['official_rank_text'].isdigit())),
                'rank_discrepancies':rank_diffs,'name_discrepancies':name_diffs,
                'missing_numbers':missing_numbers,'actual_field_size':sum(x['official_rank_text'].isdigit() for x in entries),
                'all_official_positions_numeric':all(x['official_rank_text'].isdigit() for x in entries)}
    new+=1
remaining=missing-set(review)
assert new==69,(new,len(remaining))
assert len(remaining)==9,(len(remaining),sorted(remaining))
cancelled=[]
for rid in sorted(remaining):
 row=c.execute('select race_date,issues_json,metadata_json,document_url from annual_report_races where race_id=?',(rid,)).fetchone()
 meta=json.loads(row[2]);
 if rows.get(rid) or row[0] is not None or '競 走 の 中 止' not in meta.get('raw_text',''):
  raise ValueError('unexpected missing official page, not a confirmed empty cancellation '+rid)
 dayrow=c.execute('select race_date from annual_report_races where substr(race_id,1,10)=? and race_date is not null limit 1',(rid[:10],)).fetchone()
 cancelled.append({'race_id':rid,'inferred_same_card_date':dayrow[0] if dayrow else None,'pdf_url':row[3],
 'pdf_extracted_text_excerpt':meta['raw_text'][:100],'label':'JRA_ANNUAL_PDF_TEXT_WHOLE_RACE_CANCELLED_NO_RESULT',
 'official_pdf_original_bytes_reverified':False,'result_runners':0})
metrics=collections.Counter();grades=collections.Counter()
for rid,r in review.items():
 metrics['official_races']+=1;metrics['official_rows']+=len(r['runners'])
 num=[x for x in r['runners'] if x['official_rank_text'].isdigit()]
 non=len(r['runners'])-len(num)
 metrics['nonfinish_rows']+=non;metrics['numeric_rank_rows']+=len(num)
 metrics['rank_discrepancy_rows']+=len(r['rank_discrepancies'])
 metrics['numeric_rank_discrepancy_rows']+=sum(d['official_rank'].isdigit() for d in r['rank_discrepancies'])
 metrics['name_discrepancy_rows']+=len(r['name_discrepancies'])
 for x in r['runners']:
  if not x['official_rank_text'].isdigit():metrics['status_'+x['official_rank_text']]+=1
 if r['name_discrepancies']:grade='OFFICIAL_ROSTER_PARTIAL_NAME_CONFLICT_REVIEW'
 elif non:grade='OFFICIAL_ORDER_VERIFIED_SPECIAL_RESULTS_HANDLED'
 elif not all((r['date'],r['track'],r['surface'],r['distance'])):grade='OFFICIAL_ORDER_VERIFIED_METADATA_MISSING'
 else:grade='OFFICIAL_FULL_NUMERIC_RESULT_VERIFIED'
 grades[grade]+=1
metrics['not_raced_cancelled_pdf_text']=len(cancelled)
result={'schema':'jra-review-1975-final-audit-20261111','v12_sha256':hashlib.sha256(DB.read_bytes()).hexdigest(),
 'source_47_zip_sha256':'65fbe2ac1093bac6aea2ecfbd796d856467327751884762e66963f7344e607e6',
 'additional_new_official_zip_files':[p.name for p in sorted(ROOT.glob('jra-review-missing16-shard-*-20261111.zip'))],
 'additional_new_races':new,'additional_raw_sources_sha_verified':source_verified,
 'metrics':dict(metrics),'grade_counts':dict(grades),'review_races':len(info),
 'official_result_races':review,'whole_race_cancelled_pdf_text':cancelled,'no_other_unknown_races':len(review)+len(cancelled)==1975}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'new_races':new,'metrics':metrics,'grade_counts':grades,'nine_cancelled':[x['race_id'] for x in cancelled]},ensure_ascii=False,indent=2))