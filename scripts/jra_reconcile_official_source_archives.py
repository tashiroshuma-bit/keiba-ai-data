"""Verify JRA original result HTML and merge authentic horse IDs into a sidecar.

Uses only validated canonical races, a read-only canonical database, and actual
JRA source bytes from original GitHub Actions ZIPs; never guesses missing IDs.
A matching horse number and normalized Japanese name must agree. Previous
profile-based candidates are kept but marked weaker, and official race links
supersede them without silently resolving contradictory IDs.
"""
import argparse
import collections
import csv
import hashlib
from html.parser import HTMLParser
import json
import re
import sqlite3
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urljoin,unquote,urlsplit

RESULT_RE=re.compile(r'pw01sde(?:10|01)([0-9]{2})(20[0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})(20[0-9]{6})/(?:[0-9A-F]{2})',re.I)
HORSE_RE=re.compile(r'pw01dud[0-9]*?(20[0-9]{8})/(?:[0-9A-F]{2})',re.I)


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as fp:
        for part in iter(lambda:fp.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def name_normalized(name):
    s=unicodedata.normalize('NFKC',str(name or ''))
    return ''.join(s.split())


def name_pdf_glyph_corrected(name):
    s=name_normalized(name)
    return re.sub(r'^(?:\(cid:\d+\))+','',s)


def url_race_id(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!='www.jra.go.jp' or p.path!='/JRADB/accessS.html':return None
    m=RESULT_RE.search(unquote(url))
    if not m:return None
    venue,year,meet,day,race,calendar=m.groups()
    if calendar[:4]!=year:return None
    return year+venue+meet+day+race


class RaceRows(HTMLParser):
    def __init__(self,base):
        super().__init__(convert_charrefs=True)
        self.base=base;self.depth=0;self.cells=[];self.current=None;self.runners=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='tr':
            self.depth+=1
            if self.depth==1:self.cells=[];self.current=None
        elif tag=='td' and self.depth==1:
            self.current={'text':'','horses':[]};self.cells.append(self.current)
        elif tag=='a' and self.current is not None and d.get('href'):
            u=urljoin(self.base,d['href']);m=HORSE_RE.search(unquote(u))
            if m and urlsplit(u).hostname=='www.jra.go.jp':self.current['horses'].append('jra:'+m.group(1))
    def handle_data(self,data):
        if self.current is not None:self.current['text']+=data
    def handle_endtag(self,tag):
        if tag=='td' and self.depth==1:self.current=None
        elif tag=='tr' and self.depth:
            self.depth-=1
            if self.depth==0 and len(self.cells)>=4:
                n=self.cells[2]['text'].strip()
                c=self.cells[3];name=name_normalized(c['text'])
                if n.isdigit() and 1<=int(n)<=30 and name and len(c['horses'])==1:
                    self.runners.append((int(n),name,c['horses'][0]))


def parse_original(blob,url):
    decoded=None
    for encoding in ('cp932','shift_jis','utf-8'):
        try:decoded=blob.decode(encoding);break
        except UnicodeDecodeError:pass
    if decoded is None:decoded=blob.decode('cp932',errors='replace')
    p=RaceRows(url);p.feed(decoded)
    if len(p.runners)<3:raise ValueError('official original contains fewer than 3 horse rows')
    if len(set(n for n,_,_ in p.runners))!=len(p.runners):raise ValueError('duplicate horse numbers')
    if len(set(h for _,_,h in p.runners))!=len(p.runners):raise ValueError('duplicate IDs')
    return {n:(name,hid) for n,name,hid in p.runners}


def load_archive_results(path):
    """Yield a JRA manifest record with immutable ZIP provenance, verify bytes.

    Supports both old one-manifest ZIPs and new ISO-week shard ZIPs.
    """
    with zipfile.ZipFile(path,'r') as archive:
        names=set(archive.namelist())
        manifests=sorted(n for n in names if n.endswith('official_race_horse_ids.json'))
        for fname in manifests:
            manifest=json.loads(archive.read(fname))
            if manifest.get('schema')!='jra-official-raw-results-horse-id-recovery-v1':
                raise ValueError('unexpected official JRA manifest')
            parent=fname[:-len('official_race_horse_ids.json')]
            for item in manifest['records']:
                race=item.get('race_id');url=item.get('source_url')
                if url_race_id(url)!=race:raise ValueError('JRA source URL/race ID mismatch')
                checksum=item.get('source_sha256','')
                if not re.fullmatch(r'[0-9a-f]{64}',checksum):raise ValueError('bad original hash')
                raw_path=parent+'raw/'+checksum+'.bin'
                if raw_path not in names:raise ValueError('original JRA HTML missing '+race)
                data=archive.read(raw_path)
                if hashlib.sha256(data).hexdigest()!=checksum:
                    raise ValueError('original HTML checksum mismatch '+race)
                confirmed=parse_original(data,url)
                claimed={(int(r['horse_number']),name_normalized(r['horse_name']),r['horse_id'])
                         for r in item['horses']}
                if claimed!={(n,name,hid) for n,(name,hid) in confirmed.items()}:
                    raise ValueError('horse ID manifest differs from JRA original '+race)
                yield item,confirmed,{'zip_name':Path(path).name,'zip_member':raw_path}


def reconcile(canonical_path,base_overlay_path,archives,output_dir,
              *,expected_sha='7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627'):
    target=Path(output_dir)
    if target.exists() and any(target.iterdir()):raise FileExistsError('destination must be empty')
    target.mkdir(parents=True,exist_ok=True)
    source_sha=digest(canonical_path)
    if expected_sha and source_sha!=expected_sha:raise ValueError('canonical v11 SHA mismatch')
    db=sqlite3.connect(Path(canonical_path).resolve().as_uri()+'?mode=ro',uri=True)
    base=sqlite3.connect(Path(base_overlay_path).resolve().as_uri()+'?mode=ro',uri=True)
    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('canonical SQLite not intact')
    if base.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('base overlay not intact')
    current={}
    for rid,num,name,hid,day,method,url in base.execute('select race_id,horse_number,horse_name,horse_id,race_date,method,source_url from horse_identity_overlay'):
        current[(rid,int(num))]={'race_id':rid,'number':int(num),'name':name,'horse_id':hid,
           'race_date':day,'method':method,'url':url}
    evidence={}
    for rid,num,hid,url,sha,observed in base.execute('select race_id,horse_number,horse_id,source_url,source_sha256,observed_at from official_direct_evidence'):
        evidence[(rid,int(num))]={'horse_id':hid,'source_url':url,'source_sha256':sha,'observed_at':observed,
                                   'zip_name':'prior_source_archive','zip_member':None}
    previous={k:v['horse_id'] for k,v in current.items()}
    stats=collections.Counter();rejections=[];source_races=set();target_races=set();byyear=collections.Counter()
    known_races={r[0]:(r[1],r[2]) for r in db.execute("select race_id,race_date,status from annual_report_races")}
    canonical_by_race=collections.defaultdict(dict)
    for rid,num,name,hid in db.execute('select race_id,horse_number,horse_name,horse_id from annual_report_runners'):
        if rid in known_races and known_races[rid][1]=='validated_result':
            canonical_by_race[rid][int(num)]=(name,hid)
            if hid is None:target_races.add(rid)
    for archive in archives:
        stats['archive_files']+=1
        try:
            iterator=load_archive_results(archive)
            for item,confirmed,provenance in iterator:
                rid=item['race_id'];stats['downloaded_primary_pages']+=1
                if rid in source_races:
                    stats['duplicate_source_pages']+=1
                    # May contain different bytes but should never conflict on existing source IDs.
                source_races.add(rid)
                if rid not in target_races:
                    stats['not_target_validated_races']+=1;continue
                match=RESULT_RE.search(unquote(item['source_url']))
                raw_day=match.group(6)
                official_day=raw_day[:4]+'-'+raw_day[4:6]+'-'+raw_day[6:8]
                if known_races[rid][0]!=official_day:
                    stats['official_result_date_conflicts']+=1
                    rejections.append({'race_id':rid,'reason':'source_calendar_date_conflict',
                                       'official_date':official_day,'canonical_date':known_races[rid][0]})
                    continue
                stats['target_races_seen']+=1
                local=canonical_by_race.get(rid,{})
                for num,(name,hid) in confirmed.items():
                    key=(rid,num)
                    old=local.get(num)
                    if old is None:
                        stats['not_in_canonical_runner_number']+=1
                        continue
                    historic_name,existing_id=old
                    if existing_id is not None:
                        if existing_id!=hid:
                            stats['known_id_conflicts']+=1
                            rejections.append({'race_id':rid,'horse_number':num,'reason':'known_id_conflict',
                                               'canonical_id':existing_id,'jra_official_id':hid})
                        else:stats['already_in_canonical']+=1
                        continue
                    if name_normalized(historic_name)!=name:
                        if name_pdf_glyph_corrected(historic_name)==name:
                            stats['pdf_cid_prefix_normalization']+=1
                        else:
                            stats['horse_name_conflicts']+=1
                            rejections.append({'race_id':rid,'horse_number':num,'reason':'horse_name_conflict',
                                               'canonical_name':historic_name,'official_name':name})
                            continue
                    if key in previous and previous[key]!=hid:
                        stats['profile_candidate_conflicts']+=1
                        rejections.append({'race_id':rid,'horse_number':num,'reason':'profile_id_conflict',
                                           'profile_candidate':previous[key],'official_id':hid})
                        continue
                    if key in evidence:
                        if evidence[key]['horse_id']!=hid:
                            stats['two_official_source_conflicts']+=1
                            rejections.append({'race_id':rid,'horse_number':num,'reason':'two_official_sources_disagree'})
                        else:stats['repeat_direct_id_evidence']+=1
                        continue
                    evidence[key]={'horse_id':hid,'source_url':item['source_url'],
                        'source_sha256':item['source_sha256'],'observed_at':item['observed_at'],**provenance}
                    current[key]={'race_id':rid,'number':num,'name':name,'horse_id':hid,
                                  'race_date':known_races[rid][0],
                                  'method':'JRA_OFFICIAL_RACE_ROW_DIRECT','url':item['source_url']}
                    stats['new_direct_id_rows']+=1
                    byyear[rid[:4]]+=1
        except Exception as exc:
            stats['archive_parse_errors']+=1
            rejections.append({'archive_file':Path(archive).name,'reason':'archive_validation_failed',
                               'error':type(exc).__name__+': '+str(exc)[:300]})
    db.close();base.close()
    outdb=target/'horse_id_overlay_source_verified.sqlite'
    conn=sqlite3.connect(outdb)
    conn.execute('CREATE TABLE horse_identity_overlay(race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,horse_id TEXT NOT NULL,race_date TEXT NOT NULL,method TEXT NOT NULL,source_url TEXT,PRIMARY KEY(race_id,horse_number))')
    conn.execute('CREATE TABLE official_direct_evidence(race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_id TEXT NOT NULL,source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,PRIMARY KEY(race_id,horse_number))')
    conn.execute('CREATE TABLE evidence_archive_locator(race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,zip_name TEXT NOT NULL,zip_member TEXT,PRIMARY KEY(race_id,horse_number))')
    for k,x in sorted(current.items()):
        conn.execute('insert into horse_identity_overlay values(?,?,?,?,?,?,?)',(x['race_id'],x['number'],x['name'],x['horse_id'],x['race_date'],x['method'],x['url']))
    for (rid,num),x in sorted(evidence.items()):
        conn.execute('insert into official_direct_evidence values(?,?,?,?,?,?)',(rid,num,x['horse_id'],x['source_url'],x['source_sha256'],x['observed_at']))
        conn.execute('insert into evidence_archive_locator values(?,?,?,?)',(rid,num,x['zip_name'],x['zip_member']))
    conn.commit();quick=conn.execute('pragma quick_check').fetchone()[0]
    if quick!='ok':raise ValueError('merged overlay is corrupt')
    totals={x:conn.execute('select count(*) from '+x).fetchone()[0]
            for x in ('horse_identity_overlay','official_direct_evidence')}
    conn.close()
    original_nulls=[(rid,num,name) for rid,rows in canonical_by_race.items()
                    for num,(name,hid) in rows.items() if hid is None]
    total_null=len(original_nulls)
    rejection_reasons={(a.get('race_id'),a.get('horse_number')):a['reason']
                       for a in rejections if a.get('horse_number') is not None}
    unresolved_by_reason=collections.Counter()
    with (target/'unresolved_rows.csv').open('w',newline='',encoding='utf-8') as missing_out:
        w=csv.writer(missing_out)
        w.writerow(['race_id','horse_number','horse_name','race_date','blocker'])
        for rid,num,name in sorted(original_nulls):
            if (rid,num) in current:continue
            if rid not in source_races:reason='official_source_page_not_yet_observed'
            else:reason=rejection_reasons.get((rid,num),'official_runner_id_not_matching_or_absent')
            unresolved_by_reason[reason]+=1
            w.writerow([rid,num,name,known_races[rid][0],reason])
    report={'status':'PARTIAL_SOURCE_BACKED_ID_RECOVERY_NEVER_GUESS',
            'schema':'jra-horse-full-unresolved-source-reconciliation-v1',
            'canonical_sha256':source_sha,'canonical_mutated':False,
            'base_overlay_sha256':digest(base_overlay_path),
            'new_overlay_sha256':digest(outdb),'sqlite_quick_check':quick,
            'archives_received':len(archives),'verified_original_source_pages':len(source_races),
            'canonical_races_with_missing_ids':len(target_races),
            'still_no_official_source_race_pages':len(target_races-source_races),
            'new_official_direct_rows':stats['new_direct_id_rows'],
            'new_direct_rows_by_year':dict(sorted(byyear.items())),
            'official_direct_confirmed_rows':totals['official_direct_evidence'],
            'profile_only_candidate_rows':totals['horse_identity_overlay']-totals['official_direct_evidence'],
            'total_covered_rows_in_sidecar':totals['horse_identity_overlay'],
            'total_original_canonical_null_rows':total_null,
            'remaining_without_any_id_candidate':total_null-totals['horse_identity_overlay'],
            'remaining_without_direct_official_confirmation':total_null-totals['official_direct_evidence'],
            'statistics':dict(stats),'unresolved_by_reason':dict(unresolved_by_reason),
            'unresolved_csv':'unresolved_rows.csv','rejected_rows':rejections,
            'input_archives':[{'file':Path(a).name,'sha256':digest(a)} for a in archives]}
    (target/'identity_source_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (target/'rejected_rows.csv').open('w',newline='',encoding='utf-8') as out:
        fields=['race_id','horse_number','reason','canonical_name','official_name','canonical_id','jra_official_id','profile_candidate','official_id','archive_file','error']
        w=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rejections)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--canonical',required=True)
    p.add_argument('--base-overlay',required=True)
    p.add_argument('--archives',nargs='+',required=True)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args()
    report=reconcile(a.canonical,a.base_overlay,a.archives,a.output_dir)
    print(json.dumps({key:report[key] for key in ('verified_original_source_pages','new_official_direct_rows',
       'official_direct_confirmed_rows','total_covered_rows_in_sidecar','remaining_without_any_id_candidate','statistics')},ensure_ascii=False))

if __name__=='__main__':main()