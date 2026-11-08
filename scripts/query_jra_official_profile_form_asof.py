"""JRA official identity-keyed past form feature export for NEXT race only.

Only rows acquired from JRA official profile before forecast asof are used.
The original race's results cannot be retroactively re-predicted using Nov8
postrace captures. Distance and going fields retained with raw pace times:
no unverified cross-course normalization, fake opponent rating, or rider ID.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1_audit.json"

def parse(s):
    t=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError("offset time required")
    return t

def source_sha_verify(database=DB,audit=AUDIT):
    expected=json.loads(Path(audit).read_text())
    h=hashlib.sha256()
    with Path(database).open("rb") as fh:
        for chunk in iter(lambda:fh.read(2**20),b""):h.update(chunk)
    if h.hexdigest()!=expected["sqlite_sha256"] or Path(database).stat().st_size!=expected["sqlite_bytes"]:
        raise ValueError("JRA official profile source SHA/size mismatch")
    if expected["verified_profiles"]!=18 or expected["past_race_history_rows"]!=193:
        raise ValueError("expected actual 18 profiles and 193 historic runs")
    return True

def make_features(db,horse_id,asof,off_at,*,target_surface=None):
    if not (str(horse_id).startswith("jra:") and len(str(horse_id))==14
            and str(horse_id)[4:].isdigit()):
        raise ValueError("official horse profile ID required")
    asof=parse(asof);off=parse(off_at)
    if not asof<off:raise ValueError("asof must be before target off")
    c=sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    try:
        meta=c.execute("SELECT * FROM official_profile WHERE horse_id=?",(horse_id,)).fetchone()
        if not meta:return {"horse_id":horse_id,"status":"MISSING_OFFICIAL_PROFILE",
                             "observed_preoff_features":0,"features":None}
        observed=parse(meta["observed_at"])
        if not observed<=asof:
            return {"horse_id":horse_id,"status":"PROFILE_NOT_YET_OBSERVED_ASOF",
                    "observed_preoff_features":0,"features":None}
        rows=c.execute("""SELECT * FROM official_past_run WHERE horse_id=?
             ORDER BY prior_race_date DESC""",(horse_id,)).fetchall()
        accepted=[]
        for r in rows:
            item=dict(r)
            when=dt.date.fromisoformat(item["prior_race_date"])
            # Require full 2-calendar-day lag by target off day, regardless
            # of what the profile shows about subsequent performance.
            if (off.date()-when).days<2:continue
            if parse(item["profile_observed_at"])>asof:continue
            if item["source_profile_sha256"]!=meta["source_sha256"]:
                raise ValueError("historical source SHA mismatch")
            accepted.append(item)
        recent=accepted[:5]
        valid_fin=[h for h in recent if h["finish_position"] is not None]
        def starts_on(surface):
            return sum(1 for x in accepted if x["distance_surface"].startswith(surface))
        return {"horse_id":horse_id,"status":"PROVEN_PAST_HISTORY" if accepted else "NO_PAST_RUNS",
          "source_profile_url":meta["profile_url"],
          "source_observed_at":meta["observed_at"],
          "published_at_originally_verified":False,
          "usable_only_after_capture":True,
          "observed_preoff_features":len(accepted),
          "features":{
              "prior_race_count_in_captured_profile":len(accepted),
              "last5_starts":len(recent),
              "last5_top3":sum(x["finish_position"]<=3 for x in valid_fin),
              "last5_win":sum(x["finish_position"]==1 for x in valid_fin),
              "last5_mean_finishing_place":sum(x["finish_position"] for x in valid_fin)/len(valid_fin) if valid_fin else None,
              "observed_turf_starts":starts_on("芝"),
              "observed_dirt_starts":starts_on("ダート"),
              "target_surface_past_starts":starts_on(target_surface) if target_surface else None,
              "recent_races":[{
                    "race_date":x["prior_race_date"],"venue":x["venue"],
                    "distance_surface":x["distance_surface"],"going":x["going"],
                    "field_size":x["field_size"],"finish_position":x["finish_position"],
                    "popularity_final":x["popularity_final"],"jockey_name":x["jockey_name"],
                    "time_text":x["time_text"],"bodyweight_kg":x["bodyweight_kg"]}
                for x in recent]},
          "original_2026_11_08_prediction_retroactive":False,
          "canonical_v50_modified":False}
    finally:c.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--horse-id",required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--off-at",required=True)
    p.add_argument("--surface",choices=["芝","ダート"])
    a=p.parse_args()
    source_sha_verify()
    print(json.dumps(make_features(DB,a.horse_id,a.asof,a.off_at,
                    target_surface=a.surface),ensure_ascii=False))
if __name__=="__main__":main()
