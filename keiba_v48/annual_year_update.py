"""Append verified annual PDF evidence without rebuilding earlier years."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
from pypdf import PdfReader
from offline_performance_repair import attach_corner
from pdf_performance import parse_times
from pdf_payouts import decode_payouts
from official_linkage import propagate, audit, unlinked_causes


def digest(path):
    with open(path,'rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def raw_history_digest(db, before_year):
    """Fingerprint outcome/source inputs, excluding derived identity fields."""
    h=hashlib.sha256()
    for row in db.execute('''SELECT race_id,metadata_json,issues_json,status,race_date,off_timestamp,expected_runners
          FROM annual_report_races WHERE substr(race_id,1,4)<? ORDER BY race_id''',(str(before_year),)):
        h.update(json.dumps(list(row),ensure_ascii=False,separators=(',',':')).encode())
    for rid,num,raw in db.execute('''SELECT race_id,horse_number,payload_json FROM annual_report_runners
          WHERE substr(race_id,1,4)<? ORDER BY race_id,horse_number''',(str(before_year),)):
        payload=json.loads(raw)
        for k in ('horse_id','jockey_id','identity_status'):payload.pop(k,None)
        h.update(json.dumps([rid,num,payload],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
    return h.hexdigest()


def update(base,destination,year=2026):
    destination=Path(destination)
    if destination.exists():raise ValueError('new destination required')
    src=sqlite3.connect(Path(base).resolve().as_uri()+'?mode=ro',uri=True)
    db=sqlite3.connect(':memory:');src.backup(db);src.close();db.row_factory=sqlite3.Row
    before=raw_history_digest(db,year)
    docs=list(db.execute('select * from annual_report_documents where year=?',(year,)))
    if not docs or any(d['status'] not in ('parsed','parse_review') for d in docs):
        raise ValueError('all indexed annual PDFs must finish parsing before update')
    counters=collections.Counter();rejections=[]
    for d in docs:
        path=Path(d['local_path'])
        if digest(path)!=d['sha256'] or path.stat().st_size!=d['byte_count']:
            raise ValueError('original PDF identity mismatch: '+d['url'])
        p=PdfReader(path);m=p.metadata
        created=m.creation_date;modified=m.modification_date
        proof=dict(url=d['url'],sha256=d['sha256'],creation_raw=m.get('/CreationDate'),modification_raw=m.get('/ModDate'),
                   creation_timestamp=created.isoformat() if created else None,modification_timestamp=modified.isoformat() if modified else None,
                   clock_consistent=created<=modified if created and modified else None,
                   availability_usage='artifact_metadata_only_never_historical_publication_proof')
        db.execute('insert or replace into document_artifact_times values(?,?,?)',(d['url'],d['sha256'],json.dumps(proof)))
        counters['verified_new_originals']+=1
    for r in db.execute('select * from annual_report_races where substr(race_id,1,4)=? order by race_id',(str(year),)).fetchall():
        rid=r['race_id'];meta=json.loads(r['metadata_json'])
        rows=[json.loads(x[0]) for x in db.execute('select payload_json from annual_report_runners where race_id=? order by finish_order',(rid,))]
        try:
            if not r['expected_runners']:raise ValueError('missing expected runner count')
            parsed=parse_times(rows,r['expected_runners'],json.loads(r['issues_json']),meta['raw_text'],True)
        except ValueError as exc:
            rejections.append(dict(race_id=rid,stage='performance',reason=str(exc)));continue
        doc=next(d for d in docs if d['url']==r['document_url'])
        try:
            payouts,proof=decode_payouts(meta['raw_text'],{str(x['horse_number']):x['finish_position'] for x in parsed if x['finish_position']},meta.get('win_payout_100'))
            proof.update(raw_text_sha256=hashlib.sha256(meta['raw_text'].encode()).hexdigest(),verified_pdf_sha256=doc['sha256'])
            db.execute('insert or replace into pdf_payout_evidence values(?,?,?,?,?,?)',
                       (rid,json.dumps(payouts,sort_keys=True),json.dumps(proof),doc['url'],doc['sha256'],doc['fetched_at']))
            counters['new_payout_evidence_races']+=1
        except ValueError as exc:
            rejections.append(dict(race_id=rid,stage='payout',reason=str(exc)))
            # Exceptional fields need full payout/rank corroboration.
            if r['status']!='validated_result':continue
        attached,_=attach_corner(parsed,meta['raw_text'])
        counters['new_corner_evidence_races']+=attached
        keys=('horse_number','finish_position','runner_status','finish_time_seconds','margin_seconds','relative_speed_z',
              'field_size','final_win_odds','corner4_position','corner4_range','corner4_method')
        overlay=[{k:x.get(k) for k in keys} for x in parsed]
        payload=dict(runners=overlay,active_horse_numbers=[x['horse_number'] for x in parsed if x['runner_status']!='nonstarter'],
                     complete=True,method='verified_PDF_times_and_complete_field',original_status=r['status'])
        db.execute('insert or replace into pdf_performance_evidence values(?,?)',(rid,json.dumps(payload,separators=(',',':'))))
        counters['new_performance_evidence_races']+=1
    linkage=propagate(db)
    if raw_history_digest(db,year)!=before:raise ValueError('earlier raw history was changed')
    if db.execute('pragma integrity_check').fetchone()[0]!='ok':
        raise ValueError('updated database integrity failed')
    if db.execute('pragma foreign_key_check').fetchall():raise ValueError('updated database foreign key violation')
    report=dict(year=year,counters=dict(counters),rejections=rejections,linkage=linkage,
                identity_audit=audit(db),unlinked_causes=unlinked_causes(db),earlier_raw_history_unchanged=True,
                earlier_raw_history_sha256=before,source_document_statuses=dict(db.execute('select status,count(*) from annual_report_documents where year=? group by status',(year,))),
                race_counts_by_year=dict(db.execute('select substr(race_id,1,4),count(*) from annual_report_races group by 1')),
                runner_counts_by_year=dict(db.execute('select substr(race_id,1,4),count(*) from annual_report_runners group by 1')),
                last_race_date=db.execute('select max(race_date) from annual_report_races').fetchone()[0])
    db.commit();target=sqlite3.connect(destination);db.backup(target);target.close();db.close()
    report.update(output_db_sha256=digest(destination),output_db_bytes=destination.stat().st_size)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',required=True)
    ap.add_argument('--db',required=True);ap.add_argument('--year',type=int,default=2026);ap.add_argument('--report',required=True)
    a=ap.parse_args();report=update(a.base,a.db,a.year)
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report['counters']),flush=True)
