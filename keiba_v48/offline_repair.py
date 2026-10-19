"""Repair payout coverage from verified saved PDFs; retain clock uncertainty."""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

from pypdf import PdfReader
from pdf_payouts import decode_payouts


def pdf_info(job):
    url,sha,raw=job
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('saved PDF checksum mismatch: '+url)
    reader=PdfReader(io.BytesIO(raw));metadata=reader.metadata
    created=metadata.creation_date;modified=metadata.modification_date
    return dict(url=url,sha256=sha,creation_raw=metadata.get('/CreationDate'),modification_raw=metadata.get('/ModDate'),
                creation_timestamp=created.isoformat() if created else None,modification_timestamp=modified.isoformat() if modified else None,
                clock_consistent=created<=modified if created and modified else None,
                availability_usage='artifact_metadata_only_never_historical_publication_proof')


def repair(base,destination,pdf_archives):
    dest=Path(destination)
    if dest.exists():raise ValueError('new output required')
    src=sqlite3.connect('file:'+str(Path(base).resolve())+'?mode=ro',uri=True)
    if src.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise ValueError('base integrity failed')
    db=sqlite3.connect(':memory:');src.backup(db);src.close()
    docs={url:(sha,observed) for url,sha,observed in db.execute('select url,sha256,fetched_at from annual_report_documents')}
    archives=[zipfile.ZipFile(p) for p in pdf_archives];members={}
    for z in archives:
        for n in z.namelist():
            if n.endswith('.pdf'):
                name=Path(n).name
                if name in members:raise ValueError('duplicate saved PDF filename')
                members[name]=(z,n)
    jobs=[]
    for url,(sha,_) in docs.items():
        if Path(url).name not in members:raise ValueError('saved original missing: '+url)
        z,n=members[Path(url).name];jobs.append((url,sha,z.read(n)))
    with cf.ProcessPoolExecutor(max_workers=4) as pool:info=list(pool.map(pdf_info,jobs,chunksize=4))
    for z in archives:z.close()
    db.executescript('''CREATE TABLE IF NOT EXISTS pdf_payout_evidence(
        race_id TEXT PRIMARY KEY,payouts_json TEXT NOT NULL,proof_json TEXT NOT NULL,
        source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS document_artifact_times(
        document_url TEXT PRIMARY KEY,source_sha256 TEXT NOT NULL,payload_json TEXT NOT NULL);''')
    for row in info:db.execute('insert or replace into document_artifact_times values(?,?,?)',(row['url'],row['sha256'],json.dumps(row)))
    decoded=0;errors=[];overlap=0;conflicts=[]
    rich={rid:json.loads(p) for rid,p in db.execute('select race_id,payload_json from enriched_results')}
    for rid,url,metadata in db.execute("select race_id,document_url,metadata_json from annual_report_races where status='validated_result'").fetchall():
        meta=json.loads(metadata);ranks={str(n):json.loads(p)['finish_position'] for n,p in db.execute('select horse_number,payload_json from annual_report_runners where race_id=?',(rid,))}
        try:payouts,proof=decode_payouts(meta['raw_text'],ranks,meta.get('win_payout_100'))
        except ValueError as e:errors.append(dict(race_id=rid,error=str(e)));continue
        if rid in rich:
            overlap+=1
            if payouts!=rich[rid]['payouts']:conflicts.append(rid);continue
        proof.update(raw_text_sha256=hashlib.sha256(meta['raw_text'].encode()).hexdigest(),verified_pdf_sha256=docs[url][0])
        db.execute('insert or replace into pdf_payout_evidence values(?,?,?,?,?,?)',(rid,json.dumps(payouts,sort_keys=True),json.dumps(proof),url,*docs[url]));decoded+=1
    if conflicts:raise ValueError('PDF/HTML payout disagreement: '+str(conflicts[:10]))
    voids={r[0] for r in db.execute('select race_id from official_void_races')}
    for url,error in db.execute("select source_url,error from official_linkage_pages where status='error'").fetchall():
        from official_linkage import race_key
        key=race_key(url)
        if key and key[0] in voids:db.execute("update official_linkage_pages set status='official_void',error=NULL where source_url=?",(url,))
    report=dict(verified_saved_pdf_documents=len(info),decoded_payout_races=decoded,payout_keys=decoded*5,decoding_errors=errors,
                independent_html_comparisons=overlap,independent_html_disagreements=conflicts,
                artifact_clock_conflict_documents=sum(r['clock_consistent'] is False for r in info),
                artifact_times_usage='do_not_use_as_result_publication_time',historical_publication_times_fabricated=0,
                integrity_check=db.execute('pragma integrity_check').fetchone()[0],foreign_key_violations=len(db.execute('pragma foreign_key_check').fetchall()))
    db.commit();db.execute('VACUUM');dest.parent.mkdir(parents=True,exist_ok=True)
    target=sqlite3.connect(dest);db.backup(target);target.close();db.close()
    check=sqlite3.connect('file:'+str(dest.resolve())+'?mode=ro',uri=True)
    if check.execute('pragma integrity_check').fetchall()!=[('ok',)] or check.execute('pragma foreign_key_check').fetchall():raise ValueError('repaired DB integrity failed')
    check.close();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',required=True);p.add_argument('--db',required=True);p.add_argument('--pdf-archives',nargs='+',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    result=repair(a.base,a.db,a.pdf_archives);Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)
