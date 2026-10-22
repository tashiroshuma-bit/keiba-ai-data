"""Saved-byte profile audit; do not fetch result/profile links or infer IDs."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urljoin
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from official_linkage import profile_key,parse_html,parse_profile_starts,race_key,official_url,JOCKEY


def audit(db_path,cache):
    db=sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True);counts=collections.Counter();sources=[];candidates=[]
    before=hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    for path in sorted(Path(cache).glob('*.json')):
        m=json.loads(path.read_text());hid=profile_key(m['url']);raw=path.with_suffix('.html')
        if not hid or not raw.exists():continue
        body=raw.read_bytes()
        if hashlib.sha256(body).hexdigest()!=m['sha256']:raise ValueError('cache integrity failed')
        soup=parse_html(body,'lxml');counts['cached_profiles']+=1;sources.append({k:m[k] for k in ('url','sha256','observed_at')})
        rows=parse_profile_starts(soup,m['url']);counts['starts_with_official_jockey_code']+=len(rows)
        for r in rows:
            target=db.execute('SELECT horse_number,jockey_id FROM annual_report_runners WHERE race_id=? AND horse_id=?',(r['race_id'],hid)).fetchall()
            counts['coded_starts_matching_database_horse']+=len(target)
            for num,jid in target:
                if jid is None:candidates.append(dict(race_id=r['race_id'],horse_number=num,horse_id=hid,jockey_id=r['jockey_id'],source_url=m['url']))
        for tr in soup.select('tbody > tr'):
            race=tr.select_one('td.race a[href*="pw01sde"]');cell=tr.select_one('td.jockey')
            if not race or not cell:continue
            key=race_key(official_url(urljoin(m['url'],race['href'])))
            if not key or any(JOCKEY.search(a.get('onclick','')) for a in cell.select('a[onclick]')):continue
            counts['starts_without_official_jockey_code']+=1
            counts['uncoded_starts_matching_missing_database_jockey']+=db.execute('SELECT count(*) FROM annual_report_runners WHERE race_id=? AND horse_id=? AND jockey_id IS NULL',(key[0],hid)).fetchone()[0]
    db.close();assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest()==before
    return dict(schema='keiba-cached-profile-id-audit-v1',input_db_sha256=before,counts=dict(counts),sources=sources,
        additional_jockey_candidates=len(candidates),candidates=candidates,network_requests=0,database_unchanged=True,
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('db','cache','output'):p.add_argument('--'+k,required=True)
    a=p.parse_args();r=audit(a.db,a.cache);Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(counts=r['counts'],additional_candidates=r['additional_jockey_candidates'])))
