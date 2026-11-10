"""Build immutable candidate and independently JRA-result-confirmed horse ID sidecar.

No mutation of canonical v11. Direct JRA race-row evidence outranks profile-only
historical name+birthyear inference. A conflicting identity aborts the merge.
"""
import argparse,hashlib,json,os,sqlite3,collections,unicodedata
from pathlib import Path

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(2**20),b''):h.update(block)
 return h.hexdigest()

def consolidate(canonical,profile_overlay,source_overlays,output):
 out=Path(output)
 if out.exists():raise FileExistsError('immutable output exists')
 src=sqlite3.connect(Path(profile_overlay).resolve().as_uri()+'?mode=ro',uri=True)
 data={}
 for rid,num,name,hid,date,method,url in src.execute('select race_id,horse_number,horse_name,horse_id,race_date,method,source_url from horse_identity_overlay'):
  data[(rid,num)]={'race_id':rid,'number':num,'name':name,'horse_id':hid,'race_date':date,'method':method,'url':url,'original_sha':None,'observed_at':None}
 src.close()
 candidate_keys=set(data)
 proof={};byinput={}
 can=sqlite3.connect(Path(canonical).resolve().as_uri()+'?mode=ro',uri=True)
 for overlay in source_overlays:
  con=sqlite3.connect(Path(overlay).resolve().as_uri()+'?mode=ro',uri=True)
  rows=con.execute('select race_id,horse_number,horse_name,horse_id,source_url,source_sha256,observed_at,evidence_level from official_race_horse_id_links').fetchall()
  for rid,num,name,hid,url,source_sha,observed_at,level in rows:
   if level!='JRA_OFFICIAL_RACE_ROW_DIRECT':raise ValueError('unverified direct source')
   key=(rid,num)
   old=can.execute('select x.horse_name,x.horse_id,r.race_date from annual_report_runners x join annual_report_races r using(race_id) where x.race_id=? and x.horse_number=? and r.status="validated_result"',key).fetchone()
   if old is None or old[1] is not None or ''.join(unicodedata.normalize('NFKC',old[0]).split()) != ''.join(unicodedata.normalize('NFKC',name).split()):raise ValueError('direct row not a matching canonical null-ID')
   if key in data and data[key]['horse_id']!=hid:raise ValueError('existing profile identity collision')
   if key in proof and proof[key]['source_sha']!=source_sha:
    if proof[key]['horse_id']!=hid:raise ValueError('two contradictory official sources')
    continue
   data[key]={'race_id':rid,'number':num,'name':name,'horse_id':hid,'race_date':old[2],
             'method':level,'url':url,'original_sha':source_sha,'observed_at':observed_at}
   proof[key]={'horse_id':hid,'source_sha':source_sha}
  byinput[str(overlay)]=len(rows)
  con.close()
 can.close()
 conn=sqlite3.connect(out)
 conn.execute('CREATE TABLE horse_identity_overlay(race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,horse_id TEXT NOT NULL,race_date TEXT NOT NULL,method TEXT NOT NULL,source_url TEXT, PRIMARY KEY(race_id,horse_number))')
 conn.execute('CREATE TABLE official_direct_evidence(race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_id TEXT NOT NULL,source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,PRIMARY KEY(race_id,horse_number))')
 for key,r in sorted(data.items()):
  conn.execute('INSERT INTO horse_identity_overlay VALUES(?,?,?,?,?,?,?)',(r['race_id'],r['number'],r['name'],r['horse_id'],r['race_date'],r['method'],r['url']))
  if r['original_sha']:conn.execute('INSERT INTO official_direct_evidence VALUES(?,?,?,?,?,?)',(r['race_id'],r['number'],r['horse_id'],r['url'],r['original_sha'],r['observed_at']))
 conn.commit()
 status=conn.execute('PRAGMA quick_check').fetchone()[0];conn.close()
 if status!='ok':raise ValueError('bad sqlite result')
 return {'profile_only_candidates':len(data)-len(proof),'official_race_direct_verified_rows':len(proof),
         'new_unique_official_rows':len(set(proof)-candidate_keys),'total_covered_rows':len(data),
         'remaining_null_ids_if_candidates_included':66360-len(data),
         'source_overlay_counts':byinput,'overlay_sha256':digest(out),'sqlite_quick_check':status,
         'canonical_sha256':digest(canonical),'canonical_modified':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--canonical',required=True);p.add_argument('--profile-overlay',required=True)
 p.add_argument('--source-overlays',nargs='+',required=True);p.add_argument('--output',required=True)
 a=p.parse_args();print(json.dumps(consolidate(a.canonical,a.profile_overlay,a.source_overlays,a.output),ensure_ascii=False,indent=2))