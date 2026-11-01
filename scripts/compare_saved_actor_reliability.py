"""Saved 2026-11-01 23-race horse/jockey reliability ablation.

Retrospective exploratory comparison; no model selection or deployment.
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def winners(text):
    return {f"{track}{num}R": int(first) for track, num, first in
            re.findall(r"^- \[(東京|京都)(\d+)R\]\([^)]+\)：(\d+)-",
                       text, re.MULTILINE)}


def score(name, horse, runner):
    base = math.log(max(horse["p1"], 1e-300))
    starts = runner.get("starts") or 0
    experience = math.log1p(starts) / math.log(11)
    podium = ((runner.get("wins") or 0) +
              .5 * (runner.get("seconds") or 0) +
              .25 * (runner.get("thirds") or 0)) / (starts + 5)
    jockey = ((runner.get("jockey_form") if runner.get("jockey_form") is not None
               else .25) - .25) * min(1, (runner.get("jockey_history_samples") or 0)/300)
    additions = {
        "baseline_D": 0,
        "experience": .35*experience,
        "horse_podium_reliability": .8*podium,
        "jockey_sample_reliability": .8*jockey,
        "combined": .25*experience + .45*podium + .45*jockey,
    }
    return base + additions[name]


def main():
    races = json.loads((ROOT/"reports/odds_refresh_20261101_morning/PREDICTIONS.json").read_text())["races"]
    actual = winners((ROOT/"reports/review_20261101/FOUR_MODEL_SETTLEMENT_20261101T194949+0900.md").read_text())
    names = ("baseline_D", "experience", "horse_podium_reliability",
             "jockey_sample_reliability", "combined")
    report = {}
    for name in names:
        hits = 0
        by_track = {}
        for race in races:
            if race["race"] not in actual:
                continue
            runners = {r["number"]: r for r in race["runners"]}
            horses = race["models"]["D"]["horses"]
            picked = max(horses, key=lambda h: (score(name, h, runners[h["number"]]),
                                                -h["number"]))["number"]
            ok = int(picked == actual[race["race"]])
            hits += ok
            track = by_track.setdefault(race["track"], {"hits": 0, "races": 0})
            track["hits"] += ok
            track["races"] += 1
        report[name] = dict(hits=hits, races=sum(x["races"] for x in by_track.values()),
                            hit_rate=hits/sum(x["races"] for x in by_track.values()),
                            by_track=by_track)
    print(json.dumps(dict(schema="saved-actor-reliability-ablation-v1",
                          evidence="saved 2026-11-01 morning forecasts and settlement",
                          validation="same-day retrospective exploratory, not unseen",
                          model_changed=False, results=report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
