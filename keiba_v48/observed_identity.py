"""Resolve every identity dependency, including profile and three-race aliases."""
import collections
import json
from features import timestamp
from official_linkage import jockey_name, normalized, printed_age


def identity_observations(db):
    result = {}; errors = collections.Counter()
    direct = {(r[0],r[1]):r[2:] for r in db.execute('''SELECT race_id,horse_number,horse_id,jockey_id,
        observed_at,source_url,source_sha256 FROM official_identity_evidence''')}
    profiles = {(r[0],r[1]):r[2:] for r in db.execute('''SELECT race_id,horse_number,profile_horse_id,jockey_id,
        observed_at,source_url,source_sha256 FROM official_profile_start_evidence''')}
    anchors={}
    for proof in direct.values():
        at=timestamp(proof[2]);anchors[proof[0]]=min(anchors.get(proof[0],at),at)
    alias_rows=collections.defaultdict(dict)
    for rid,raw,hname,payload,date,source_name,birth,jid,source_payload,observed,pdf_observed in db.execute('''
        SELECT e.race_id,h.jockey_name,h.horse_name,h.payload_json,r.race_date,e.horse_name,e.birth_year,
        e.jockey_id,e.payload_json,e.observed_at,d.fetched_at FROM official_identity_evidence e
        JOIN annual_report_runners h USING(race_id,horse_number) JOIN annual_report_races r USING(race_id)
        JOIN annual_report_documents d ON d.url=r.document_url'''):
        age=printed_age(json.loads(payload).get('sex_age',''))
        if not age or not date or normalized(hname)!=source_name or int(date[:4])-age!=birth:continue
        canonical=jockey_name(json.loads(source_payload).get('jockey_name'))
        alias=jockey_name(raw)
        if jid and alias and canonical and alias!=canonical:
            if not pdf_observed:continue
            key=(alias,jid);at=max(timestamp(observed),timestamp(pdf_observed))
            alias_rows[key][rid]=min(alias_rows[key].get(rid,at),at)
    alias_times={key:sorted(v.values())[2] for key,v in alias_rows.items() if len(v)>=3}
    for rid,num,hid,jid,hm,jm,hr,hn,jr,jn,raw in db.execute('''SELECT l.*,h.jockey_name
        FROM annual_identity_links l JOIN annual_report_runners h USING(race_id,horse_number)'''):
        if not hid:continue
        times=[];valid=True
        for identity,method,ref,col in ((hid,hm,(hr,hn),0),(jid,jm,(jr,jn),1)):
            if not identity:continue
            table=profiles if method=='exact_profile_start_and_attested_horse' else direct
            proof=table.get((rid,num) if table is profiles else ref)
            if not proof or proof[col]!=identity or not proof[3].startswith('https://www.jra.go.jp/') or len(proof[4])!=64:
                errors['missing_or_mismatched_identity_proof']+=1;valid=False;break
            times.append(timestamp(proof[2]))
            if table is profiles:
                if hid not in anchors:
                    errors['missing_profile_horse_anchor']+=1;valid=False;break
                times.append(anchors[hid])
            if method=='multi_race_attested_pdf_alias':
                alias_at=alias_times.get((jockey_name(raw),identity))
                if alias_at is None:
                    errors['alias_support_not_proven']+=1;valid=False;break
                times.append(alias_at)
        if valid:result[rid,str(num)]=max(times)
    return result,dict(errors)
