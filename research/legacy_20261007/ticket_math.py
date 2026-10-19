"""Race-level ticket evaluation. Python 3.10+, standard library only.

Examples:
  python ticket_math.py forecast --plan plan.json --scenarios top3.json
  python ticket_math.py settle --plan plan.json --result result.json

Forecasts require an independently validated *joint top-three* distribution.
Horse winner scores alone are deliberately not accepted as ticket probabilities.
"""
import argparse
import json
import math
from datetime import datetime
from pathlib import Path


TYPES = {"WIN": 1, "PLACE": 1, "QUINELLA": 2, "WIDE": 2, "TRIO": 3}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def timestamp(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("timezone offset required")
    return stamp


def field(plan):
    participants = tuple(int(x) for x in plan["field"])
    if len(participants) < 5 or len(set(participants)) != len(participants):
        raise ValueError("only races with at least 5 distinct starters are supported")
    if plan["budget_yen"] <= 0 or plan["budget_yen"] % 100:
        raise ValueError("budget must be positive and in 100-yen units")
    return participants


def check_plan(plan, price_required):
    participants = set(field(plan))
    start = timestamp(plan["scheduled_start"])
    if timestamp(plan["locked_at"]) >= start:
        raise ValueError("plan must be locked before the scheduled start")
    total = 0
    seen = set()
    for ticket in plan["tickets"]:
        kind = ticket["type"]
        horses = tuple(int(x) for x in ticket["horses"])
        if kind not in TYPES or len(horses) != TYPES[kind] or len(set(horses)) != len(horses):
            raise ValueError("invalid ticket type or horse count")
        if not set(horses) <= participants:
            raise ValueError("ticket contains a nonstarter")
        key = (kind, tuple(sorted(horses)))
        if key in seen:
            raise ValueError("duplicate ticket")
        seen.add(key)
        stake = ticket["stake_yen"]
        if not isinstance(stake, int) or stake <= 0 or stake % 100:
            raise ValueError("stake must be in 100-yen units")
        total += stake
        if price_required:
            payout = ticket.get("price_floor_per_100_yen")
            if not isinstance(payout, int) or payout < 100:
                raise ValueError("a conservative payout per 100 yen is required")
    if total > plan["budget_yen"]:
        raise ValueError("stakes exceed the race budget")
    if price_required and plan["tickets"] and timestamp(plan["odds_observed_at"]) >= start:
        raise ValueError("odds must be observed before the start")
    if price_required and plan["tickets"]:
        age = (timestamp(plan["locked_at"]) - timestamp(plan["odds_observed_at"])).total_seconds()
        if age < 0 or age > plan.get("max_odds_age_seconds", 600):
            raise ValueError("odds are too old or newer than the locked plan")
        if not plan.get("odds_source_url", "").startswith("https://"):
            raise ValueError("an odds source URL is required")
    return total


def key(ticket):
    return f'{ticket["type"]}:{"-".join(str(i) for i in sorted(ticket["horses"]))}'


def exposure(plan):
    stakes = {int(h): sum(t["stake_yen"] for t in plan["tickets"] if int(h) in t["horses"])
              for h in plan["field"]}
    return {str(h): v for h, v in stakes.items() if v}


def hit(ticket, top3, field_size):
    kind = ticket["type"]
    horses = set(ticket["horses"])
    first, second, third = top3
    if kind == "WIN":
        return first in horses
    if kind == "PLACE":
        return bool(horses & ({first, second, third} if field_size >= 8 else {first, second}))
    if kind == "QUINELLA":
        return horses == {first, second}
    if kind == "WIDE":
        return horses <= {first, second, third}
    if kind == "TRIO":
        return horses == {first, second, third}
    raise ValueError("unsupported ticket")


def forecast(plan, scenarios):
    stake = check_plan(plan, True)
    start = timestamp(plan["scheduled_start"])
    if scenarios.get("validation_status") != "independently_validated":
        raise ValueError("joint scenarios have no independent validation: no ticket probabilities or recommendation")
    if scenarios["race_id"] != plan["race_id"] or timestamp(scenarios["generated_at"]) >= start:
        raise ValueError("joint scenarios must match the race and predate the start")
    if not scenarios.get("validation_report_id"):
        raise ValueError("independent validation report ID is required")
    seen = set()
    mass = 0.0
    distributions = []
    for row in scenarios["top3"]:
        top = tuple(int(i) for i in row["order"])
        p = float(row["probability"])
        if len(top) != 3 or len(set(top)) != 3 or not set(top) <= set(plan["field"]):
            raise ValueError("invalid top-three outcome")
        if top in seen or not math.isfinite(p) or p <= 0:
            raise ValueError("duplicate outcome or invalid probability")
        seen.add(top)
        mass += p
        distributions.append((top, p))
    expected_count = len(plan["field"]) * (len(plan["field"]) - 1) * (len(plan["field"]) - 2)
    if len(seen) != expected_count or abs(mass - 1) > 1e-8:
        raise ValueError("joint distribution must include every ordered top-three outcome and sum to one")
    per_ticket = {key(t): 0.0 for t in plan["tickets"]}
    hit_prob = cover_prob = 0.0
    expected_payout = 0.0
    for top, probability in distributions:
        payout = 0
        any_hit = False
        for ticket in plan["tickets"]:
            if hit(ticket, top, len(plan["field"])):
                any_hit = True
                per_ticket[key(ticket)] += probability
                payout += ticket["stake_yen"] // 100 * ticket["price_floor_per_100_yen"]
        hit_prob += probability * any_hit
        cover_prob += probability * (payout >= stake and stake > 0)
        expected_payout += probability * payout
    return {"race_id": plan["race_id"], "declared_validation_report_id": scenarios["validation_report_id"],
            "ticket_hit_probability": per_ticket, "at_least_one_hit_probability": hit_prob,
            "no_hit_probability": max(0.0, 1 - hit_prob),
            "single_horse_exposure_yen": exposure(plan),
            "investment_yen": stake, "unspent_budget_yen": plan["budget_yen"] - stake,
            "recover_investment_probability_at_price_floor": cover_prob,
            "expected_payout_yen_at_price_floor": expected_payout,
            "expected_net_yen_at_price_floor": expected_payout - stake,
            "price_note": "pre-race price floors are not final JRA payouts; validation_report_id is supplied by the caller, not audited by this program"}


def settle(plan, result):
    stake = check_plan(plan, False)
    if result["race_id"] != plan["race_id"]:
        raise ValueError("result is from a different race")
    if result.get("result_status") != "final_all_started_no_dead_heat":
        raise ValueError("refunds, nonstarters and dead heats require a separate settlement rule")
    if not result.get("source_url", "").startswith(("https://www.jra.go.jp/", "https://sp.jra.jp/")):
        raise ValueError("official JRA result URL required")
    if timestamp(result["confirmed_at"]) <= timestamp(plan["scheduled_start"]):
        raise ValueError("result confirmation must follow the scheduled start")
    top = tuple(int(i) for i in result["top3"])
    if len(top) != 3 or len(set(top)) != 3 or not set(top) <= set(plan["field"]):
        raise ValueError("invalid result top three")
    outcomes = []
    payout = 0
    for ticket in plan["tickets"]:
        won = hit(ticket, top, len(plan["field"]))
        paid = result["jra_payout_per_100_yen"].get(key(ticket)) if won else 0
        if won and (not isinstance(paid, int) or paid < 100):
            raise ValueError("missing official 100-yen payout for a winning ticket")
        returned = ticket["stake_yen"] // 100 * paid
        payout += returned
        outcomes.append({"ticket": key(ticket), "stake_yen": ticket["stake_yen"],
                         "hit": won, "payout_yen": returned})
    return {"race_id": plan["race_id"], "result_source": result["source_url"],
            "tickets": outcomes, "ticket_hit": any(x["hit"] for x in outcomes),
            "single_horse_exposure_yen": exposure(plan),
            "recovered_investment": payout >= stake and stake > 0,
            "investment_yen": stake, "unspent_budget_yen": plan["budget_yen"] - stake,
            "payout_yen": payout, "net_yen": payout - stake,
            "return_rate": payout / stake if stake else None,
            "purchase_note": "hypothetical unless actual purchase is separately verified"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("forecast", "settle"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--scenarios")
    parser.add_argument("--result")
    args = parser.parse_args()
    plan = read(args.plan)
    if args.command == "forecast":
        if not args.scenarios:
            parser.error("--scenarios is required")
        report = forecast(plan, read(args.scenarios))
    else:
        if not args.result:
            parser.error("--result is required")
        report = settle(plan, read(args.result))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

