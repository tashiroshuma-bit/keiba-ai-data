"""Retrospective 2026-11-01 frozen D versus horse confidence ablation.

Uses only saved pre-race career counts, predictions, and final winners.
Exploratory same-day evaluation, not unseen validation or model promotion.
"""
import json
import math
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def winners(text):
    return {f"{track}{race}R":int(first) for track,race,first in
            re.findall(r"^- \[(東京|京都)(\d+)R\]\([^)]+\)：(\d+)-",
                       text,re.MULTILINE)}


def run():
    forecasts=json.loads((ROOT/"reports/odds_refresh_20261101_morning/PREDICTIONS.json").read_text())["races"]
    actual=winners((ROOT/"reports/review_20261101/FOUR_MODEL_SETTLEMENT_20261101T194949+0900.md").read_text())
    methods=("baseline","old_horse","confidence","confidence_weak","confidence_strong")
    results={name:dict(hits=0,races=0,changed=[]) for name in methods}
    for race in forecasts:
        if race["race"] not in actual:
            continue
        runners={r["number"]:r for r in race["runners"]}
        horses=race["models"]["D"]["horses"]
        picks={}
        for name in methods:
            def score(h):
                runner=runners[h["number"]]
                n=runner.get("starts") or 0
                podium=(runner.get("wins") or 0)+.5*(runner.get("seconds") or 0)+.25*(runner.get("thirds") or 0)
                smooth=(podium+1.2)/(n+8)
                delta={"baseline":0,"old_horse":.8*podium/(n+5),
                       "confidence":.8*(smooth-.15),
                       "confidence_weak":.4*(smooth-.15),
                       "confidence_strong":1.6*(smooth-.15)}[name]
                return math.log(max(h["p1"],1e-300))+delta
            picks[name]=max(horses,key=lambda h:(score(h),-h["number"]))["number"]
        for name in methods:
            row=results[name]
            row["races"]+=1
            row["hits"]+=int(picks[name]==actual[race["race"]])
            if picks[name]!=picks["baseline"]:
                row["changed"].append(dict(race=race["race"],old=picks["baseline"],
                                           new=picks[name],actual=actual[race["race"]]))
    for value in results.values():
        value["hit_rate"]=value["hits"]/value["races"]
    if any(value["races"]!=23 for value in results.values()):
        raise ValueError("expected 23 races")
    return dict(schema="horse-confidence-ablation-20261101-v1",
                source="saved pre-race forecasts and post-race settlement",
                caution="retrospective same-day exploratory, not independent validation",
                production_model_changed=False,results=results)


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
