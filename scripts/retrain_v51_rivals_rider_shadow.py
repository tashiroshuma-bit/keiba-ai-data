"""v51 candidate: safe horse-vs-opponent strength, race pace and rider history.

Research ONLY; this candidate underperformed on 2025, so must not replace v50.
Reproduce using canonical jra_2023_2025.sqlite supplied outside the repository:
KEIBA_CANONICAL_DB=... KEIBA_RETRAIN_OUTPUT_DIR=... python -m scripts.retrain_v51_rivals_rider_shadow
"""
from __future__ import annotations
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path

import numpy as np
try:
    from scripts import retrain_v50_canonical_db_shadow as base
except ModuleNotFoundError:
    import retrain_v50_canonical_db_shadow as base

OUT=Path(os.environ.get("KEIBA_RETRAIN_OUTPUT_DIR","/mnt/data/keiba"))
ADDITIONS=[
    "opponent_prior_strength","opponent_strength_last3","beat_opponent_strength",
    "speed_recent_last3","pace_front_last3","rider_surface_residual",
    "rider_horse_strength_interaction","recent_form_vs_lifetime",
    "opponent_quality_x_recency",
]

def make_enriched(events,rows):
    """Add only information from racing days at least 2 days before this race.

    Opponent ability for each historic start is fixed BEFORE that start's finish
    and before any new rider/horse updates, avoiding label-to-feature leakage.
    Horse/jockey IDs are already official; missing remains missing.
    """
    stats=collections.defaultdict(lambda:{
        "n":0,"sum_opp":0.,"recent":collections.deque(maxlen=3),
        "beat":0.,"speed":collections.deque(maxlen=3),
        "pace":collections.deque(maxlen=3)})
    horse=collections.defaultdict(lambda:{"n":0,"place":0.})
    rider=collections.defaultdict(lambda:{"n":0,"res":0.})
    queue=collections.deque()
    audit=collections.Counter()
    if len(events)!=len(rows):
        raise ValueError("races and prebuilt features misaligned")
    for ev,row in zip(events,rows):
        if ev["race_id"]!=row["race_id"]:
            raise ValueError("source race mismatch")
        day=dt.date.fromisoformat(ev["date"])
        cutoff=day-dt.timedelta(days=2)
        while queue and dt.date.fromisoformat(queue[0][0]["date"])<=cutoff:
            old,pre=queue.popleft()
            for h,ctx in zip(old["horses"],pre):
                hid,jid,fin=h["horse_id"],h["jockey_id"],h["finish"]
                if hid:
                    st=stats[hid];st["n"]+=1
                    st["sum_opp"]+=ctx["opponent"]
                    st["recent"].append(ctx["opponent"])
                    st["beat"]+=ctx["opponent"]*(fin<=3)
                    speed=h.get("speed_z")
                    if isinstance(speed,(int,float)) and math.isfinite(speed):
                        st["speed"].append(float(speed))
                    corner=h.get("corner4")
                    if isinstance(corner,(int,float)) and math.isfinite(corner):
                        st["pace"].append(1-float(corner)/old["field"])
                    hh=horse[hid];hh["n"]+=1;hh["place"]+=int(fin<=3)
                if jid:
                    rr=rider[jid,old["surface"]]
                    rr["n"]+=1
                    rr["res"]+=int(fin<=3)-ctx["own"]
        active=ev["horses"]
        own=[]
        for h in active:
            hh=horse.get(h["horse_id"]) if h["horse_id"] else None
            own.append((hh["place"]+3)/(hh["n"]+15) if hh else .2)
        opponent=[(sum(own)-p)/(len(own)-1) for p in own]
        extra=[]
        for i,(h,ownp,opp) in enumerate(zip(active,own,opponent)):
            hid,jid=h["horse_id"],h["jockey_id"]
            st=stats.get(hid) if hid else None
            n=st["n"] if st else 0
            rr=rider.get((jid,ev["surface"])) if jid else None
            prior_opp=st["sum_opp"]/n if n else .2
            recent_opp=sum(st["recent"])/len(st["recent"]) if st and st["recent"] else .2
            beat=(st["beat"]+1)/(n+5) if st else .2
            speed=sum(st["speed"])/len(st["speed"]) if st and st["speed"] else 0.
            pace=sum(st["pace"])/len(st["pace"]) if st and st["pace"] else 0.
            residual=rr["res"]/(rr["n"]+30) if rr else 0.
            # base X was centered within this race; these are centered contrasts.
            form=row["X"][i,2]
            vs_life=form-row["X"][i,1]
            extra.append([prior_opp,recent_opp,beat,speed,pace,
                          residual,residual*ownp,vs_life,recent_opp*form])
            audit["opponent_history_available"]+=int(bool(st and n>0))
            audit["rider_surface_available"]+=int(bool(rr and rr["n"]>0))
        ex=np.array(extra,dtype=float)
        if not np.isfinite(ex).all():
            raise ValueError("nonfinite as-of opponent/pace inputs")
        row["X"]=np.hstack((row["X"],ex-ex.mean(axis=0)))
        queue.append((ev,[{"opponent":q,"own":p} for q,p in zip(opponent,own)]))
    return dict(audit)

def main():
    base.verify_canonical_database()
    events,skips=base.fetch()
    rows,coverage=base.create_rows(events)
    audit=make_enriched(events,rows)
    if len(base.FEATURES)==25:
        base.FEATURES.extend(ADDITIONS)
    elif len(base.FEATURES)!=34:
        raise ValueError("unexpected feature schema")
    byyear=collections.defaultdict(list)
    for row in rows:
        byyear[row["date"][:4]].append(row)
    first,select,hold25,hold26=(byyear[y] for y in ("2023","2024","2025","2026"))
    if min(map(len,(first,select,hold25,hold26)))<1800:
        raise ValueError("too few historical records")
    orig=list(range(18))
    candidates=[]
    for ridge in (.02,.1,.4):
        for name,idx in (
            ("baseline",orig),
            ("fullplus",orig+list(range(25,34))),
            ("opponent_rider",orig+[25,26,27,30,31,33]),
            ("speed_pace",orig+[28,29,30,32])):
            model=base.run_fit(first,ridge,idx)
            measured=base.score(select,base.predict(select,model))
            candidates.append({"ridge":ridge,"family":name,"features":idx,
                               "selection_2024":measured})
    # Parameters selected exclusively by 2024, NOT postrace 2025/2026.
    choose=lambda arr:max(arr,key=lambda r:(
        r["selection_2024"]["top1"],
        r["selection_2024"]["winner_top3"],
        -r["selection_2024"]["logloss"]))
    selected=choose([v for v in candidates if v["family"]!="baseline"])
    baseline=choose([v for v in candidates if v["family"]=="baseline"])
    train=first+select
    newmodel=base.run_fit(train,selected["ridge"],selected["features"])
    oldmodel=base.run_fit(train,baseline["ridge"],baseline["features"])
    stats={}
    for year,cohort in (("2025",hold25),("2026",hold26)):
        stats[year]={}
        for name,model in (("baseline",oldmodel),("v51_candidate",newmodel)):
            p=base.predict(cohort,model)
            stats[year][name]=base.score(cohort,p)
            stats[year][name]["weak_race_strata"]=base.strata(cohort,p)
    pass_all=all(
        stats[year]["v51_candidate"]["top1"]>=stats[year]["baseline"]["top1"]
        and stats[year]["v51_candidate"]["winner_top3"]>=stats[year]["baseline"]["winner_top3"]
        and stats[year]["v51_candidate"]["logloss"]<=stats[year]["baseline"]["logloss"]
        for year in ("2025","2026"))
    fitted={"weights":list(map(float,newmodel["weights"])),
            "feature_indices":newmodel["features"],
            "mean":list(map(float,newmodel["mean"])),
            "scale":list(map(float,newmodel["scale"])),
            "ridge":newmodel["ridge"]}
    result={"schema":"v51-candidate-2026-11-08-v1",
        "source_db_sha256":base.EXPECTED_DB_SHA256,
        "research_only":True,
        "canonical_v50_unchanged":True,
        "train_years":["2023","2024"],
        "validation_years":["2025","2026"],
        "year_counts":{y:len(r) for y,r in byyear.items()},
        "new_features":ADDITIONS,
        "identity_proven_only":True,
        "identity_unverified_not_name_joined":True,
        "two_calendar_day_history_lag":True,
        "proven_original_publication_at_preoff":False,
        "baseline_2024":baseline,"selection_2024":selected,
        "coverage":audit,
        "model":fitted,
        "holdouts":stats,
        "passed_strict_oos_gate":pass_all,
        "production_promotion":False}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"v51_rival_rider_retrain_results.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"candidate":selected["family"],"gate":pass_all,
          "holdouts":{year:{k:{field:r[field] for field in (
              "n","top1","winner_top3","logloss","brier")}
            for k,r in blocks.items()} for year,blocks in stats.items()}},
          ensure_ascii=False))
    if pass_all:
        print("Research gate passed; still requires canonical v50 paired comparison.")

if __name__=="__main__":
    main()
