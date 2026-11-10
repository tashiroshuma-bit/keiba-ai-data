"""Conservative importer of JRA primary result row -> horse registration ID.

Requires original source bytes and checks race ID+horse number+exact normalized
horse name. Leaves canonical DB unchanged. Can merge an existing candidate
sidecar with priority to independent official race row evidence.
"""
import argparse,hashlib,json,os,sqlite3,unicodedata
from pathlib import Path
from urllib.parse import unquote

def normalized(name):
    return ''.join(unicodedata.normalize('NFKC',str(name)).split())

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as fp:
        for buf in iter(lambda:fp.read(2**20),b''): h.update(buf)
    return h.hexdigest()

def import_results(database,manifest_path,output_dir,prior_sidecar=None):
    root=Path(manifest_path).parent; data=json.loads(Path(manifest_path).read_bytes())
    if data['schema']!='jra-official-raw-results-horse-id-recovery-v1':raise ValueError('wrong official source schema')
    output=Path(output_dir)
    if output.exists() and any(output.iterdir()):raise FileExistsError('immutable destination already exists')
    output.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    prior={}
    if prior_sidecar:
        o=sqlite3.connect(Path(prior_sidecar).resolve().as_uri()+'?mode=ro',uri=True)
        for row in o.execute('select race_id,horse_number,horse_id from horse_identity_overlay'):
            prior[(str(row[0]),int(row[1]))]=row[2]
        o.close()
    links=[];rejected=[];source_count=0
    try:
        for race in data['records']:
            rid=race['race_id'];url=race['source_url'];finger=race['source_sha256']
            if not url.startswith('https://www.jra.go.jp/JRADB/accessS.html?'):
                raise ValueError('unapproved primary source URL')
            if len(finger)!=64 or sha(root/'raw'/(finger+'.bin'))!=finger:
                raise ValueError('source original HTML bytes absent or tampered '+rid)
            source_count+=1
            expected=con.execute('select horse_number,horse_name,horse_id from annual_report_runners where race_id=?',(rid,)).fetchall()
            bynum={int(x['horse_number']):x for x in expected}
            if not bynum:
                rejected.append({'race_id':rid,'reason':'race_absent_from_canonical'});continue
            seen=set()
            for h in race['horses']:
                n=int(h['horse_number']);key=(rid,n)
                if n in seen:raise ValueError('duplicated official horse number')
                seen.add(n)
                old=bynum.get(n)
                if old is None:
                    rejected.append({'race_id':rid,'number':n,'reason':'number_not_in_canonical'});continue
                official=normalized(h['horse_name']);canonical=normalized(old['horse_name'])
                if official!=canonical:
                    rejected.append({'race_id':rid,'number':n,'reason':'official_name_does_not_match',
                        'official':official,'canonical':canonical});continue
                hid=h['horse_id']
                if old['horse_id'] is not None:
                    if old['horse_id']!=hid:raise ValueError('conflict with existing canonical horse ID')
                    continue
                if key in prior and prior[key]!=hid:
                    rejected.append({'race_id':rid,'number':n,'reason':'conflicts_profile_candidate'});continue
                links.append({'race_id':rid,'horse_number':n,'horse_name':canonical,'horse_id':hid,
                    'source_url':url,'source_sha256':finger,'observed_at':race['observed_at'],
                    'evidence_level':'JRA_OFFICIAL_RACE_ROW_DIRECT'})
    finally:con.close()
    if len({(r['race_id'],r['horse_number']) for r in links})!=len(links):
        raise ValueError('duplicate source matches')
    db=sqlite3.connect(output/'official_race_horse_id_links.sqlite')
    db.execute('CREATE TABLE official_race_horse_id_links (race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,horse_id TEXT NOT NULL,source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,evidence_level TEXT NOT NULL, PRIMARY KEY(race_id,horse_number))')
    db.executemany('INSERT INTO official_race_horse_id_links VALUES (?,?,?,?,?,?,?,?)',[tuple(r[k] for k in ('race_id','horse_number','horse_name','horse_id','source_url','source_sha256','observed_at','evidence_level')) for r in links])
    db.commit();ok=db.execute('PRAGMA quick_check').fetchone()[0];db.close()
    if ok!='ok':raise ValueError('overlay database corruption')
    report={'schema':'jra-official-racewise-id-backfill-audit-v1','canonical_database_sha256':sha(database),
        'official_result_pages_verified':source_count,'race_rows_newly_direct_verified':len(links),
        'rejected':rejected,'links':links,'prior_candidate_links':len(prior),
        'status':'DIRECT_OFFICIAL_RACE_PROVENANCE_ROSTER_VERIFIED',
        'official_html_archive_root':str((root/'raw').resolve()),'canonical_mutation':False,
        'official_link_sqlite_sha256':sha(output/'official_race_horse_id_links.sqlite')}
    (output/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return {'newly_verified':len(links),'rejected':len(rejected),'source_pages':source_count,'sqlite_quick_check':ok, 'sqlite_sha256':report['official_link_sqlite_sha256']}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--database',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--prior-sidecar');p.add_argument('--output-dir',required=True)
    a=p.parse_args();print(json.dumps(import_results(a.database,a.manifest,a.output_dir,a.prior_sidecar),ensure_ascii=False))
if __name__=='__main__':main()