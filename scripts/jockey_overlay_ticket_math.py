"""Frozen legacy PL ticket approximation; research only, not calibrated."""
import itertools

def plackett_luce(weights):
    n = len(weights)
    triples = {}
    p2 = [0.0] * n
    p3 = [0.0] * n
    pairs = {}
    trios = {}
    for i, j, k in itertools.permutations(range(n), 3):
        q = weights[i] * weights[j] / (1 - weights[i]) * weights[k] / (1 - weights[i] - weights[j])
        triples[(i, j, k)] = q
        p2[j] += q
        p3[k] += q
        pairs[tuple(sorted((i, j)))] = pairs.get(tuple(sorted((i, j))), 0.0) + q
        trios[tuple(sorted((i, j, k)))] = trios.get(tuple(sorted((i, j, k))), 0.0) + q
    return p2, p3, triples, pairs, trios

def threshold(items, threshold):
    chosen, cumulative = [], 0.0
    for numbers, probability in sorted(items.items(), key=lambda x: (-x[1], x[0])):
        cumulative += probability
        chosen.append({"numbers": list(numbers), "p": probability, "cumulative": cumulative})
        if cumulative + 1e-12 >= threshold:
            break
    return {"threshold": threshold, "count": len(chosen), "cumulative": cumulative, "tickets": chosen}

def calculate_model(horses, p1):
    numbers = [h.get("display_key", h["number"]) for h in horses]
    p2, p3, triples, pairs, trios = plackett_luce(p1)
    order = sorted(range(len(horses)), key=lambda i: (-p1[i], numbers[i]))
    exact = max(triples, key=triples.get)
    single = {(numbers[i],): p1[i] for i in range(len(horses))}
    pair_no = {tuple(sorted((numbers[i], numbers[j]))): p for (i, j), p in pairs.items()}
    trio_no = {tuple(sorted((numbers[i], numbers[j], numbers[k]))): p for (i, j, k), p in trios.items()}
    ranked = [{"number": numbers[i], "name": horses[i]["name"], "p1": p1[i], "p2": p2[i], "p3": p3[i]} for i in order]
    return {
        "marks": dict(zip(["◎","○","▲","☆","△"], [r["number"] for r in ranked[:5]])),
        "ordered_top3": [numbers[i] for i in exact], "horses": ranked,
        "priority": {"single": threshold(single, .40), "quinella": threshold(pair_no, .25), "trio": threshold(trio_no, .30)},
        "research_stake_yen": 0, "stake_reason": "PREOFF_ODDS_MISSING_OR_UNCALIBRATED_DO_NOT_FORCE_BUDGET",
    }
