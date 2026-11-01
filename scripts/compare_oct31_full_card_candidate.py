"""Research shadow candidate on saved full October 31 card; no production mutation.

Use saved pre-off runner counts and model D probabilities only.
"""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json"
S=ROOT/"reports/review_20261031/scores.json"

def evaluate():
    races=[r for r in json.loads(P.read_text())["races"] if r["date"]=="2026-10-31"]
    actual={r["race"]:r["actual"] for r in json.loads(S.read_text())["scores"] if r["model"]=="D"}
    out={}
    for name in ("baseline","horse","jockey_proxy","horse_jockey_proxy"):
        n=hits=unordered=ordered=0
        changes=[]
        for race in races:
            truth=actual.get(race["race"])
            if truth is None:continue
            runners={r["number"]:r for r in race["runners"]}
            horses=race["models"]["D"]["horses"]
            def score(h):
                r=runners[h["number"]]
                horse=.8*((r["wins"]+.5*r["seconds"]+.25*r["thirds"]+1.2)/(r["starts"]+8)-.15)
                rider=.8*((r.get("jockey_form") if r.get("jockey_form") is not None else .25)-.25)*min(1,(r.get("jockey_history_samples") or 0)/300)
                if name=="baseline":delta=0
                elif name=="horse":delta=horse
                elif name=="jockey_proxy":delta=rider
                else:delta=horse+.5*rider
                return math.log(max(h["p1"],1e-300))+delta
            ranked=sorted(horses,key=lambda h:(-score(h),h["number"]))
            base=sorted(horses,key=lambda h:(-h["p1"],h["number"]))[0]["number"]
            chosen=[h["number"] for h in ranked[:3]]
            n+=1
            hits+=chosen[0]==truth[0]
            unordered+=sorted(chosen)==sorted(truth)
            ordered+=chosen==truth
            if chosen[0]!=base:changes.append(dict(race=race["race"],base=base,chosen=chosen[0],winner=truth[0]))
        out[name]=dict(n=n,top1=hits,unordered=unordered,ordered=ordered,changes=changes)
    if any(v["n"]!=23 for v in out.values()):
        raise ValueError("Expected 23 scored flat races")
    return dict(date="2026-10-31",status="retrospective_research_not_production",
                model="D",results=out)

if __name__=="__main__":
    print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
