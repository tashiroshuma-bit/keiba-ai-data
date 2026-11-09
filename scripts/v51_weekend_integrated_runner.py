"""One-command pre-off v50 + v51 research manifest, with optional body-weight freeze.

Input is the *actual* source-A full field and canonical v11 DB; this program
neither downloads data nor asserts synthetic fixtures are actual JRA races.
Run at 08:00 without weights, and rerun from newly observed A inputs near off.
All output is append-only. Shadow diagnostics never alter v50.
"""
import argparse
import hashlib
import json
import datetime as dt
from pathlib import Path
from scripts.capture_v50_bodyweight import (raw, moment, indexed, index_races,
                                             immutable_save, capture)
from scripts.standard_v50_forecast import standard_forecast
from scripts.v51_research_diagnostics import calibration_diagnostic
from scripts.v51_preoff_feature_builder import build
from scripts.v51_weekend_preflight import sha

def verified_sources(weights, archive):
    folder=Path(archive)
    if not folder.is_dir(): raise ValueError("original weight source archive missing")
    for race in weights["races"]:
        h=race["source_sha256"]
        if not isinstance(h,str) or len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
            raise ValueError("source SHA256 must be 64 lowercase hexadecimal")
        path=folder/(h+".bin")
        if not path.is_file() or path.is_symlink() or sha(path)!=h:
            raise ValueError("original weight source missing or tampered for "+race["race"])

def run(source_a,database,output_dir,*,weights=None,weight_archive=None,
        research_input=None,rank_snapshots=None,now=None):
    src,src_sha=raw(source_a)
    if src.get("source_model")!="A":raise ValueError("only actual v50 source A")
    asof=moment(src["asof"])
    real_now=now if now is not None else dt.datetime.now(dt.timezone.utc)
    if real_now.tzinfo is None:raise ValueError("runtime clock must have timezone")
    real_now=real_now.astimezone(dt.timezone.utc)
    if not asof<=real_now:raise ValueError("source A snapshot timestamp is in the future")
    if (real_now-asof).total_seconds()>3600:
        raise ValueError("source A snapshot too stale for prospective runner")
    races=index_races(src["races"],"race")
    for rid,r in races.items():
        if moment(r["original_off_at"])<=real_now:
            raise ValueError("race already started, cannot freeze prospective forecast: "+rid)
        indexed(r["horses"])
    root=Path(output_dir)
    root.mkdir(parents=True,exist_ok=True)
    identifier=asof.strftime("%Y%m%dT%H%M%SZ")+"_"+src_sha[:12]
    v50path=root/("v50_"+identifier+".json")
    v50=standard_forecast(source_a,database,v50path)
    v50_file_hash=sha(v50path)
    pred=index_races(v50["races"],"race")
    if set(pred)!=set(races):raise ValueError("standard v50 changed race roster")
    diagnostics={}
    for race,p in sorted(pred.items()):
        v=indexed(p["v50"]["horses"])
        if set(v)!=set(indexed(races[race]["horses"])):raise ValueError("v50 field mismatch")
        numbers=sorted(v,key=int)
        probabilities=[float(v[n]["p1"]) for n in numbers]
        diagnostics[race]={"v50_podium_pl_approximation":calibration_diagnostic(probabilities,[int(n) for n in numbers]),
            "research_status":"RESEARCH_ONLY_NO_PROMOTION"}
    optional={}
    if research_input is not None:
        inputs,input_sha=raw(research_input)
        entries=index_races(inputs["races"],"race")
        if set(entries)!=set(races):raise ValueError("research feature race mismatch")
        out=[]
        for rid in sorted(entries):
            row=entries[rid]
            if moment(row["asof"])!=asof or moment(row["off"])!=moment(races[rid]["original_off_at"]):
                raise ValueError("research asof or off mismatch")
            if set(indexed(row["runners"]))!=set(indexed(races[rid]["horses"])):
                raise ValueError("research official field mismatch")
            features=build(row["runners"],asof=row["asof"],off=row["off"],
                track=row["track"],surface=row["surface"],
                distance_m=row["distance_m"],class_index=row["class_index"],
                prior_day_results=row.get("prior_day_results",[]))
            out.append({"race":rid,**features})
        optional["features"]={"sha256":input_sha,"races":out,
            "status":"UNFITTED_RESEARCH_INPUTS_ONLY"}
    else:
        optional["features"]={"status":"NOT_SUPPLIED_NO_RESEARCH_FEATURES"}
    if rank_snapshots is not None:
        ranks,rank_sha=raw(rank_snapshots)
        items=index_races(ranks["races"],"race")
        if set(items)!=set(races):raise ValueError("rank shadow field mismatch")
        for rid,p in items.items():
            if p.get("deployment_status")!="experimental_rank_shadow" or p.get("strict_production_validated") is not False:
                raise ValueError("only frozen rank research output accepted")
            if moment(p["created_at"])>asof or moment(p["off_timestamp"])!=moment(races[rid]["original_off_at"]):
                raise ValueError("rank model only available after v50 snapshot")
            if len(p["runners"])<3 or len({str(q["horse_number"]) for q in p["runners"]})!=len(p["runners"]):
                raise ValueError("invalid or duplicate rank runner field")
            if {str(q["horse_number"]) for q in p["runners"]}!=set(indexed(races[rid]["horses"])):
                raise ValueError("rank shadow horse field mismatch")
        optional["learned_rank"]={"sha256":rank_sha,"status":"SAVED_RESEARCH_OUTPUT_SAME_ASOF",
            "races":len(items)}
    else:optional["learned_rank"]={"status":"NOT_SUPPLIED_NO_LEARNED_2ND_3RD"}
    if weights is not None:
        if weight_archive is None:raise ValueError("--weight-source-archive required")
        w,wsha=raw(weights)
        verified_sources(w,weight_archive)
        if set(index_races(w["races"],"race"))!=set(races):
            raise ValueError("weights must cover exact source A races")
        if moment(w["asof"])!=asof:raise ValueError("weight asof differs")
        for rid,weight_race in index_races(w["races"],"race").items():
            if moment(weight_race["original_off_at"])!=moment(races[rid]["original_off_at"]):
                raise ValueError("original off mismatch")
            if set(indexed(weight_race["horses"]))!=set(indexed(races[rid]["horses"])):
                raise ValueError("weight field mismatch")
        paired=capture(v50,w,v50_hash=v50_file_hash,weight_hash=wsha)
        pairfile=root/("v50_weight_pair_"+identifier+".json")
        paired_sha=immutable_save(pairfile,paired)
        optional["bodyweight"]={"status":"FROZEN_PREOFF_SHADOW_ONLY",
             "sha256":paired_sha,"path":str(pairfile),"source_manifest_sha256":wsha}
    else:
        optional["bodyweight"]={"status":"NOT_YET_PUBLISHED_OR_NOT_SUPPLIED",
            "note":"A morning v50 forecast does not require future announced weights"}
    manifest={"schema":"jra-v51-weekend-research-preoff-manifest-v1",
              "status":"V50_STANDARD_V51_SHADOW_ONLY",
              "source_a_sha256":src_sha,"v50_file_sha256":v50_file_hash,
              "canonical_db_sha256":v50["canonical_database_sha256"],
              "v50_path":str(v50path),"forecast_asof":src["asof"],
              "races":len(races),"race_diagnostics":diagnostics,"optional":optional,
              "source_observation_authentication":"MANIFEST_ONLY_INDEPENDENT_SOURCE_EVIDENCE_REQUIRED",
              "production_model":"v50","promoted_v51":False}
    manifestfile=root/("research_preoff_"+identifier+".json")
    h=immutable_save(manifestfile,manifest)
    return {"manifest":str(manifestfile),"sha256":h,"v50_path":str(v50path),
            "races":len(races),"v50_sha256":v50_file_hash,
            "weight_status":optional["bodyweight"]["status"],
            "feature_status":optional["features"]["status"],
            "rank_status":optional["learned_rank"]["status"]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--forecast-source",required=True)
    ap.add_argument("--database",required=True)
    ap.add_argument("--output-dir",required=True)
    ap.add_argument("--weights")
    ap.add_argument("--weight-source-archive")
    ap.add_argument("--research-input")
    ap.add_argument("--rank-snapshots")
    args=ap.parse_args()
    print(json.dumps(run(args.forecast_source,args.database,args.output_dir,
        weights=args.weights,weight_archive=args.weight_source_archive,
        research_input=args.research_input,rank_snapshots=args.rank_snapshots),
        ensure_ascii=False))
if __name__=="__main__":main()
