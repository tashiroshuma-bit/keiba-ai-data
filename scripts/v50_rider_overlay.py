"""v50 rider-ability overlay; immutable v49 inputs and as-of validated rider residuals.

Research feature branch only until production CI and independent calibration pass.
"""
from __future__ import annotations
import math
from typing import Mapping, Sequence

VERSION = "v50"
UPDATED = "2026-11-01"
DEFAULT_WEIGHT = 1.0
DEFAULT_TEMPERATURE = 1.0


def apply_v50(horses: Sequence[dict], rider_residuals: Mapping[str, float],
              *, weight: float = DEFAULT_WEIGHT,
              temperature: float = DEFAULT_TEMPERATURE) -> list[dict]:
    """Return new horse records with v50_p1; never mutate saved v49 probabilities.

    rider_residuals must be computed exclusively from observations available
    before the forecast timestamp. Missing jockey IDs receive neutral residual.
    """
    if not horses or temperature <= 0 or not math.isfinite(temperature):
        raise ValueError("nonempty field and positive finite temperature required")
    if not math.isfinite(weight):
        raise ValueError("finite weight required")
    numbers = [h["number"] for h in horses]
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate horse numbers")
    probs = [float(h["p1"]) for h in horses]
    if any(not math.isfinite(p) or p <= 0 for p in probs):
        raise ValueError("all original p1 must be finite and positive")
    if abs(sum(probs)-1.0) > 1e-5:
        raise ValueError("original p1 not normalized")
    logits = []
    for horse, p in zip(horses, probs):
        rid = horse.get("jockey_id")
        residual = float(rider_residuals.get(rid, 0.0)) if rid else 0.0
        if not math.isfinite(residual):
            raise ValueError("nonfinite rider residual")
        logits.append((math.log(p) + weight * residual) / temperature)
    peak = max(logits)
    exp = [math.exp(x-peak) for x in logits]
    total = sum(exp)
    return [{**h, "v50_p1": value/total} for h, value in zip(horses, exp)]


def evaluate_p1(races: Sequence[dict], rider_residuals: Mapping[str, float],
                *, weight: float = DEFAULT_WEIGHT,
                temperature: float = DEFAULT_TEMPERATURE) -> dict:
    """Paired comparison; each race has horses and actual_winner_number."""
    result = {"races": 0, "v49_wins": 0, "v50_wins": 0,
              "v49_logloss": 0.0, "v50_logloss": 0.0,
              "v49_brier": 0.0, "v50_brier": 0.0}
    for race in races:
        horses = race["horses"]
        truth = race["actual_winner_number"]
        overlay = apply_v50(horses, rider_residuals, weight=weight,
                            temperature=temperature)
        winners = [i for i, h in enumerate(horses) if h["number"] == truth]
        if len(winners) != 1:
            raise ValueError("winner missing or ambiguous")
        winner = winners[0]
        original = [float(h["p1"]) for h in horses]
        revised = [float(h["v50_p1"]) for h in overlay]
        result["races"] += 1
        result["v49_wins"] += int(max(range(len(horses)), key=lambda i: original[i]) == winner)
        result["v50_wins"] += int(max(range(len(horses)), key=lambda i: revised[i]) == winner)
        for label, probabilities in (("v49", original), ("v50", revised)):
            result[label+"_logloss"] -= math.log(probabilities[winner])
            result[label+"_brier"] += sum((p - (i == winner))**2
                                         for i, p in enumerate(probabilities))
    if result["races"]:
        for key in ("v49_logloss", "v50_logloss", "v49_brier", "v50_brier"):
            result[key] /= result["races"]
    return result
