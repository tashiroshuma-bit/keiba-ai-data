"""Point-in-time feature builder: past results only; prevents same-race leakage."""
import csv, datetime as dt, collections, json, argparse
from pathlib import Path

def ts(s):
    v=dt.datetime.fromisoformat(s)
    if v.tzinfo is None: raise ValueError("timezone offset required")
    return v

def read_csv(p):
    with open(p,encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

def build(history, runners, cutoff_minutes=5):
    """history: historical race results with actual finish and result_available_at.
    runners: race entrants with off_timestamp and pre_off odds timestamp.
    All timestamps ISO8601 with timezone. No future results may enter predictors.
    """
    index=collections.defaultdict(list)
    for h in history:
        for k in ("horse_id","race_id","off_timestamp","result_available_at","finish_position","distance_m","surface"):
            if not h.get(k): raise ValueError(f"history missing {k}")
        if ts(h["result_available_at"]) < ts(h["off_timestamp"]):
            raise ValueError("result published before race")
        index[h["horse_id"]].append(h)
    output=[]
    for r in runners:
        for k in ("horse_id","race_id","off_timestamp","odds_timestamp","pre_off_odds"):
            if not r.get(k): raise ValueError(f"runner missing {k}")
        cutoff=ts(r["off_timestamp"])-dt.timedelta(minutes=cutoff_minutes)
        if ts(r["odds_timestamp"])>cutoff: raise ValueError("late odds")
        if float(r["pre_off_odds"])<=1: raise ValueError("invalid odds")
        eligible=sorted((h for h in index[r["horse_id"]]
          if h["race_id"]!=r["race_id"] and ts(h["result_available_at"])<=cutoff
          and ts(h["off_timestamp"])<ts(r["off_timestamp"])),
          key=lambda h:ts(h["off_timestamp"]))[-4:]
        finishes=[int(h["finish_position"]) for h in eligible if h["finish_position"].isdigit()]
        output.append({**r,
            "prior_4_starts":len(eligible),
            "prior_4_wins":sum(f==1 for f in finishes),
            "prior_4_mean_finish":round(sum(finishes)/len(finishes),4) if finishes else "",
            "prior_4_same_surface_starts":sum(h["surface"]==r.get("surface") for h in eligible),
            "prior_4_similar_distance_starts":sum(abs(int(h["distance_m"])-int(r["distance_m"]))<=200 for h in eligible)})
    return output

def audit_coverage(rows):
    groups=collections.defaultdict(list)
    for r in rows: groups[r.get("race_id","")].append(r)
    result=[]
    for race,rs in sorted(groups.items()):
        ids=[r.get("horse_number","") for r in rs]
        result.append({"race_id":race,"runner_count":len(rs),
          "unique_numbers":len(set(ids))==len(ids),
          "has_preoff_odds":all(r.get("odds_timestamp") and r.get("pre_off_odds") for r in rs),
          "has_source":all(r.get("source_url") for r in rs),
          "has_result":all(r.get("finish_position") for r in rs),
          "field_complete_attested":all(r.get("field_complete")=="yes" for r in rs)})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",required=True);p.add_argument("--runners",required=True)
    p.add_argument("--output-dir",default="output");p.add_argument("--cutoff-minutes",type=int,default=5)
    a=p.parse_args();dest=Path(a.output_dir);dest.mkdir(parents=True,exist_ok=True)
    runners=read_csv(a.runners)
    report=audit_coverage(runners)
    (dest/"coverage.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if not report or not all(x["unique_numbers"] and x["has_preoff_odds"] and x["has_source"] and x["field_complete_attested"] for x in report):
        raise SystemExit("coverage gate failed; see coverage.json")
    out=build(read_csv(a.history),runners,a.cutoff_minutes)
    with (dest/"point_in_time_features.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
    print(f"created {len(out)} leakage-safe feature rows")
if __name__=="__main__":main()
