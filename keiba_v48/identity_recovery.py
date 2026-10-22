"""Offline recovery from hash-verified official pages; preserve original PDF text."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
from official_linkage import (attest, normalized, jockey_name, parse_html, parse_result,
                              printed_age, propagate, race_key)
from observed_identity import identity_observations
from completion_validation import sha
from validation import canonical


def causes(db):
    keys=collections.defaultdict(set)
    for name,birth,hid in db.execute('SELECT horse_name,birth_year,horse_id FROM official_identity_evidence'):
        keys[normalized(name),birth].add(hid)
    counts=collections.Counter(); distinct=collections.defaultdict(set)
    for name,payload,date in db.execute('''SELECT h.horse_name,h.payload_json,r.race_date FROM annual_report_runners h
        JOIN annual_report_races r USING(race_id) WHERE h.horse_id IS NULL'''):
        age=printed_age(json.loads(payload).get('sex_age',''))
        birth=int(date[:4])-age if date and age else None
        ids=keys.get((normalized(name),birth),set())
        reason=('missing_birth_year' if birth is None else 'unresolved_pdf_glyph' if '(cid:' in name
                else 'conflicting_official_ids' if len(ids)>1 else 'attested_key_not_applied' if ids
                else 'no_official_name_birth_evidence')
        counts[reason]+=1;distinct[reason].add((normalized(name),birth))
    return dict(rows=dict(counts),distinct_name_birth_keys={k:len(v) for k,v in distinct.items()})


def recover(base, destination, cache, report):
    if Path(destination).exists():raise ValueError('new recovery destination required')
    before_hash=sha(base)
    source=sqlite3.connect('file:'+str(Path(base).resolve())+'?mode=ro',uri=True)
    db=sqlite3.connect(destination);source.backup(db);source.close()
    before=dict(db.execute('SELECT race_id||":"||horse_number,horse_id FROM annual_report_runners'))
    before_causes=causes(db); corrections=[]
    db.execute('''CREATE TABLE IF NOT EXISTS identity_text_repairs(
        race_id TEXT,horse_number INTEGER,original_payload_json TEXT NOT NULL,
        source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,
        repair_basis TEXT NOT NULL,PRIMARY KEY(race_id,horse_number))''')
    cached_rows=0
    missing={r[0] for r in db.execute('SELECT DISTINCT race_id FROM annual_report_runners WHERE horse_id IS NULL')}
    for path in sorted(Path(cache).glob('*.json')):
        meta=json.loads(path.read_text());key=race_key(meta['url']);raw=path.with_suffix('.html')
        if not key or key[0] not in missing or not raw.exists():continue
        body=raw.read_bytes()
        if hashlib.sha256(body).hexdigest()!=meta['sha256']:raise ValueError('cache hash mismatch')
        for row in parse_result(parse_html(body,'lxml'),meta['url']):
            target=db.execute('''SELECT h.horse_name,h.jockey_name,h.payload_json,r.race_date,json_extract(h.payload_json,'$.finish_position')
                FROM annual_report_runners h JOIN annual_report_races r USING(race_id)
                WHERE h.race_id=? AND h.horse_number=? AND h.horse_id IS NULL''',
                (row['race_id'],row['horse_number'])).fetchone()
            if not target:continue
            cached_rows+=1
            payload=json.loads(target[2]);age=printed_age(payload.get('sex_age',''))
            if (not age or row['source_finish_position'] is None or target[3]!=row['race_date'] or int(target[3][:4])-age!=row['birth_year']
                    or target[4]!=row['source_finish_position']
                    or jockey_name(target[1])!=row['jockey_name']):continue
            text=normalized(target[0]);same=text==row['horse_name']
            doubled=(len(text)%2==0 and all(text[i]==text[i+1] for i in range(0,len(text),2)))
            collapsed=text[::2] if doubled else ''
            # A deterministic doubled-font corruption, corroborated by exact race,
            # runner, printed date, birth year, finish and rider. No fuzzy name join.
            damaged=doubled and collapsed.startswith(row['horse_name']) and len(collapsed)-len(row['horse_name'])<=2
            if not same and not damaged:continue
            if damaged:
                db.execute('INSERT INTO identity_text_repairs VALUES(?,?,?,?,?,?,?)',
                    (row['race_id'],row['horse_number'],target[2],meta['url'],meta['sha256'],meta['observed_at'],
                     'doubled_pdf_glyphs_and_exact_official_race_number_date_birth_finish_rider'))
                payload['horse_name']=row['horse_name']
                db.execute('UPDATE annual_report_runners SET horse_name=?,payload_json=? WHERE race_id=? AND horse_number=?',
                    (row['horse_name'],json.dumps(payload,ensure_ascii=False),row['race_id'],row['horse_number']))
                corrections.append(dict(race_id=row['race_id'],horse_number=row['horse_number'],
                    original_name=target[0],official_display_name=row['horse_name'],source_sha256=meta['sha256']))
            attest(db,[row],meta)
    propagated=propagate(db)
    db.commit()
    recovered=[];lost=[]
    for rid,num,hid in db.execute('SELECT race_id,horse_number,horse_id FROM annual_report_runners'):
        old=before[rid+':'+str(num)]
        if old is None and hid:recovered.append(dict(race_id=rid,horse_number=num,horse_id=hid))
        elif old and hid!=old:lost.append(dict(race_id=rid,horse_number=num,old=old,new=hid))
    if lost:raise ValueError('recovery changed existing official identities')
    times,errors=identity_observations(db)
    result=dict(schema='keiba-offline-identity-recovery-v1',input_sha256=before_hash,
        output_sha256=sha(destination),before=before_causes,after=causes(db),newly_linked_rows=len(recovered),
        recovered=recovered,text_repairs=corrections,propagation=propagated,cached_unlinked_source_rows=cached_rows,
        observed_identity_rows=len(times),observed_identity_errors=errors,
        integrity_check=db.execute('PRAGMA integrity_check').fetchone()[0],
        foreign_key_errors=db.execute('PRAGMA foreign_key_check').fetchall(),
        existing_horse_ids_changed=lost,input_unchanged=sha(base)==before_hash,
        network_requests=0,model_retrained=False)
    db.close()
    if result['integrity_check']!='ok' or result['foreign_key_errors']:
        raise ValueError('recovery database integrity failed')
    Path(report).write_text(canonical(result))
    print(canonical({k:result[k] for k in ('newly_linked_rows','output_sha256','observed_identity_errors','after')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('base','destination','cache','report'):p.add_argument('--'+k,required=True)
    a=p.parse_args();recover(a.base,a.destination,a.cache,a.report)
