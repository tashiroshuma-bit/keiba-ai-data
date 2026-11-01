"""Run true saved-A to v50 rider overlay paired retrospective check.

Calibration: 2026-10-31, evaluation: 2026-11-01.
Real data and actual historical as-of rider residuals, not 6036 race V50 proof.
October 31 and November 1 A horse probabilities are saved full-precision; both are normalized for floating point safety.
Do not alter the original forecasts or training data.
"""
import glob, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SNAP=ROOT/"reports/v50/horse_adjusted_rider_snapshot_20261029.json"
CAT=ROOT/"reports/weekend_20261031_1101/OBSERVED_JOCKEY_FEATURES_20261031T033200.json"
OCT_DOCS=ROOT/"reports/weekend_20261031_1101/rider_details_20261031"
OCT_RESULTS=ROOT/"reports/review_20261031/scores.json"
NOV_PRED=ROOT/"reports/odds_refresh_20261101_morning/PREDICTIONS.json"
NOV_WIN=ROOT/"reports/error_analysis_20261101/REAL_WINNER_RANK_AUDIT.json"

def pformat(raw):
    p={int(k):float(v) for k,v in raw.items()}
    if not p or any(not math.isfinite(v) or v<=0 for v in p.values()):raise ValueError("invalid source probability")
    return {k:v/sum(p.values()) for k,v in p.items()}

def corrected(prob, ids, surface, residuals, weight=1.0, temperature=1.0):
    logits={k:(math.log(v)+weight*residuals.get(surface+":"+(ids.get(k) or ""),0))/temperature for k,v in prob.items()}
    peak=max(logits.values()); exp={k:math.exp(v-peak) for k,v in logits.items()}
    den=sum(exp.values())
    return {k:v/den for k,v in exp.items()}

def metrics(races, residuals, weight, temperature, baseline=False):
    n=hits=coverage=0
    ll=brier=0.
    for r in races:
        a=r["p1"]
        p=a if baseline else corrected(a,r["jockey_ids"],r["surface"],residuals,weight,temperature)
        truth=r["winner"]
        if truth not in p:raise ValueError("result winner missing from forecast")
        picked=max(sorted(p),key=p.get)
        hits+=picked==truth
        ll-=math.log(p[truth]);brier+=sum((v-(k==truth))**2 for k,v in p.items())
        coverage+=sum(bool(jid) and (r["surface"]+":"+jid) in residuals for jid in r["jockey_ids"].values())
        n+=1
    return {"races":n,"winner_hits":hits,"winner_hit_rate":hits/n,"mean_log_loss":ll/n,"mean_brier":brier/n,"covered_runner_rows":coverage}

def get_oct(catalog):
    """Full-precision October 31 saved preoff A probabilities and matched rider IDs."""
    truth={x["race"]:x["actual"][0] for x in json.loads(OCT_RESULTS.read_text())["scores"] if x["model"]=="A"}
    archive=json.loads((ROOT/"reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json").read_text())
    out=[]
    for race in archive["races"]:
        if race["date"]!="2026-10-31" or not race.get("number_published"):continue
        key=race["race"]
        horses=race["models"]["A"]["horses"]
        p={h["number"]:h["p1"] for h in horses}
        roster={r["number"]:r.get("jockey_id") for r in race["runners"] if not r.get("withdrawn")}
        if len(p)<3 or set(p)!=set(roster):raise ValueError("October full field mismatch "+key)
        if key not in truth:raise ValueError("missing October actual "+key)
        out.append({"race":key,"surface":race["surface"],"winner":truth[key],"p1":pformat(p),"jockey_ids":roster})
    if len(out)!=23:raise ValueError("October expected 23 flat races; got "+str(len(out)))
    return out

def get_nov():
    races=json.loads(NOV_PRED.read_text())["races"]
    truth={x["race"]:x["winner"] for x in json.loads(NOV_WIN.read_text())["rows"]}
    out=[]
    for r in races:
        key=r["race"]
        ro={x["number"]:x.get("jockey_id") for x in r["runners"] if not x.get("withdrawn")}
        p={h["number"]:h["p1"] for h in r["models"]["A"]["horses"]}
        if set(p)!=set(ro):raise ValueError("November full field mismatch "+key)
        out.append({"race":key,"surface":r["surface"],"winner":truth[key],"p1":pformat(p),"jockey_ids":ro})
    if len(out)!=23:raise ValueError("November expected 23 flat races")
    return out

def run():
    snapshot=json.loads(SNAP.read_text());cat=json.loads(CAT.read_text())
    if snapshot["database_sha256"]!=cat["database_sha256"]:raise ValueError("different DB sources")
    catalog={name:jid for jid,name in cat["direct_identity_catalog"]}
    residuals=snapshot["residuals"]
    cal=get_oct(catalog);test=get_nov()
    grid=[0.7,0.8,0.9,1.0,1.1,1.25,1.5,1.75,2.0]
    temp=min(grid,key=lambda t:(metrics(cal,residuals,1,t)["mean_log_loss"],abs(t-1)))
    o={"schema":"v50-oct31-nov01-paired-retrospective-v1",
       "database_sha256":snapshot["database_sha256"],"rider_training_races":snapshot["races_used"],
       "calibration":"October 31 selects temperature only; no November test leakage",
       "source_provenance":"October and November archived A probabilities full precision; October outcome source official_verified=false",
       "calibration_temperature":temp,"calibration_races":len(cal),"test_races":len(test),
       "oct31_A":metrics(cal,residuals,0,1,baseline=True),
       "oct31_v50_uncalibrated":metrics(cal,residuals,1,1),
       "oct31_v50_calibrated":metrics(cal,residuals,1,temp),
       "nov01_A":metrics(test,residuals,0,1,baseline=True),
       "nov01_v50_uncalibrated":metrics(test,residuals,1,1),
       "nov01_v50_calibrated":metrics(test,residuals,1,temp),
       "model_switch":"NOT_AUTOMATIC; requires verified outcome and fully paired historical benchmark",
       "limits":["N=23 per day, no claim of full 2025-26 coverage",
                 "2016? No: source is 2026, not unseen to researcher",
                 "Rider coefficient fixed to 1; only temperature selected on calibration set",
                 "Rider IDs come from the exact saved full-card archive; official source reconciliation remains incomplete"]}
    return o

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
