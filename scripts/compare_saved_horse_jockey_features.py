"""Retrospective feature ablation on saved Nov 1 forecasts (no canonical DB).

This is same-day exploratory analysis, NOT unseen validation. No promotion.
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "reports/odds_refresh_20261101_morning/PREDICTIONS.json"
SETTLEMENT = ROOT / "reports/review_20261101/FOUR_MODEL_SETTLEMENT_20261101T194949+0900.md"


def actual_winners(text):
    result = {}
    for track, race, first in re.findall(
        r"^- \[(東京|京都)(\d+)R\]\([^)]+\)：(\d+)-\d+-\d+",
        text, re.MULTILINE
    ):
        result[f"{track}{race}R"] = int(first)
    return result


def score(name, horse, runner):
    p = max(horse["p1"], 1e-300)
    j = (runner.get("jockey_form") if runner.get("jockey_form") is not None else .25) - .25
    starts = runner.get("starts") or 0
    wins = runner.get("wins") or 0
    h = (wins + 1) / (starts + 5) - .15
    if name == "D":
        return p
    if name == "D_jockey_weak":
        return math.log(p) + .5*j
    if name == "D_jockey_strong":
        return math.log(p) + 1.5*j
    if name == "D_horse":
        return math.log(p) + .4*h
    if name == "D_combined":
        return math.log(p) + .7*j + .4*h
    if name == "D_top3":
        return math.log(p) + .3*(horse["p2"]+horse["p3"])
    raise ValueError(name)


def main():
    races = json.loads(PRED.read_text())["races"]
    actual = actual_winners(SETTLEMENT.read_text())
    labels = ("D", "D_jockey_weak", "D_jockey_strong",
              "D_horse", "D_combined", "D_top3")
    result = {label: dict(hits=0, races=0) for label in labels}
    for race in races:
        if race["race"] not in actual:
            continue
        runners = {r["number"]: r for r in race["runners"]}
        horses = race["models"]["D"]["horses"]
        for label in labels:
            winner = max(horses, key=lambda h: (
                score(label, h, runners[h["number"]]), -h["number"]
            ))["number"]
            result[label]["hits"] += int(winner == actual[race["race"]])
            result[label]["races"] += 1
    for value in result.values():
        value["rate"] = value["hits"]/value["races"] if value["races"] else None
    print(json.dumps(dict(schema="saved-feature-ablation-v1",
                          source="Nov 1 saved morning observations and settlement",
                          caution="Same-period exploration; not unseen validation",
                          results=result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
