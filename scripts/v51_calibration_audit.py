"""Post-race reliability audit of same-preoff-source v50 and v51 bodyweight shadow.

Descriptive, no temperature fitting, no promotion. Requires exact full result
fields. Observe event as-of, never use results or final odds as features.
"""
import math
from collections import defaultdict
try:
    from scripts.capture_v50_bodyweight import moment
    from scripts.v51_body_weight_shadow import apply
except ModuleNotFoundError:
    from capture_v50_bodyweight import moment
    from v51_body_weight_shadow import apply

def bin_label(p):
    for threshold in (.10,.15,.20,.30,.40,.50,.70,1.01):
        if p<threshold:return f"<{threshold:.2f}"
    raise ValueError("bad p")

def metrics(archive,results):
    if archive.get("schema")!="jra-v50-weight-paired-preoff-v1":
        raise ValueError("genuine paired v50 input required")
    by={r["race"]:r for r in results["races"]}
    if len(by)!=len(results["races"]) or set(by)!={r["race"] for r in archive["races"]}:
        raise ValueError("race/result roster mismatch")
    out=defaultdict(lambda:defaultdict(list))
    asof=archive["forecast_asof"]
    for race in archive["races"]:
        key=race["race"]
        if not (moment(asof)<moment(race["original_off_at"])<moment(results["observed_at"])):
            raise ValueError("pre/post event ordering invalid")
        runners=race["horses"]
        keys=[str(r["number"]) for r in runners]
        ordered=[str(x) for x in by[key]["finish_order"]]
        if len(ordered)!=len(keys) or len(set(ordered))!=len(keys) or set(ordered)!=set(keys):
            raise ValueError("incomplete official result")
        base=[{"number":r["number"],"v50_p1":r["v50_p1"]} for r in runners]
        weights=[{"number":r["number"],"asof":asof,
                  "weight_observed_at":r["weight_observed_at"],
                  "weight_change_bucket":r["weight_change_bucket"]} for r in runners]
        s=apply(base,weights,asof=asof)
        p50={str(v["number"]):float(v["v50_p1"]) for v in base}
        p51={str(v["number"]):float(v["v51_shadow_p1"]) for v in s["horses"]}
        for model,p in (("v50",p50),("v51_shadow",p51)):
            top=max(sorted(p,key=int),key=lambda k:p[k])
            confidence=p[top]
            hit=int(top==ordered[0])
            entropy=-sum(v*math.log(v) for v in p.values())/math.log(len(p))
            group="high_entropy" if entropy>=.95 else "lower_entropy"
            item={"confidence":confidence,"hit":hit,
                  "winner_logloss":-math.log(p[ordered[0]])}
            out[model][("confidence",bin_label(confidence))].append(item)
            out[model][("entropy",group)].append(item)
    reports={}
    for model,groups in out.items():
        cells=[]
        for (axis,group),rows in sorted(groups.items()):
            cells.append({"axis":axis,"bucket":group,"n":len(rows),
                          "mean_top1_probability":sum(x["confidence"] for x in rows)/len(rows),
                          "actual_top1_hit":sum(x["hit"] for x in rows)/len(rows),
                          "mean_winner_logloss":sum(x["winner_logloss"] for x in rows)/len(rows)})
        n=sum(x["n"] for x in cells if x["axis"]=="confidence")
        ece=sum(x["n"]*abs(x["actual_top1_hit"]-x["mean_top1_probability"])
                for x in cells if x["axis"]=="confidence")/n
        reports[model]={"n_races":n,"top1_ece_descriptive":ece,"reliability":cells}
    return {"status":"PROSPECTIVE_CALIBRATION_AUDIT_ONLY",
            "comparisons":reports,
            "limitations":["Posthoc bins are descriptive; high confidence may have low sample size",
                           "No calibration coefficients re-fitted on evaluation results",
                           "Same-day/race correlations and race-field sizes require later cohort analysis",
                           "No v51 production promotion"]}
