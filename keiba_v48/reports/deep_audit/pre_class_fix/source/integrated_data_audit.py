"""Read-only reproducible quality audit of the integrated official archive."""
import argparse
import collections
import datetime as dt
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3

from enriched_features import load_archive,history_index
from completion_validation import pack
from exceptional_results import ticket_hit
from features import ENRICHED_FEATURE_NAMES,finish
import numpy as np


def audit_database(path,lag=2,with_features=False,asof='2026-10-20'):
    path=Path(path).resolve()
    with path.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    result=dict(schema='keiba-integrated-quality-v1',as_of_date=asof,input_db_sha256=digest,
                input_db_bytes=path.stat().st_size,lag_days=lag,read_only=True)
    result['integrity']=dict(sqlite=db.execute('pragma integrity_check').fetchone()[0],foreign_key_violations=len(db.execute('pragma foreign_key_check').fetchall()))
    tables=('annual_report_races','annual_report_runners','annual_identity_links','official_identity_evidence','pdf_performance_evidence','pdf_payout_evidence','enriched_results')
    result['table_counts']={t:db.execute('select count(*) from '+t).fetchone()[0] for t in tables}
    result['runner_key_duplicate_groups']=db.execute('select count(*) from (select race_id,horse_number from annual_report_runners group by 1,2 having count(*)>1)').fetchone()[0]
    result['identity_link_disagreements']=db.execute('''select count(*) from annual_report_runners r join annual_identity_links l using(race_id,horse_number)
        where r.horse_id is not l.horse_id or r.jockey_id is not l.jockey_id''').fetchone()[0]
    result['identity_by_year']=[dict(year=y,rows=n,horse_missing=hm,jockey_missing=jm,horse_missing_fraction=hm/n,jockey_missing_fraction=jm/n)
        for y,n,hm,jm in db.execute("select substr(race_id,1,4),count(*),sum(horse_id is null),sum(jockey_id is null) from annual_report_runners group by 1")]
    result['race_date_range']=dict(zip(('min','max'),db.execute('select min(race_date),max(race_date) from annual_report_races').fetchone()))
    result['source_result_age_days']=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(result['race_date_range']['max'])).days
    result['raw_races_missing_dates_or_off']=db.execute('select count(*) from annual_report_races where race_date is null or off_timestamp is null').fetchone()[0]
    result['time_evidence']=dict(exact_publication_missing=db.execute('select count(*) from annual_time_evidence where result_published_at is null').fetchone()[0],
                                 rows=db.execute('select count(*) from annual_time_evidence').fetchone()[0],
                                 pdf_clock_conflicts=sum(json.loads(p).get('clock_consistent') is False for p, in db.execute('select payload_json from document_artifact_times')))
    db.close()
    history,fields,loaded=load_archive(path,lag,allow_unlinked_fields=True)
    groups=collections.defaultdict(list)
    for row in fields:groups[row['race_id']].append(row)
    result['usable']=dict(races=len(groups),runner_rows=len(fields),history_rows=len(history),excluded_races=loaded['exclusions']['incomplete_or_exceptional_races'],void_races=len(loaded['void_races']))
    result['full_field_headcount_mismatches']=sum(any(row['field_size']!=len(rows) for row in rows) for rows in groups.values())
    isolated=collections.Counter(row['horse_id'] for row in history if row.get('horse_identity_missing'))
    result['unlinked_isolation']=dict(rows=sum(isolated.values()),distinct_row_keys=len(isolated),cross_race_key_reuse=sum(n>1 for n in isolated.values()),
                                      usable_rows=sum(row['horse_identity_missing'] for row in fields),usable_fraction=sum(row['horse_identity_missing'] for row in fields)/len(fields))
    result['current_inputs_masked']=dict(going=sum(row.get('going') is None for row in fields),carried_weight=sum(row.get('carried_weight') is None for row in fields),denominator=len(fields),
                                        reason='historical pre-off observation unavailable; do not fill with post-result fields')
    result['same_day_result_eligible_rows']=sum(row['result_available_at'][:10]==row['race_date'] for row in history)
    categories=collections.defaultdict(collections.Counter)
    for row in fields:
        group=categories[row.get('race_category','unknown')];group['rows']+=1;group['horse_missing']+=row['horse_identity_missing']
    result['identity_by_category']={k:dict(v) for k,v in categories.items()}
    tied=[];invalid_old_hits=[];false_after=0
    for rid,rows in groups.items():
        ranks=collections.Counter(finish(row) for row in rows if finish(row))
        if max(ranks.values())<2:continue
        tied.append(rid)
        for kind,size in (('wide',2),('trio',3)):
            top=[i for i,row in enumerate(rows) if finish(row) and finish(row)<=3]
            for selected in itertools.combinations(top,size):
                counts=collections.Counter(finish(rows[i]) for i in selected)
                invalid=any(n>4-rank for rank,n in counts.items())
                if invalid:
                    record=dict(race_id=rid,kind=kind,horse_numbers=[rows[i]['horse_number'] for i in selected],ranks=[finish(rows[i]) for i in selected])
                    invalid_old_hits.append(record);false_after+=ticket_hit(rows,list(selected),kind)
    result['dead_heat_audit']=dict(races=len(tied),old_rank_le3_false_hit_combinations=len(invalid_old_hits),corrected_false_hits=false_after,examples=invalid_old_hits)
    if with_features:
        races=pack(history_index(history),fields)
        matrix=np.asarray([f['values'] for race in races for f in race['features']])
        result['feature_profile']={name:dict(min=float(matrix[:,i].min()),max=float(matrix[:,i].max()),std=float(matrix[:,i].std()),
                                           distinct_nonconstant=bool(matrix[:,i].max()-matrix[:,i].min()>1e-12)) for i,name in enumerate(ENRICHED_FEATURE_NAMES)}
        result['unlinked_runners_with_cross_race_history']=sum(f['history_starts']>0 for race in races for row,f in zip(race['rows'],race['features']) if row['horse_identity_missing'])
    result['database_unchanged']=hashlib.sha256(path.read_bytes()).hexdigest()==digest
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--output',required=True)
    p.add_argument('--lag-days',type=int,choices=[2,7],default=2);p.add_argument('--features',action='store_true');a=p.parse_args()
    report=audit_database(a.db,a.lag_days,a.features);dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('feature_profile',)},ensure_ascii=False))
