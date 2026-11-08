"""Query the official 48-horse future form bank using a future race card asof.

Inputs are exact official JRA horse IDs and names, NOT fuzzy matches.
Prove capture occurred before the intended forecast snapshot. Keep partial
coverage and full V51's 34-feature preoff requirements explicitly separate.
"""
from __future__ import annotations
import argparse,datetime as dt,json,sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"operations/data_updates/jra_v51_future_horse_form_bank_20261108.sqlite"

def aware(s):
    t=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("asof timestamp must include timezone")
    return t

def select(race,asof,horses,db=DEFAULT):
    asof_t=aware(asof)
    if not isinstance(horses,list) or len(horses)<3:
        raise ValueError("complete race horse list required")
    if len({h["number"] for h in horses})!=len(horses):
        raise ValueError("horse numbers must be unique")
    if len({h.get("horse_id") for h in horses if h.get("horse_id")})!=len(
        [h for h in horses if h.get("horse_id")]):
        raise ValueError("duplicate official horse IDs")
    data=[]
    conn=sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro",uri=True)
    try:
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("feature bank is corrupt")
        for h in horses:
            horse_id=h.get("horse_id")
            if not horse_id:
                data.append({"number":h["number"],"name":h["name"],
                             "status":"OFFICIAL_HORSE_ID_MISSING"})
                continue
            if not str(horse_id).startswith("jra:"):
                raise ValueError("untrusted horse ID namespace")
            row=conn.execute("""SELECT horse_name,linked_nov08_race,
                profile_url,profile_sha256,verified_available_at,
                prior_runs,recent3_runs,recent3_wins,recent3_top3,
                recent3_mean_finish,recent3_mean_relative_finish,
                recent3_turf_runs,recent3_dirt_runs,
                recent3_mean_fair_speed_ms
                FROM future_horse_form WHERE horse_id=?""",(horse_id,)).fetchone()
            if row is None:
                data.append({"number":h["number"],"name":h["name"],
                             "horse_id":horse_id,"status":"NO_SOURCE_OBSERVATION"})
                continue
            if row[0]!=h["name"]:
                raise ValueError(f"official name mismatch for {horse_id}")
            if aware(row[4])>asof_t:
                data.append({"number":h["number"],"name":h["name"],
                             "horse_id":horse_id,
                             "source_observed_at":row[4],
                             "status":"OBSERVED_AFTER_FORECAST_CUTOFF"})
                continue
            data.append({"number":h["number"],"name":h["name"],
                         "horse_id":horse_id,"status":"OBSERVED_BEFORE_ASOF",
                         "source_observed_at":row[4],
                         "source_profile_url":row[2],"source_sha256":row[3],
                         "original_publication_timestamp_proven":False,
                         "proven_available_no_later_than":row[4],
                         "features":{
                            "prior_runs":row[5],"recent3_runs":row[6],
                            "recent3_wins":row[7],"recent3_top3":row[8],
                            "recent3_mean_finish":row[9],
                            "recent3_relative_finish":row[10],
                            "recent3_turf_runs":row[11],
                            "recent3_dirt_runs":row[12],
                            "recent3_speed_m_per_s_unadjusted":row[13]}})
    finally:conn.close()
    complete=all(x["status"]=="OBSERVED_BEFORE_ASOF" for x in data)
    return {"schema":"jra-source-backed-form-query-v1","race":race,
       "forecast_asof":asof,"horse_count":len(horses),
       "source_backed_horses":sum(x["status"]=="OBSERVED_BEFORE_ASOF" for x in data),
       "complete_form_coverage":complete,
       "status":"FORM_OBSERVED_ALL_HORSES" if complete else "PARTIAL_FORM_COVERAGE",
       "full_v51_34_feature_evidence_ready":False,
       "retrospective_use_of_nov08_results":False,
       "production_v50_modified":False,
       "horses":data}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--race-card",type=Path,required=True,
       help="JSON {race,asof,horses:[{number,name,horse_id}]}, user verified")
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--bank",type=Path,default=DEFAULT)
    args=ap.parse_args()
    card=json.loads(args.race_card.read_text())
    result=select(card["race"],card["asof"],card["horses"],args.bank)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
            "with_evidence":result["source_backed_horses"],
            "total":result["horse_count"],
            "can_compare_v51_to_v50":result["full_v51_34_feature_evidence_ready"]},
          ensure_ascii=False))
if __name__=="__main__":main()
