"""Analyze historical races won by non-favorites, joined to saved final-market odds.

All final odds are STRICTLY HINDSIGHT: never feed into a pre-race forecast.
Exact stable race-id + full-runner order matching required. 2025 and 2026
results are separate so putative patterns can be examined out-of-sample.
"""
import json, math, hashlib, statistics
from pathlib import Path
from collections import defaultdict,Counter

ROOT=Path(__file__).resolve().parents[1]
HIST=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
MARKET=ROOT/"keiba_v48/reports/completion/final_market_decisions_lag7.json"
DEST=ROOT/"reports/nonfavorite_winner_analysis_20261107.json"
DOC=ROOT/"reports/nonfavorite_winner_analysis_20261107.md"
VENUES={"01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京","06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉"}

def rate(items):
    n=len(items)
    if not n:return {"n":0,"favorite_won":0,"other_won":0,"nonfavorite_rate":None}
    winners=sum(r["winner_is_favorite"] for r in items)
    return {"n":n,"favorite_won":winners,"other_won":n-winners,
            "nonfavorite_rate":(n-winners)/n}

def confidence(n,x):
    if not n:return None
    z=1.96
    p=x/n
    d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [center-half,center+half]

def main():
    histories=json.loads(HIST.read_text())
    markets=json.loads(MARKET.read_text())
    mindex={x["race_id"]:x for x in markets}
    if len(mindex)!=len(markets):raise ValueError("duplicated market race IDs")
    rows=[];skips=Counter();years=Counter()
    for race in histories:
        id=race.get("race_id")
        m=mindex.get(id)
        if not m:
            skips["market_missing"]+=1;continue
        probs=m.get("market_probabilities")
        numbers=race.get("horse_numbers")
        winner=str(race.get("winner_horse_number"))
        if not isinstance(probs,list) or not isinstance(numbers,list) or len(probs)!=len(numbers) or len(numbers)<3:
            skips["mismatched_field"]+=1;continue
        if len(set(map(str,numbers)))!=len(numbers) or not all(isinstance(x,(float,int)) and math.isfinite(x) and x>=0 for x in probs) or abs(sum(probs)-1)>1e-5:
            skips["market_or_number_invalid"]+=1;continue
        if winner not in numbers:
            skips["winner_not_in_field"]+=1;continue
        if m.get("odds_basis")!="post_race_final" or m.get("actionable_before_off") is not False:
            skips["odds_policy_mismatch"]+=1;continue
        order=sorted(range(len(probs)),key=lambda i:(-probs[i],str(numbers[i])))
        favorite=order[0]
        second=order[1]
        winneridx=numbers.index(winner)
        popularity=order.index(winneridx)+1
        fp=probs[favorite]
        sp=probs[second]
        field=len(numbers)
        starts=race.get("history_starts")
        start_unknown=not isinstance(starts,list) or len(starts)!=field
        horse_starts=int(starts[winneridx]) if not start_unknown and isinstance(starts[winneridx],(int,float)) and math.isfinite(starts[winneridx]) else None
        favor_starts=int(starts[favorite]) if not start_unknown and isinstance(starts[favorite],(int,float)) and math.isfinite(starts[favorite]) else None
        year=id[:4]
        venue=VENUES.get(id[4:6],id[4:6])
        rows.append({"race_id":id,"year":year,"venue":venue,
           "field_size":field,"winner_is_favorite":winneridx==favorite,
           "winner_market_rank":popularity,
           "favorite_market_share":fp,"second_market_share":sp,
           "favorite_share_gap":fp-sp,"favorite_share_ratio":fp/sp if sp else None,
           "market_entropy":-sum(p*math.log(p) for p in probs if p>0)/math.log(field),
           "winner_history_starts":horse_starts,"favorite_history_starts":favor_starts,
           "favorite_horse_number":str(numbers[favorite]),
           "winner_horse_number":winner})
        years[year]+=1
    if len(rows)<100:
        raise RuntimeError("historical join too small: "+str(len(rows))+" skipped "+str(skips))
    def bucket_fp(v):
        if v<0.20:return "<20%"
        if v<0.30:return "20–30%"
        if v<0.40:return "30–40%"
        if v<0.50:return "40–50%"
        return "50%+"
    def bucket_gap(v):
        if v<0.03:return "<3pp"
        if v<0.08:return "3–8pp"
        if v<0.15:return "8–15pp"
        return "15pp+"
    def bucket_field(n):
        if n<=9:return "3–9"
        if n<=13:return "10–13"
        return "14–18"
    def bucket_starts(n):
        if n is None:return "missing"
        if n==0:return "0"
        if n<=2:return "1–2"
        if n<=5:return "3–5"
        return "6+"
    def group(rows,fn):
        bins=defaultdict(list)
        for r in rows:bins[fn(r)].append(r)
        return {k:{**rate(v),"wilson95":confidence(len(v),sum(not x["winner_is_favorite"] for x in v))}
                for k,v in sorted(bins.items())}
    def breakdown(subset):
        return {
            "overall":rate(subset),
            "favorite_market_share":group(subset,lambda r:bucket_fp(r["favorite_market_share"])),
            "favorite_vs_second_market_share_gap":group(subset,lambda r:bucket_gap(r["favorite_share_gap"])),
            "field_size":group(subset,lambda r:bucket_field(r["field_size"])),
            "venue":group(subset,lambda r:r["venue"]),
            "winner_market_rank":dict(sorted(Counter(r["winner_market_rank"] for r in subset).items())),
            "winner_previous_starts":group(subset,lambda r:bucket_starts(r["winner_history_starts"])),
        }
    all_data=breakdown(rows)
    byyear={year:breakdown([r for r in rows if r["year"]==year]) for year in sorted(years)}
    # Compare favorite share & number of runners jointly; more meaningful than
    # unadjusted comparisons across radically different class/horse pools.
    matrix=group(rows,lambda r:bucket_fp(r["favorite_market_share"])+" / "+bucket_field(r["field_size"]))
    result={
        "source_history":str(HIST.relative_to(ROOT)),
        "source_market":str(MARKET.relative_to(ROOT)),
        "history_sha256":hashlib.sha256(HIST.read_bytes()).hexdigest(),
        "market_sha256":hashlib.sha256(MARKET.read_bytes()).hexdigest(),
        "odds_basis":"POSTRACE_FINAL_DIAGNOSTIC_ONLY",
        "limitations":[
            "Final market-implied probability reconstructed from final odds; race-day preoff signal unavailable.",
            "Market-implied rank may differ from official popularity when odds tie.",
            "Race histories are already preselected by the original data pipeline; not necessarily all JRA races.",
            "Causal attribution is impossible from observational strata.",
            "Historical performance must not be evaluated using postrace final odds as forecast features."
        ],
        "joined":len(rows),"unjoined":dict(skips),"by_year_count":dict(years),
        "all":all_data,"by_year":byyear,"favorite_share_x_field":matrix,
        "example_nonfavorite_winners":sorted(
            (r for r in rows if not r["winner_is_favorite"]),
            key=lambda r:(r["winner_market_rank"],r["favorite_market_share"]),reverse=True)[:25]
    }
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    p=lambda r:"—" if r["nonfavorite_rate"] is None else f"{r['other_won']}/{r['n']} ({r['nonfavorite_rate']:.1%})"
    lines=["# JRA過去レース分析：1番人気以外が勝つレースの共通点","",
           "**対象は保存済みの2025〜2026年結果＋最終市場オッズの共通レース。最終オッズは事後分析だけに利用。**",
           f"突合成功：{len(rows)}R。対応できないデータ：{dict(skips)}。",
           f"全体：{p(all_data['overall'])}。",""]
    for year,v in byyear.items():
        lines.append(f"{year}年：{p(v['overall'])}。")
    for heading,key in (("1番人気の市場確率帯","favorite_market_share"),
                        ("1番人気と2番人気の市場確率差","favorite_vs_second_market_share_gap"),
                        ("出走頭数","field_size"),("競馬場","venue"),
                        ("勝った馬の過去出走数","winner_previous_starts")):
        lines+=["","## "+heading,"",
                "|条件|全年合計|2025年|2026年|","|---|---:|---:|---:|"]
        for k,v in all_data[key].items():
            lines.append("|"+k+"|"+p(v)+"|"+
                         p(byyear.get("2025",{}).get(key,{}).get(k,{"n":0,"nonfavorite_rate":None}))+"|"+
                         p(byyear.get("2026",{}).get(key,{}).get(k,{"n":0,"nonfavorite_rate":None}))+"|")
    lines+=["","## 1番人気市場確率×出走頭数","",
            "|組合せ|1番人気以外の勝利|","|---|---:|"]
    for k,v in matrix.items():
        lines.append(f"|{k}|{p(v)}|")
    lines+=["","## 注意",""]+["- "+x for x in result["limitations"]]
    DOC.write_text("\n".join(lines)+"\n")
    print(json.dumps({"joined":len(rows),"unjoined":dict(skips),
        "by_year_count":dict(years),"favorite_share":all_data["favorite_market_share"],
        "field":all_data["field_size"],"gap":all_data["favorite_vs_second_market_share_gap"]},ensure_ascii=False))

if __name__=="__main__":main()
