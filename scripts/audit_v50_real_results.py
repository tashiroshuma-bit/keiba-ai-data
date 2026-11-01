"""Paired real archived result audit. Not an independent promotion gate."""
import json
from collections import defaultdict
from pathlib import Path
from scripts.convert_weekend_to_v50 import adapt
from scripts.v50_rider_overlay import evaluate_p1

ARCHIVE=Path("reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json")
SCORES=Path("reports/review_20261031/scores.json")

def evaluate():
    source=json.loads(ARCHIVE.read_text())
    scores=json.loads(SCORES.read_text())
    truth={}
    for item in scores["scores"]:
        if item["model"]=="D":
            truth[item["race"]]=item["actual"][0]
    report={"status":"retrospective_only_not_independent_not_promoted",
            "official_verified":bool(scores.get("official_verified")),
            "model_results":{}}
    for model in "ABCD":
        races=[]
        for race in adapt(source,model=model)["races"]:
            race_name=race["race"].split(" ",1)[1]
            if race_name not in truth or not race["race"].startswith("2026-10-31"):
                continue
            races.append({"horses":race["horses"],
                          "actual_winner_number":truth[race_name]})
        report["model_results"][model]=evaluate_p1(races,{})
    return report

if __name__=="__main__":
    print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
