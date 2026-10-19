"""Offline, evidence-backed PDF performance and exceptional-field recovery."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
from pdf_performance import parse_times,fourth_corner
from pdf_payouts import decode_payouts


def attach_corner(rows,text,official=None):
    positions=fourth_corner(text,[r['horse_number'] for r in rows if r['runner_status']!='nonstarter'])
    if not positions:return False,False
    if official is not None:
        for r in official:
            n=r['horse_number'];known=r.get('corner4_position')
            if n in positions and known is not None:
                low,high=positions[n]['corner4_range']
                if not low<=known<=high:return False,True
    for r in rows:
        if r['horse_number'] in positions:r.update(positions[r['horse_number']])
    return True,False


def repair_performance(base,destination):
    if Path(destination).exists():raise ValueError('new destination required')
    src=sqlite3.connect('file:'+str(Path(base).resolve())+'?mode=ro',uri=True)
    db=sqlite3.connect(':memory:');src.backup(db);src.close();db.row_factory=sqlite3.Row
    verified=db.execute('select count(*) from annual_report_documents d join document_artifact_times t on d.url=t.document_url and d.sha256=t.source_sha256').fetchone()[0]
    if verified!=db.execute('select count(*) from annual_report_documents').fetchone()[0]:raise ValueError('verified source PDF inventory required')
    records=[];counts=collections.Counter();errors=collections.Counter();conflicts=[]
    rich={r['race_id']:json.loads(r['payload_json']) for r in db.execute('select * from enriched_results')}
    for race in db.execute('select * from annual_report_races').fetchall():
        rid=race['race_id'];meta=json.loads(race['metadata_json'])
        raw=[json.loads(r['payload_json']) for r in db.execute('select * from annual_report_runners where race_id=? order by finish_order',(rid,))]
        if not race['expected_runners']:continue
        try:rows=parse_times(raw,race['expected_runners'],json.loads(race['issues_json']),meta['raw_text'],True)
        except ValueError as e:errors[str(e)]+=1;continue
        if rid in rich:
            official={r['horse_number']:r for r in rich[rid]['runners'] if r['horse_number'] in rich[rid]['active_horse_numbers']}
            if set(official)!={r['horse_number'] for r in rows if r['runner_status']!='nonstarter'}:conflicts.append((rid,'field'));continue
            bad=False
            for r in rows:
                if r['runner_status']=='nonstarter':continue
                known=official[r['horse_number']]
                if r['finish_position']!=known.get('finish_position') or (r['finish_time_seconds'] is not None and abs(r['finish_time_seconds']-known['finish_time_seconds'])>1e-6):bad=True;break
            if bad:conflicts.append((rid,'rank_or_time'));continue
            counts['HTML_agreed_races']+=1
        if race['status']!='validated_result':
            try:payouts,proof=decode_payouts(meta['raw_text'],{str(r['horse_number']):r['finish_position'] for r in rows if r['finish_position']},meta.get('win_payout_100'))
            except ValueError as e:errors['exception_payout_'+str(e)]+=1;continue
            doc=db.execute('select sha256,fetched_at from annual_report_documents where url=?',(race['document_url'],)).fetchone()
            proof['method']='explicit_PDF_field_times_and_exception_handling; '+proof['method'];proof['raw_text_sha256']=hashlib.sha256(meta['raw_text'].encode()).hexdigest()
            db.execute('insert or replace into pdf_payout_evidence values(?,?,?,?,?,?)',(rid,json.dumps(payouts,sort_keys=True),json.dumps(proof),race['document_url'],*doc))
            counts['reviewed_exception_fields_repaired']+=1
        attached,conflict=attach_corner(rows,meta['raw_text'],rich[rid]['runners'] if rid in rich else None)
        if attached:
            counts['corner_races']+=1;counts['corner_rows']+=sum(r.get('corner4_position') is not None for r in rows)
            if rid in rich:counts['HTML_corner_agreed_races']+=1
        if conflict:counts['quarantined_corner_conflicts']+=1
        keys=('horse_number','finish_position','runner_status','finish_time_seconds','margin_seconds','relative_speed_z','field_size','final_win_odds','corner4_position','corner4_range','corner4_method')
        overlay=[{k:r.get(k) for k in keys} for r in rows]
        payload=dict(runners=overlay,active_horse_numbers=[r['horse_number'] for r in rows if r['runner_status']!='nonstarter'],complete=True,method='verified_PDF_times_and_complete_field',original_status=race['status'])
        records.append((rid,json.dumps(payload,separators=(',',':'))));counts['performance_races']+=1;counts['performance_rows']+=len(rows)
    # Rebuild the complete evidence overlay from the immutable annual-report
    # inputs.  This also makes a later parser correction reproducible from an
    # already repaired checkpoint instead of requiring the original base DB.
    db.execute('DROP TABLE IF EXISTS pdf_performance_evidence')
    db.execute('CREATE TABLE pdf_performance_evidence(race_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL)');db.executemany('insert into pdf_performance_evidence values(?,?)',records)
    db.commit();db.execute('VACUUM');dest=sqlite3.connect(destination);db.backup(dest);dest.close();db.close()
    report=dict(counts=counts,rejections=errors,quarantined_source_conflicts=conflicts)
    check=sqlite3.connect('file:'+str(Path(destination).resolve())+'?mode=ro',uri=True)
    report['integrity_check']=check.execute('pragma integrity_check').fetchone()[0];report['foreign_key_violations']=len(check.execute('pragma foreign_key_check').fetchall());check.close()
    if report['integrity_check']!='ok' or report['foreign_key_violations']:raise ValueError('repaired database verification failed')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',required=True);p.add_argument('--db',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    result=repair_performance(a.base,a.db);Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)
