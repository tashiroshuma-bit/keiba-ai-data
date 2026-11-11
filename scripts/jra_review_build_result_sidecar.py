"""Materialize grade-separated JRA official review outcomes; never mutate canonical.
Input audit is independently parsed from SHA-verified original official JRA HTML.
Non-finish statuses are NULL rank, and numerical dead-heats retain official ranks.
"""
import sqlite3, json, hashlib, pathlib,collections,datetime
SOURCE=pathlib.Path('/mnt/data/jra_review_all1975_reconciled_20261111.json')
OUT=pathlib.Path('/mnt/data/jra_review_1975_result_grade_overlay_final_20261111.sqlite')
REVIEW=json.loads(SOURCE.read_text())
if OUT.exists():OUT.unlink()
con=sqlite3.connect(OUT)
con.executescript('''
create table review_race_evidence (
 race_id text primary key, race_date text, source_url text, source_sha256 text, source_archive text,
 source_field_size integer, actual_finishers integer, nonfinishers integer, name_mismatch_count integer,
 rank_corrected_rows integer, review_grade text not null, original_issues_json text not null,
 status text not null default 'research_only_not_canonical_status_promotion');
create table review_runner_evidence (
 race_id text not null, horse_number integer not null, horse_name_official text,
 horse_id_official text, official_rank integer, official_status text not null,
 original_canonical_finish_order integer, official_profile_url text,
 source_sha256 text not null, name_match integer not null,
 primary key(race_id,horse_number));
create index review_runner_horse_id on review_runner_evidence(horse_id_official);
''')
audit=REVIEW['official_result_races']; cnt=collections.Counter()
for rid,r in audit.items():
 rows=r['runners'];parsed_diffs={d['horse_number']:d for d in r['rank_discrepancies']}
 bad_names={d['horse_number'] for d in r['name_discrepancies']}
 non=sum(not x['official_rank_text'].isdigit() for x in rows)
 numeric=sum(x['official_rank_text'].isdigit() for x in rows)
 if r['name_discrepancies']:grade='OFFICIAL_ROSTER_PARTIAL_NAME_CONFLICT_REVIEW'
 elif non:grade='OFFICIAL_ORDER_VERIFIED_SPECIAL_RESULTS_HANDLED'
 elif not (r['date'] and r['track'] and r['surface'] and r['distance']):grade='OFFICIAL_ORDER_VERIFIED_METADATA_MISSING'
 else:grade='OFFICIAL_FULL_NUMERIC_RESULT_VERIFIED'
 cnt[grade]+=1
 con.execute('insert into review_race_evidence (race_id,race_date,source_url,source_sha256,source_archive,source_field_size,actual_finishers,nonfinishers,name_mismatch_count,rank_corrected_rows,review_grade,original_issues_json) values (?,?,?,?,?,?,?,?,?,?,?,?)', (rid,r['date'],r['official_url'],r['source_sha256'],r['source_archive'],len(rows),numeric,non,len(r['name_discrepancies']),len(r['rank_discrepancies']),grade,json.dumps(r['issues'],ensure_ascii=False)))
 for idx,x in enumerate(rows,1):
  text=x['official_rank_text'];ranking=int(text) if text.isdigit() else None
  orig=parsed_diffs.get(x['num'],{}).get('db_rank',idx)
  if ranking is None:status={'中止':'DNF','取消':'SCRATCH','除外':'EXCLUDED'}.get(text,'UNKNOWN_NONFINISH')
  else:status='FINISHED'
  con.execute('insert into review_runner_evidence (race_id,horse_number,horse_name_official,horse_id_official,official_rank,official_status,original_canonical_finish_order,source_sha256,name_match) values (?,?,?,?,?,?,?,?,?)', (rid,x['num'],x['official_name'],x['horse_id'],ranking,status,orig,r['source_sha256'],int(x['num'] not in bad_names)))
con.execute('''create table review_cancelled_race_evidence (
 race_id text primary key, inferred_date text, official_pdf_url text not null, extracted_text_excerpt text,
 evidence_grade text not null, original_pdf_sha256_verified integer not null default 0)''')
for cancelled in REVIEW['whole_race_cancelled_pdf_text']:
 con.execute('insert into review_cancelled_race_evidence (race_id,inferred_date,official_pdf_url,extracted_text_excerpt,evidence_grade) values (?,?,?,?,?)',
    (cancelled['race_id'],cancelled['inferred_same_card_date'],cancelled['pdf_url'],cancelled['pdf_extracted_text_excerpt'],cancelled['label']))
con.commit()
assert con.execute('select count(*) from review_cancelled_race_evidence').fetchone()[0]==9
assert con.execute('select count(*) from review_race_evidence').fetchone()[0]==1966
assert con.execute('select count(*) from review_runner_evidence where official_rank is null').fetchone()[0]==1511
assert con.execute('select count(*) from review_runner_evidence where name_match=0').fetchone()[0]==10
assert con.execute('select count(*) from review_race_evidence where review_grade="OFFICIAL_FULL_NUMERIC_RESULT_VERIFIED"').fetchone()[0]==615
assert con.execute('pragma quick_check').fetchone()[0]=='ok'
print(json.dumps({'grade_counts':cnt,'races':1966,'official_rows':con.execute('select count(*) from review_runner_evidence').fetchone()[0], 'nonfinish':1511, 'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(), 'size':OUT.stat().st_size},ensure_ascii=False))
con.close()