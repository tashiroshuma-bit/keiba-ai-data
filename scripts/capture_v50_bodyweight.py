"""Immutable paired v50 / pre-off body-weight capture for later v51 validation.

Usage:
 python -m scripts.capture_v50_bodyweight --v50 saved_v50.json --weights weights.json --output-dir operations/predictions/2026-11-14/
Weight input contract: {"asof":"ISO8601", "races":[{"race":"2026-11-14 Tokyo 1R",
"original_off_at":"ISO8601", "source_url":"https://...", "source_sha256":"64 lowercase hex",
"observed_at":"ISO8601", "horses":[{"number":1,"body_weight_kg":478,
"weight_change_kg":-4, "weight_observed_at":"ISO8601"}, ...]}]}
No network guessing, historical backdating, overwrites or live bets.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

def moment(s):
    if not isinstance(s,str): raise ValueError("timestamp required")
    t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None: raise ValueError("timezone-aware timestamp required")
    return t.astimezone(dt.timezone.utc)

def digest(data):return hashlib.sha256(data).hexdigest()
def raw(path):
    data=Path(path).read_bytes()
    return json.loads(data),digest(data)

def number_key(x):
    if isinstance(x,bool):raise ValueError("invalid horse number")
    v=str(x)
    if not v.isdigit() or int(v)<=0: raise ValueError("invalid horse number")
    return str(int(v))

def indexed(rows):
    if not isinstance(rows,list) or len(rows)<3:raise ValueError("complete field with >=3 horses required")
    keys=[number_key(x["number"]) for x in rows]
    if len(set(keys))!=len(keys):raise ValueError("duplicate horse number")
    return dict(zip(keys,rows))

def bucket(delta):
    if delta is None:return "unknown"
    if isinstance(delta,bool) or not isinstance(delta,(int,float)) or not math.isfinite(delta):
        raise ValueError("numeric weight change required or null")
    if delta<=-20:return "<=-20"
    if delta<=-10:return "-19..-10"
    if delta<=-4:return "-9..-4"
    if delta<4:return "-3..+3"
    if delta<10:return "+4..+9"
    if delta<20:return "+10..+19"
    return ">=+20"

def capture(v50,weight,*,v50_hash,weight_hash,expected_policy_sha=None):
    if v50.get("version")!="v50" or v50.get("standard_forecast") is not True:
        raise ValueError("genuine standard v50 output required")
    if v50.get("live_bet_generation") is not False:raise ValueError("live bets must be disabled")
    if not v50.get("canonical_database_sha256") or not v50.get("policy_sha256"):
        raise ValueError("database and policy provenance required")
    if expected_policy_sha and v50["policy_sha256"]!=expected_policy_sha:
        raise ValueError("policy changed")
    if not v50.get("forecast_sha256") or not v50.get("rider_sha256"):
        raise ValueError("actual v50 source and rider hashes required")
    a=moment(v50["forecast_asof"])
    if moment(weight["asof"])!=a:raise ValueError("asof differs")
    vr=index_races(v50.get("races"),"race")
    wr=index_races(weight.get("races"),"race")
    if set(vr)!=set(wr):raise ValueError("all v50 races must have weight snapshot")
    out=[]
    for race in sorted(vr):
        pred=vr[race]; w=wr[race]
        off=moment(w["original_off_at"])
        source_observed=moment(w["observed_at"])
        if not (source_observed<=a<off):
            raise ValueError("weight source must be observed by forecast asof before off")
        if not w.get("source_url") or not isinstance(w.get("source_sha256"),str) or len(w["source_sha256"])!=64:
            raise ValueError("weight source URL and digest required")
        if any(c not in "0123456789abcdef" for c in w["source_sha256"]):
            raise ValueError("source_sha256 must be lowercase hexadecimal")
        vh=indexed(pred["v50"]["horses"])
        wh=indexed(w["horses"])
        if set(vh)!=set(wh): raise ValueError("horse roster mismatch")
        probs=[float(vh[k]["p1"]) for k in sorted(vh,key=int)]
        if any(not math.isfinite(p) or not 0<p<1 for p in probs) or abs(sum(probs)-1)>1e-5:
            raise ValueError("non-normalized v50 win probabilities")
        horse_rows=[]
        for key in sorted(vh,key=int):
            h=wh[key]
            if moment(h["weight_observed_at"])>source_observed:
                raise ValueError("horse weight timestamp newer than source observed timestamp")
            kg=h.get("body_weight_kg")
            if kg is not None and (isinstance(kg,bool) or not isinstance(kg,(int,float)) or not 300<=kg<=650):
                raise ValueError("weight out of plausible range")
            if kg is None and h.get("weight_change_kg") is not None:
                raise ValueError("weight change cannot be known without measured weight")
            delta=h.get("weight_change_kg")
            horse_rows.append({"number":int(key),"name":vh[key].get("name"),
                 "v50_p1":float(vh[key]["p1"]),"body_weight_kg":kg,
                 "weight_change_kg":delta,"weight_change_bucket":bucket(delta),
                 "weight_observed_at":h["weight_observed_at"]})
        out.append({"race":race,"original_off_at":w["original_off_at"],
                    "weight_source_url":w["source_url"],
                    "weight_source_sha256":w["source_sha256"],
                    "weight_source_observed_at":w["observed_at"],
                    "horses":horse_rows})
    return {"schema":"jra-v50-weight-paired-preoff-v1",
            "status":"ARCHIVED_PREOFF_RESEARCH_NO_V51_PROMOTION",
            "forecast_asof":v50["forecast_asof"],
            "v50_file_sha256":v50_hash,"weight_file_sha256":weight_hash,
            "canonical_database_sha256":v50["canonical_database_sha256"],
            "v50_policy_sha256":v50["policy_sha256"],
            "v50_forecast_source_sha256":v50["forecast_sha256"],
            "v50_rider_source_sha256":v50["rider_sha256"],
            "production_model":"v50","research_model":"v51",
            "races":out}

def index_races(rows,key):
    if not isinstance(rows,list) or not rows:raise ValueError("nonempty races required")
    keys=[r[key] for r in rows]
    if len(set(keys))!=len(keys):raise ValueError("duplicate race")
    return dict(zip(keys,rows))

def immutable_save(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return digest(data)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v50",required=True);p.add_argument("--weights",required=True)
    p.add_argument("--forecast-source",required=True,help="Exact immutable source input to standard v50")
    p.add_argument("--output-dir",required=True)
    p.add_argument("--weight-source-archive",required=True,help="directory of original preoff source bytes indexed by SHA256")
    a=p.parse_args()
    v,vhash=raw(a.v50);w,whash=raw(a.weights)
    origin,origin_sha=raw(a.forecast_source)
    if origin_sha!=v.get("forecast_sha256"):
        raise ValueError("v50 source bytes do not match forecast SHA256")
    forecast_races=index_races(origin.get("races"),"race")
    weight_races=index_races(w.get("races"),"race")
    if set(forecast_races)!=set(weight_races):
        raise ValueError("race set mismatch with original v50 forecast input")
    if moment(origin.get("asof"))!=moment(v["forecast_asof"]):
        raise ValueError("forecast input asof mismatch")
    for race in forecast_races:
        if moment(forecast_races[race]["original_off_at"])!=moment(weight_races[race]["original_off_at"]):
            raise ValueError("off timestamp mismatch from original forecast input")
        if set(indexed(forecast_races[race]["horses"]))!=set(indexed(weight_races[race]["horses"])):
            raise ValueError("forecast source and weight roster mismatch")
    # Independently verify that each source digest actually corresponds to saved
    # original bytes rather than an unverified claim inside the JSON manifest.
    # Existence/hash is necessary but not proof of original capture wall-clock time.
    source_dir=Path(a.weight_source_archive)
    if not source_dir.is_dir():raise ValueError("original source archive folder missing")
    for item in w["races"]:
        fingerprint=item["source_sha256"]
        if not isinstance(fingerprint,str) or len(fingerprint)!=64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
            raise ValueError("source SHA256 malformed")
        source_file=source_dir/(fingerprint+".bin")
        if not source_file.is_file() or source_file.is_symlink() or not source_file.stat().st_size:
            raise ValueError("source bytes not archived for race "+item["race"])
        h=hashlib.sha256()
        with source_file.open("rb") as stream:
            for piece in iter(lambda:stream.read(1048576),b""):h.update(piece)
        if h.hexdigest()!=fingerprint:
            raise ValueError("original source bytes and declared SHA256 mismatch")
    output=capture(v,w,v50_hash=vhash,weight_hash=whash)
    # Exact race and as-of are embedded in the file, SHA prevents ambiguous replacements.
    name="v50_weight_pair_"+moment(output["forecast_asof"]).strftime("%Y%m%dT%H%M%SZ")+"_"+vhash[:12]+".json"
    dst=Path(a.output_dir)/name
    checksum=immutable_save(dst,output)
    print(json.dumps({"saved":str(dst),"sha256":checksum,"races":len(output["races"]),
                      "status":"ARCHIVED_PREOFF_RESEARCH_NO_V51_PROMOTION"}))

if __name__=="__main__":main()
