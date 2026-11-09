"""Compare true pre-off rank shadow outputs against SAME-RACE standard v50.

The rank shadow may carry its own learned conditional 2nd/3rd picks. They
must not be mislabeled as p1-descending PL triplets. This is evaluation only,
never production promotion.
"""
import math
try:
    from scripts.capture_v50_bodyweight import moment
except ModuleNotFoundError:
    from capture_v50_bodyweight import moment

def roster(rows,key):
    if len(rows)<3:raise ValueError("too few horses")
    d={str(r[key]):r for r in rows}
    if len(d)!=len(rows):raise ValueError("duplicate horse number")
    return d

def compare(archive,rank_snapshots,official_results):
    if archive.get("schema")!="jra-v50-weight-paired-preoff-v1":
        raise ValueError("original v50 paired archive required")
    snapshots=rank_snapshots.get("races")
    results=official_results.get("races")
    if not isinstance(snapshots,list) or not isinstance(results,list):
        raise ValueError("complete race snapshots required")
    by_rank={r["race"]:r for r in snapshots}
    by_result={r["race"]:r for r in results}
    by_base={r["race"]:r for r in archive["races"]}
    if len(by_rank)!=len(snapshots) or len(by_result)!=len(results):
        raise ValueError("duplicate race")
    if not set(by_rank)==set(by_result)==set(by_base):
        raise ValueError("race set or result set mismatch")
    asof=moment(archive["forecast_asof"])
    rows=[]
    for race in sorted(by_base):
        a=by_base[race];s=by_rank[race];result=by_result[race]
        if s.get("deployment_status")!="experimental_rank_shadow" or s.get("strict_production_validated") is not False:
            raise ValueError("trained rank output must remain research-only")
        if moment(s["created_at"])>asof or moment(s["off_timestamp"])!=moment(a["original_off_at"]):
            raise ValueError("rank forecast was made after v50 asof or different off")
        if asof>=moment(a["original_off_at"]):
            raise ValueError("v50 pair not actually before off")
        b=roster(a["horses"],"number")
        h=roster(s["runners"],"horse_number")
        if set(b)!=set(h):raise ValueError("horse roster mismatch")
        outcome=[str(x) for x in result["finish_order"]]
        if len(set(outcome))!=len(b) or set(outcome)!=set(b):
            raise ValueError("official full finishing order required")
        if moment(official_results["observed_at"])<=moment(a["original_off_at"]):
            raise ValueError("official result timestamp impossible")
        for probability_key in ("p_first","p_second","p_third"):
            probs=[h[k][probability_key] for k in b]
            if any(isinstance(p,bool) or not isinstance(p,(float,int)) or
                   not math.isfinite(p) or p<0 or p>1 for p in probs) or abs(sum(probs)-1)>1e-5:
                raise ValueError("rank conditional model marginal invalid")
        v50={k:float(b[k]["v50_p1"]) for k in b}
        rank={k:float(h[k]["p_first"]) for k in h}
        v50_pick=max(sorted(v50,key=int),key=lambda k:v50[k])
        rank_pick=str(s["winner_pick"])
        rank_trio=[str(n) for n in s["top3_pick"]]
        rank_order=[str(n) for n in s["ordered_pick"]]
        if (rank_pick not in h or len(set(rank_trio))!=3 or
            len(set(rank_order))!=3 or not set(rank_trio)<=set(h) or not set(rank_order)<=set(h)):
            raise ValueError("invalid conditional podium picks")
        v50_top=sorted(v50,key=lambda k:(-v50[k],int(k)))[:3]
        metrics={}
        for name,p,top1,top3,order in (
            ("v50",v50,v50_pick,v50_top,v50_top),
            ("conditional_rank_shadow",rank,rank_pick,rank_trio,rank_order)):
            metrics[name]={
                "winner_hit":int(top1==outcome[0]),
                "winner_in_top3":int(outcome[0] in top3),
                "unordered_full_podium_hit":int(set(top3)==set(outcome[:3])),
                "ordered_full_podium_hit":int(order==outcome[:3]),
                "winner_logloss":-math.log(max(p[outcome[0]],1e-15)),
                "winner_brier":sum((p[k]-int(k==outcome[0]))**2 for k in p)}
        rows.append({"race":race,"date":race[:10],"v50":metrics["v50"],
                     "conditional_rank_shadow":metrics["conditional_rank_shadow"]})
    summary={}
    for name in ("v50","conditional_rank_shadow"):
        summary[name]={k:sum(row[name][k] for row in rows)/len(rows)
                       for k in rows[0][name]}
    return {"status":"REAL_PAIRED_SHADOW_EVALUATION_NO_AUTOMATIC_PROMOTION",
            "n_races":len(rows),"metrics":summary,
            "delta_rank_minus_v50":{k:summary["conditional_rank_shadow"][k]-summary["v50"][k]
                                     for k in summary["v50"]},
            "per_race":rows,
            "warnings":["v50 ordered podium here is p1-rank proxy; rank candidate uses its saved conditional ordered pick",
                        "True conditional training provenance must be independently checked",
                        "No claim that v51 learned rank shadow is superior without independent cohort"]}
