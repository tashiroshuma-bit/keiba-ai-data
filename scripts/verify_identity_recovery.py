"""Check the complete recovery diff and readback; outcomes cannot be rewritten."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'keiba_v48'))
from integrated_data_audit import audit_database
from observed_identity import identity_observations


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(base,recovered,checkpoint,require_saved=False):
    before=digest(base);expected=json.loads(Path(checkpoint).read_text())
    assert before==expected['input_sha256'] and digest(recovered)==expected['output_sha256']
    old=sqlite3.connect(Path(base).resolve().as_uri()+'?mode=ro',uri=True)
    new=sqlite3.connect(Path(recovered).resolve().as_uri()+'?mode=ro',uri=True)
    tables={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    mutable={'annual_report_runners','annual_identity_links','official_identity_evidence','official_jockey_aliases','annual_time_evidence'}
    unchanged={}
    for table in sorted(tables-mutable):
        a=old.execute('SELECT * FROM '+table+' ORDER BY rowid');b=new.execute('SELECT * FROM '+table+' ORDER BY rowid')
        count=0
        while True:
            aa=a.fetchmany(1000);bb=b.fetchmany(1000)
            assert aa==bb,table
            count+=len(aa)
            if not aa:break
        unchanged[table]=count
    names=0;linked=0;runner_count=0
    a=old.execute('SELECT * FROM annual_report_runners ORDER BY race_id,horse_number')
    b=new.execute('SELECT * FROM annual_report_runners ORDER BY race_id,horse_number')
    allowed={'horse_id','jockey_id','identity_status','horse_name'}
    for aa,bb in zip(a,b,strict=True):
        runner_count+=1
        assert aa[:3]==bb[:3] and aa[4]==bb[4] and aa[6]==bb[6]
        assert aa[5] is None or aa[5]==bb[5]
        po=json.loads(aa[7]);pn=json.loads(bb[7])
        assert {k:v for k,v in po.items() if k not in allowed}=={k:v for k,v in pn.items() if k not in allowed}
        if aa[3]!=bb[3]:
            names+=1
            proof=new.execute('SELECT original_payload_json FROM identity_text_repairs WHERE race_id=? AND horse_number=?',aa[:2]).fetchone()
            assert proof and json.loads(proof[0])==po
        linked+=aa[5] is None and bb[5] is not None
    assert linked==expected['newly_linked_rows']==10 and names==len(expected['text_repairs'])==2
    proofs,errors=identity_observations(new);assert not errors
    audit=audit_database(recovered,2,False,'2026-10-22')
    assert audit['integrity']=={'sqlite':'ok','foreign_key_violations':0}
    assert audit['identity_link_disagreements']==audit['runner_key_duplicate_groups']==audit['full_field_headcount_mismatches']==0
    assert audit['usable']['races']==12763 and audit['database_unchanged']
    identity=dict(sha256=digest(recovered),bytes=Path(recovered).stat().st_size)
    if require_saved:
        identity.update(library_file_id=os.getxattr(recovered,'user.library-file-id').decode(),
                        version=int(os.getxattr(recovered,'user.library-file-version').decode()))
    old.close();new.close()
    assert digest(base)==before
    report=dict(schema='keiba-identity-recovery-readback-v1',verified=True,
        verified_at=dt.datetime.now(dt.timezone.utc).isoformat(),database=identity,input_database_sha256=before,
        saved_readback=require_saved,outcomes_and_nonidentity_payload_unchanged=True,
        names_corrected_with_original_text_preserved=names,newly_linked_rows=linked,
        rows_checked=runner_count,immutable_tables_checked=unchanged,
        observed_identity_rows=len(proofs),observed_identity_errors=errors,
        source_database_unchanged=True,usable=audit['usable'],latest_race_date=audit['race_date_range']['max'])
    return report,audit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('base','recovered','checkpoint','output'):p.add_argument('--'+k,required=True)
    p.add_argument('--require-saved',action='store_true');a=p.parse_args()
    report,audit=verify(a.base,a.recovered,a.checkpoint,a.require_saved)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    for name,value in (('verification.json',report),('data_audit.json',audit)):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report))
