"""Build frozen 31-feature V51 snapshot from official live roster and canonical v12.

Requires original canonical SQLite, verified-result overlay and independently
verified historical publication manifest. Never imputes source timestamps.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

try:
    from scripts.jra_historical_horse_id_ablation import build_dataset, HistoricalStats, FEATURES, strength, clamp
    from scripts.standard_v51_forecast import digest, stamp
    from scripts.v51_preoff_provenance_guard import check_historical_observation
except ModuleNotFoundError:
    from jra_historical_horse_id_ablation import build_dataset, HistoricalStats, FEATURES, strength, clamp
    from standard_v51_forecast import digest, stamp
    from v51_preoff_provenance_guard import check_historical_observation

JST=dt.timezone(dt.timedelta(hours=9))

def compute_one(runners, horses, jockeys, race_date, track, surface, distance):
    empty=HistoricalStats()
    n=len(runners)
    rows=[]
    for r in runners:
        h=horses.get(r["horse_id"],empty)
        j=jockeys.get(r["jockey_id"],empty)
        days=180 if not h.last_date else clamp((dt.date.fromisoformat(race_date)-dt.date.fromisoformat(h.last_date)).days,0,365)
        feats=[n,distance/1000,float(surface=="turf"),max(0,r["age"]),r["female"],r["carried_weight"],r["gate"]/max(1,n),r["number"]/max(1,n),
               math.log1p(h.n),h.winrate(),h.top3rate(),h.last3_strength(),h.last_strength(),days,
               h.winrate(h.surface,surface),h.surface[surface][0] if surface in h.surface else 0,
               h.winrate(h.track,track),h.track[track][0] if track in h.track else 0,
               h.winrate(h.distance,distance),h.distance[distance][0] if distance in h.distance else 0,
               math.log1p(j.n),j.winrate(),j.top3rate(),j.winrate(j.track,track),
               j.winrate(j.surface,surface),j.winrate(j.distance,distance),j.last3_strength()]
        rows.append(feats)
    hmean=sum(x[8] for x in rows)/n
    wmean=sum(x[9] for x in rows)/n
    jmean=sum(x[21] for x in rows)/n
    new=sum(x[8]==0 for x in rows)/n
    for f in rows:
        f.extend([hmean,f[9]-wmean,f[21]-jmean,new])
        if len(f)!=len(FEATURES):
            raise ValueError("FROZEN_FEATURE_COUNT_MISMATCH")
    return rows

def build_snapshot(database, overlay, roster, publication_manifest, model):
    source=json.loads(Path(roster).read_text())
    if source.get("schema")!="jra-v51-live-racecard-v1":
        raise ValueError("VERIFIED_OFFICIAL_ROSTER_REQUIRED")
    if len(source.get("races", []))!=1:
        raise ValueError("ONE_RACE_PER_SNAPSHOT_REQUIRED")
    manifest=json.loads(Path(publication_manifest).read_text())
    if manifest.get("schema")!="jra-v51-historical-publication-evidence-v1":
        raise ValueError("INDEPENDENT_PUBLICATION_MANIFEST_REQUIRED")
    model_doc=json.loads(Path(model).read_text())
    expected=model_doc["canonical_db_sha256"]
    if digest(database)!=expected:
        raise ValueError("CANONICAL_DATABASE_SHA_MISMATCH")
    if model_doc["feature_names"]!=FEATURES:
        raise ValueError("FROZEN_31_FEATURE_NAMES_MISMATCH")
    asof=stamp(source["captured_at"])
    historical,_=build_dataset(database,overlay)
    bydate=collections.defaultdict(list)
    for rr in historical.values():
        bydate[rr[0]["date"]].extend(rr)
    horses=collections.defaultdict(HistoricalStats)
    jockeys=collections.defaultdict(HistoricalStats)
    outputs=[]
    for race in source["races"]:
        off=stamp(race["race_off_at"])
        day=off.astimezone(JST).date().isoformat()
        if asof>=off:
            raise ValueError("FORECAST_NOT_PREOFF")
        # Historical statistics are trained only on verified full-result cohort
        # and frozen before all races of the same calendar day.
        for date in sorted(bydate):
            if date>=day:break
            for r in bydate[date]:
                evidence=manifest.get("races",{}).get(r["race"])
                if evidence is None:
                    raise ValueError("MISSING_VERIFIED_HISTORICAL_PUBLICATION:"+r["race"])
                check_historical_observation(evidence,race_off_at=race["race_off_at"],forecast_asof=source["captured_at"])
                quality=strength(r["rank"],len(historical[r["race"]]))
                horses[r["horse_id"]].update(r,quality)
                if r["jockey_id"]:jockeys[r["jockey_id"]].update(r,quality)
        vals=compute_one(race["horses"],horses,jockeys,day,race["track"],race["surface"],race["distance_m"])
        output=[]
        for runner,features in zip(race["horses"],vals):
            h=horses.get(runner["horse_id"])
            last=h.last_date if h and h.n else None
            # Every historical contribution is covered by validated publication
            # manifest; pass exact records for auditing rather than inventing proof.
            contributions=[manifest["races"][r["race"]] for date in sorted(bydate) if date<day
                           for r in bydate[date] if r["horse_id"]==runner["horse_id"]]
            output.append({"number":runner["number"],"name":runner["name"],"horse_id":runner["horse_id"],
                           "official_identity_proof":{"horse_id":runner["horse_id"],"horse_number":runner["number"],
                              "source_url":source["source_url"],"source_sha256":source["source_sha256"],
                              "observed_at":source["captured_at"]},
                           "features_observed_at":source["captured_at"],
                           "features_generated_at":source["captured_at"],
                           "feature_values":features,"prior_starts":h.n if h else 0,
                           "latest_history_date":last,"historical_evidence":contributions})
        outputs.append({"race":race["race"],"race_off_at":race["race_off_at"],
                        "features_generated_at":source["captured_at"],"horses":output})

    return {"schema":"jra-v51-preoff-feature-snapshot-v1",
            "canonical_database_sha256":expected,"roster_source_sha256":source["source_sha256"],
            "roster_source_url":source["source_url"],"roster_captured_at":source["captured_at"],
            "forecast_asof":source["captured_at"],"races":outputs}

def main():
    p=argparse.ArgumentParser()
    for k in ("database","overlay","roster","publication-manifest","model","output"):
        p.add_argument("--"+k,required=True)
    a=p.parse_args()
    doc=build_snapshot(a.database,a.overlay,a.roster,a.publication_manifest,a.model)
    Path(a.output).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"FROZEN_31_FEATURE_SNAPSHOT","races":len(doc["races"])}))
if __name__=="__main__":main()
