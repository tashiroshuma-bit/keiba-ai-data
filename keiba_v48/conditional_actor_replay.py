"""As-of conditional horse and horse-adjusted rider ablation on 6036 saved races.

Research only; 2025/26 inspected retrospective cohorts. Uses canonical DB,
saved feature cache and evidence-rank predictions with SHA checks.
Run: python keiba_v48/conditional_actor_replay.py --db PATH --cache DIR --lag 2 --output OUT
"""
import argparse, collections, gzip, json, math, pickle
from pathlib import Path
from enriched_features import load_archive
from actor_segmentation_replay import index_history
from features import timestamp
from completion_validation import sha
from validation import canonical

ROOT=Path(__file__).resolve().parent

def score_history(past, surface, distance, going):
    def shrunk(rows):
        n=len(rows)
        points=sum(1 if r.get("finish_position")==1 else .5 if r.get("finish_position")==2 else .25 if r.get("finish_position")==3 else 0 for r in rows)
        return (points+1.2)/(n+8),n
    overall,n=shrunk(past)
    on_surface=[r for r in past if r.get("surface")==surface]
    same_distance=[r for r in on_surface if r.get("distance_m") is not None and abs(float(r["distance_m"])-float(distance))<=200]
    same_going=[r for r in on_surface if going is not None and r.get("going")==going]
    # Conditional deviations are shrunk; unknown going contributes zero.
    s,ns=shrunk(on_surface);d,nd=shrunk(same_distance);g,ng=shrunk(same_going)
    return dict(overall=overall,horse_surface=(s-overall)*ns/(ns+8),
                horse_distance=(d-s)*nd/(nd+8),
                horse_going=(g-s)*ng/(ng+8) if going is not None else 0,
                starts=n)

def prior(rows, cutoff):
    return [r for r in rows if timestamp(r["off_timestamp"])<cutoff
            and timestamp(r["result_available_at"])<=cutoff]

def replay(db,cache,lag,output):
    state=json.loads((ROOT.parent/"PROJECT_STATE.json").read_text())
    if sha(db)!=state["database"]["sha256"]:
        raise ValueError("canonical DB SHA mismatch")
    stored=pickle.loads((Path(cache)/f"features_lag{lag}.pkl").read_bytes())
    if stored["identity"]["db"]!=sha(db) or stored["identity"]["lag"]!=lag:
        raise ValueError("feature cache mismatch")
    for name,digest in stored["identity"]["sources"].items():
        if sha(ROOT/name)!=digest:raise ValueError("feature source mismatch")
    reference={}
    for name,proof in json.loads((ROOT/f"reports/evidence_rank/prediction_inventory_lag{lag}.json").read_text()).items():
        path=ROOT/"reports/evidence_rank"/name
        if sha(path)!=proof["sha256"]:raise ValueError("reference SHA mismatch")
        for item in json.loads(gzip.decompress(path.read_bytes())):reference[item["race_id"]]=item
    history,_,_=load_archive(db,lag,allow_unlinked_fields=True)
    idx=index_history(history)
    # Precompute per-race rider residual using pre-race horse career scores.
    # Avoid expensive full-field scans by grouping once.
    by_race=collections.defaultdict(list)
    for h in history:by_race[h["race_id"]].append(h)
    rider_events=collections.defaultdict(list)
    for race,field in by_race.items():
        if len(field)<3:continue
        pre=[]
        for h in field:
            cutoff=timestamp(h["off_timestamp"])
            hp=prior(idx["horse"].get(h.get("horse_id"),[]),cutoff)
            pre.append(score_history(hp,h["surface"],h["distance_m"],h.get("going"))["overall"])
        mean=sum(pre)/len(pre)
        for h,s in zip(field,pre):
            pos=h.get("finish_position")
            if not isinstance(pos,int) or pos<1 or pos>len(field) or not h.get("jockey_id"):continue
            realized=(len(field)-pos)/(len(field)-1)
            expected=.5+.5*math.tanh(2*(s-mean))
            rider_events[h["jockey_id"]].append((h,realized-expected))
    for events in rider_events.values():events.sort(key=lambda x:timestamp(x[0]["off_timestamp"]))
    output_rows=[]
    for race in sorted((r for r in stored["races"] if r["race_id"] in reference),key=lambda r:(timestamp(r["off_timestamp"]),r["race_id"])):
        ref=reference[race["race_id"]]
        numbers=[int(x["horse_number"]) for x in race["rows"]]
        if numbers!=list(map(int,ref["horse_numbers"])):raise ValueError("roster mismatch")
        cutoff=min(timestamp(f["cutoff_timestamp"]) for f in race["features"])
        values={"horse_distance":[],"horse_surface":[],"horse_going":[],"rider_residual":[],"combined":[]}
        for h in race["rows"]:
            hp=prior(idx["horse"].get(h.get("horse_id"),[]),cutoff)
            hf=score_history(hp,h["surface"],h["distance_m"],h.get("going"))
            events=[v for r,v in rider_events.get(h.get("jockey_id"),[])
                    if timestamp(r["off_timestamp"])<cutoff and timestamp(r["result_available_at"])<=cutoff
                    and r.get("surface")==h.get("surface")]
            rider=sum(events)/(len(events)+30)
            values["horse_distance"].append(hf["horse_distance"])
            values["horse_surface"].append(hf["horse_surface"])
            values["horse_going"].append(hf["horse_going"])
            values["rider_residual"].append(rider)
            values["combined"].append(hf["horse_distance"]+hf["horse_surface"]+hf["horse_going"]+rider)
        # Existing calibrated winner pick is the comparator. New methods use
        # candidate ordering only as a tie-safe baseline: no invented p1 values.
        # Report standalone conditional signals, NOT a calibrated overlay.
        target=int(ref["candidate"]["target"][0])
        hits={"previous_calibrated":int(int(ref["candidate"]["winner_pick"])==target)}
        for name,signal in values.items():
            order=sorted(range(len(numbers)),key=lambda i:(-signal[i],numbers[i]))
            hits[name]=int(numbers[order[0]]==target)
        output_rows.append(dict(year=race["rows"][0]["race_date"][:4],hits=hits))
    if len(output_rows)!=6036:raise ValueError(f"expected 6036 races, got {len(output_rows)}")
    years={}
    for year in ("2025","2026"):
        subset=[r for r in output_rows if r["year"]==year]
        years[year]={"races":len(subset),"methods":{name:{"winner_hits":sum(r["hits"][name] for r in subset),
              "rate":sum(r["hits"][name] for r in subset)/len(subset)}
              for name in output_rows[0]["hits"]}}
    if years["2025"]["races"]!=3329 or years["2026"]["races"]!=2707:raise ValueError("year cohort mismatch")
    report=dict(schema="conditional-actor-standalone-retrospective-v1",years=years,
                caveats=["Not an overlay on calibrated p1; standalone ranking ablation",
                         "Historical publication times are assumed research lags",
                         "Rider residual is observational, not causal",
                         "Past evaluated years are not unseen validation"],
                production_promoted=False)
    Path(output).write_text(canonical(report)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True);p.add_argument("--cache",required=True)
    p.add_argument("--lag",type=int,choices=(2,7),required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps(replay(a.db,a.cache,a.lag,a.output),ensure_ascii=False))
