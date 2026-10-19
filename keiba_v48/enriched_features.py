"""Verified result enrichment with explicit historical publication assumptions."""
import collections
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3

from features import HistoryIndex, build_features, timestamp, finish, shrink
from historical_replay import assumed_availability
from archive_completion import class_info


def load_archive(db_path,lag_days=2):
    db=sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    groups=collections.defaultdict(list);meta={};excluded=collections.Counter(); repaired=[]; unsafe_fields=set()
    tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    void={r[0] for r in db.execute('select race_id from official_void_races')} if 'official_void_races' in tables else set()
    for r in db.execute('''SELECT r.*,h.horse_number,h.horse_id,h.jockey_id,h.payload_json,d.fetched_at
        FROM annual_report_races r JOIN annual_report_runners h USING(race_id)
        JOIN annual_report_documents d ON d.url=r.document_url ORDER BY r.race_id,h.horse_number'''):
        if r['race_id'] in void:continue
        p=json.loads(r['payload_json']); m=json.loads(r['metadata_json']);valid=r['status']=='validated_result'
        level,category,grade=class_info(m.get('raw_text','').split('発走')[0])
        row=dict(p,race_id=r['race_id'],race_date=r['race_date'],horse_id=r['horse_id'],jockey_id=r['jockey_id'],
                 horse_number=str(r['horse_number']),off_timestamp=r['off_timestamp'],track=r['track'],surface=r['surface'],
                 distance_m=r['distance_m'],going=r['going'],field_size=r['expected_runners'],source_url=r['document_url'],
                 result_observed_at=r['fetched_at'],class_level=level,race_category=category,grade=grade,
                 finish_position=p.get('finish_position') if valid else None,
                 final_win_odds=p.get('final_win_odds') if valid else None,
                 win_payout_100=m.get('win_payout_100') if valid else None)
        groups[r['race_id']].append(row);meta[r['race_id']]=dict(r)
    source_only=[]
    if 'enriched_results' in tables:
        for rid,status,payload in db.execute('select race_id,status,payload_json from enriched_results'):
            if rid in void:continue
            rich=json.loads(payload)
            if status!='complete':unsafe_fields.add(rid)
            prior={int(r['horse_number']):r for r in groups[rid]}
            if rid not in meta:source_only.append(rid)
            elif status=='complete' and meta[rid]['status']!='validated_result':repaired.append(rid)
            rows=[]
            active=set(rich['active_horse_numbers'])
            for r in rich['runners']:
                if r['horse_number'] not in active:continue
                old=prior.get(r['horse_number'],{})
                # Source rank/identity is authoritative, quarantined PDF odds stay absent.
                merged={**old,**r,'horse_number':str(r['horse_number']),
                        'off_timestamp':old.get('off_timestamp') or r.get('off_timestamp'),
                        'source_url':rich['source_url'],'source_sha256':rich['source_sha256'],
                        'result_observed_at':max(old.get('result_observed_at') or rich['observed_at'],rich['observed_at']),
                        'identity_observed_at':rich['observed_at'],'payouts':rich['payouts']}
                merged['win_payout_100']=rich['payouts'].get('win:'+str(r['horse_number'])) if r.get('finish_position')==1 else old.get('win_payout_100')
                rows.append(merged)
            # A common race-level payout label is needed independently of the selection.
            win=next((r['win_payout_100'] for r in rows if r.get('finish_position')==1),None)
            for r in rows:r['win_payout_100']=win
            groups[rid]=rows
    history=[];fields=[];coverage=collections.Counter()
    for rid,rows in sorted(groups.items()):
        for r in rows:
            if r.get('horse_id') and r.get('off_timestamp') and r.get('distance_m') and r.get('surface') and (finish(r) or r.get('runner_status')=='nonfinisher'):
                r=dict(r,result_available_at=assumed_availability(r['race_date'],lag_days),availability_basis='assumed_calendar_day_lag_for_research_only')
                if r.get('class_level') is None:r.pop('class_level',None)
                history.append(r)
                for k in ('margin_seconds','corner4_position','last_3f_rank','relative_speed_z','class_level','gate'):
                    coverage[k]+=r.get(k) is not None
        ranks=[finish(r) for r in rows if finish(r)]
        valid=(rid not in unsafe_fields and len(rows)>=3 and len(ranks)>=3 and sorted(ranks)==list(range(1,len(ranks)+1)) and
               len({r.get('horse_id') for r in rows})==len(rows) and
               all(r.get('horse_id') and r.get('off_timestamp') and r.get('distance_m') and r.get('surface') and
                   (finish(r) or r.get('runner_status')=='nonfinisher') for r in rows))
        if not valid:excluded['incomplete_or_exceptional_races']+=1;continue
        for r in rows:
            fields.append({**r,'going':None,'carried_weight':None,'field_complete':'yes','expected_runners':len(rows),
                           'result_available_at':assumed_availability(r['race_date'],lag_days),'availability_basis':'assumed_calendar_day_lag_for_research_only'})
    db.close()
    return history,fields,dict(exclusions=dict(excluded),repaired_pdf_races=len(repaired),source_only_races=len(source_only),void_races=sorted(void),feature_coverage_rows=dict(coverage),history_rows=len(history),field_rows=len(fields))


def history_index(rows,assumed=True):
    idx=HistoryIndex(rows,allow_assumed_availability=assumed,allow_missing_jockey=True)
    idx.same_day=collections.defaultdict(list)
    races=collections.defaultdict(list)
    for r in idx.rows:
        races[r['race_id']].append(r)
        if finish(r)==1:idx.same_day[r['race_date'],r.get('track'),r['surface']].append(r)
    # Opponent ability must itself be calculated at that past race's cutoff.
    for field in races.values():
        abilities={}
        for r in field:
            off=timestamp(r['off_timestamp']);cutoff=off-dt.timedelta(minutes=5)
            past=idx.prior('horse',r['horse_id'],r['race_id'],off,cutoff)
            if past:abilities[r['horse_id']]=shrink(past,lambda x:True)[0]
        for r in field:
            vals=[v for hid,v in abilities.items() if hid!=r['horse_id']]
            r['opponent_quality']=sum(vals)/len(vals) if vals else None
    return idx


def build_enriched(index,rows,use_grade=True):
    features=build_features(index,rows)
    for f,r in zip(features,rows):
        off=timestamp(r['off_timestamp']);cutoff=timestamp(f['cutoff_timestamp'])
        past=index.prior('horse',r['horse_id'],r['race_id'],off,cutoff)
        recent=past[-3:]
        margins=[min(5,max(0,float(x['margin_seconds']))) for x in recent if x.get('margin_seconds') is not None]
        opponents=[x['opponent_quality'] for x in recent if x.get('opponent_quality') is not None]
        hj=[x for x in past if r.get('jockey_id') and x.get('jockey_id')==r['jockey_id']]
        gate=r.get('gate')
        if gate is not None and (isinstance(gate,bool) or int(gate)!=float(gate) or not 1<=int(gate)<=8):raise ValueError('invalid gate')
        day=[x for x in index.same_day.get((r['race_date'],r.get('track'),r['surface']),[]) if x['race_id']!=r['race_id'] and timestamp(x['off_timestamp'])<off and timestamp(x['result_available_at'])<=cutoff and x.get('corner4_position') is not None and x.get('field_size',0)>1]
        front=sum((x['corner4_position']-1)/(x['field_size']-1)<=.35 for x in day)
        f['values'] += [1-sum(margins)/len(margins)/5 if margins else .5,float(bool(margins)),
                        sum(opponents)/len(opponents) if opponents else .25,float(bool(opponents)),shrink(hj,lambda x:True)[0],
                        (int(gate)-1)/7 if gate is not None else .5,float(gate is not None),
                        (front+1)/(len(day)+2)-.5 if day else 0,float(bool(day)),
                        (1+sum(x.get('runner_status')=='nonfinisher' for x in past))/(len(past)+10)]
        category=r.get('race_category','unknown')
        if category not in ('graded','nongraded','unknown'):raise ValueError('invalid race category')
        f['groups']=[f['group']]+(['class:'+category] if use_grade else [])
        f.update(margin_samples=len(margins),opponent_samples=len(opponents),same_day_bias_samples=len(day))
    return features


def previous_contract_index(rows,assumed=True):
    stripped=[]
    for row in rows:
        if not finish(row):continue
        r=dict(row)
        for k in ('class_level','carried_weight','corner4_position','last_3f_rank','relative_speed_z'):r.pop(k,None)
        stripped.append(r)
    return HistoryIndex(stripped,allow_assumed_availability=assumed,allow_missing_jockey=True)


def load_observed_enriched(db_path,cutoff):
    history,_,_=load_archive(db_path)
    db=sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True)
    proofs={}
    for rid,num,ho,jo in db.execute('''SELECT l.race_id,l.horse_number,h.observed_at,j.observed_at FROM annual_identity_links l
        LEFT JOIN official_identity_evidence h ON h.race_id=l.horse_evidence_race_id AND h.horse_number=l.horse_evidence_horse_number
        LEFT JOIN official_identity_evidence j ON j.race_id=l.jockey_evidence_race_id AND j.horse_number=l.jockey_evidence_horse_number'''):
        proofs[rid,str(num)]=[x for x in (ho,jo) if x]
    db.close();rows=[]
    for r in history:
        times=[r['result_observed_at']]+([r['identity_observed_at']] if r.get('identity_observed_at') else proofs.get((r['race_id'],str(r['horse_number'])),[]))
        at=max(map(timestamp,times))
        if at<=cutoff:
            rows.append({**r,'result_available_at':at.isoformat(),'availability_basis':'observed_source_and_identity_proof'})
    return rows
