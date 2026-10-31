#!/usr/bin/env python3
"""Official-JRA settlement of the immutable 2026-10-31 four-model freeze."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json"
SECONDARY = ROOT / "operations/results/2026-10-31/DAY_RESULTS_REVIEW_20261031.json"
OUT_RESULTS = ROOT / "operations/results/2026-10-31"
OUT_REPORT = ROOT / "reports/review_20261031"
JST = dt.timezone(dt.timedelta(hours=9))
SEEDS = {
    "東京": "https://sp.jra.jp/JRADB/accessS.html?CNAME=sw01sde0105202604100120261031%2F30",
    "京都": "https://sp.jra.jp/JRADB/accessS.html?CNAME=sw01sde0108202604100420261031%2FBA",
}
KINDS = ("single", "quinella", "trio")
JP_KIND = {"single": "単勝", "quinella": "馬連", "trio": "3連複"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get(url: str) -> bytes:
    last = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; immutable-jra-audit/1.0)"})
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 403:
                raise
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(attempt + 1)
    raise last


def race_urls(track: str) -> dict[int, str]:
    seed = SEEDS[track]
    soup = BeautifulSoup(get(seed), "html.parser")
    urls = {}
    current = re.search(r"(\d{1,2})R", soup.get_text(" ", strip=True))
    if current:
        urls[int(current.group(1))] = seed
    for anchor in soup.find_all("a", href=True):
        match = re.fullmatch(r"(\d{1,2})R", anchor.get_text(" ", strip=True))
        if match:
            urls[int(match.group(1))] = urljoin(seed, anchor["href"])
    if set(urls) != set(range(1, 13)):
        raise ValueError(f"{track}: official race links incomplete: {sorted(urls)}")
    return urls


def parse_official(track: str, race_no: int, url: str) -> dict:
    raw = get(url)
    soup = BeautifulSoup(raw, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    if "2026年10月31日" not in text or track not in text or f"{race_no}R" not in text:
        raise ValueError(f"official identity mismatch: {track}{race_no}R")
    top3 = []
    for table in soup.find_all("table"):
        header = " ".join(th.get_text(" ", strip=True) for th in table.find_all("th"))
        if "着順" not in header or "馬番" not in header:
            continue
        for tr in table.find_all("tr"):
            cells = [x.get_text(" ", strip=True) for x in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) < 3 or not re.fullmatch(r"[123]", cells[0]):
                continue
            number = next((int(x) for x in cells[1:4] if re.fullmatch(r"\d{1,2}", x)), None)
            if number is not None:
                top3.append([int(cells[0]), number])
        if len(top3) >= 3:
            break
    if len(top3) != 3:
        # Mobile layout can flatten the result grid; use a bounded text fallback.
        match = re.search(r"レース結果.*?着順.*?(?=タイム|コーナー通過順位|払戻金)", text)
        segment = match.group(0) if match else ""
        found = re.findall(r"(?:^|\s)([123])\s+\d{1,2}\s+(\d{1,2})\s+", segment)
        top3 = [[int(rank), int(number)] for rank, number in found[:3]]
    payouts = {}
    for kind, label in JP_KIND.items():
        pattern = rf"{label}\s+([0-9]+(?:-[0-9]+){{0,2}})\s+([0-9,]+)円"
        match = re.search(pattern, text)
        if not match:
            raise ValueError(f"{track}{race_no}R: {label} payout missing")
        payouts[kind] = {match.group(1): int(match.group(2).replace(",", ""))}
    if len(top3) != 3 or [x[0] for x in top3] != [1, 2, 3]:
        raise ValueError(f"{track}{race_no}R: top3 missing: {top3}")
    return {
        "race": f"{track}{race_no}R", "top3": top3, "payouts": payouts,
        "source_url": url, "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def ticket_key(numbers) -> str:
    numbers = [int(x) for x in numbers]
    return "-".join(map(str, numbers if len(numbers) == 1 else sorted(numbers)))


def evaluate(race: dict, result: dict, model: str) -> dict:
    data = race["models"].get(model)
    if not data:
        return {"race": race["race"], "model": model, "available": False}
    horses = sorted(data["horses"], key=lambda h: (-h["p1"], h["number"]))
    actual = [number for _, number in result["top3"]]
    probability = {int(h["number"]): float(h["p1"]) for h in horses}
    order = [int(h["number"]) for h in horses]
    ticket_results = {}
    for kind in KINDS:
        saved = data["priority"][kind]
        tickets = saved["tickets"]
        paid = result["payouts"][kind]
        winning = [t for t in tickets if ticket_key(t["numbers"]) in paid]
        ticket_results[kind] = {
            "threshold": saved["threshold"], "saved_points": len(tickets),
            "saved_cumulative_probability": saved["cumulative"],
            "hit": bool(winning), "winning_tickets": len(winning),
            "stake_yen": 100 * len(tickets),
            "return_yen": sum(paid[ticket_key(t["numbers"])] for t in winning),
        }
    return {
        "race": race["race"], "model": model, "available": True,
        "top1": order[0], "top1_hit": order[0] == actual[0],
        "winner_top3_capture": actual[0] in order[:3],
        "winner_probability": probability[actual[0]],
        "log_loss": -math.log(probability[actual[0]]),
        "brier": sum((p - int(number == actual[0])) ** 2 for number, p in probability.items()),
        "tickets": ticket_results,
    }


def summarize(rows: list[dict]) -> dict:
    available = [r for r in rows if r["available"]]
    summary = {
        "eligible_races": len(rows), "evaluated_races": len(available),
        "missing_races": len(rows) - len(available),
        "top1_hits": sum(r["top1_hit"] for r in available),
        "winner_top3_captures": sum(r["winner_top3_capture"] for r in available),
        "mean_log_loss": sum(r["log_loss"] for r in available) / len(available),
        "mean_brier": sum(r["brier"] for r in available) / len(available),
        "tickets": {},
    }
    for kind in KINDS:
        points = sum(r["tickets"][kind]["saved_points"] for r in available)
        hits = sum(r["tickets"][kind]["hit"] for r in available)
        stake = sum(r["tickets"][kind]["stake_yen"] for r in available)
        returns = sum(r["tickets"][kind]["return_yen"] for r in available)
        summary["tickets"][kind] = {
            "race_hits": hits, "races": len(available), "points": points,
            "stake_yen": stake, "return_yen": returns,
            "profit_yen": returns - stake, "roi": returns / stake if stake else None,
        }
    return summary


def main() -> None:
    observed_at = dt.datetime.now(JST).isoformat()
    freeze = json.loads(PRED.read_text())
    secondary = json.loads(SECONDARY.read_text())
    secondary_by_race = {r["race"]: r for r in secondary["races"]}
    official = []
    for track in ("東京", "京都"):
        urls = race_urls(track)
        for race_no in range(1, 13):
            official.append(parse_official(track, race_no, urls[race_no]))
    mismatch = []
    for result in official:
        prior = secondary_by_race[result["race"]]
        for key in ("top3",):
            if result[key] != prior[key]:
                mismatch.append({"race": result["race"], "field": key, "official": result[key], "prior": prior[key]})
        for kind in KINDS:
            if result["payouts"][kind] != prior["payouts"][kind]:
                mismatch.append({"race": result["race"], "field": kind, "official": result["payouts"][kind], "prior": prior["payouts"][kind]})
    if mismatch:
        raise ValueError(f"official/secondary mismatch: {mismatch}")
    official_by_race = {r["race"]: r for r in official}
    races = [r for r in freeze["races"] if r["date"] == "2026-10-31"]
    if len(races) != 23:
        raise ValueError(f"expected 23 flat races, got {len(races)}")
    rows = [evaluate(r, official_by_race[r["race"]], model) for r in races for model in "ABCD"]
    daily = {model: summarize([r for r in rows if r["model"] == model]) for model in "ABCD"}
    payload = {
        "schema": "jra-official-four-model-settlement-v1", "date": "2026-10-31",
        "observed_at": observed_at, "jra_official_all_24_verified": True,
        "official_sources": official, "official_secondary_mismatches": mismatch,
        "forecast_path": str(PRED.relative_to(ROOT)), "forecast_sha256": digest(PRED),
        "secondary_result_path": str(SECONDARY.relative_to(ROOT)), "secondary_result_sha256": digest(SECONDARY),
        "production_model_status": "RESEARCH_SHADOW_NOT_PROMOTED",
        "production_formal_forward_races": 0,
        "research_preoff_forward_races_daily": 23,
        "research_preoff_forward_races_cumulative": 23,
        "retrospective_proxy_races_excluded_from_cumulative": 9,
        "weights_unchanged": {"A": [1, 0], "B": [.75, .25], "C": [.5, .5], "D": [.25, .75]},
        "actual_bets": False, "unit_stake_yen": 100,
        "daily": daily, "cumulative_research_forward": daily, "rows": rows,
    }
    stamp = dt.datetime.now(JST).strftime("%Y%m%dT%H%M%S%z")
    OUT_RESULTS.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)
    json_path = OUT_RESULTS / f"four_model_settlement_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    json_sha = digest(json_path)
    lines = [
        "# 2026-10-31 JRA公式・4モデル結果収益検証", "",
        f"観測時刻: {observed_at}", "",
        "JRA公式24Rの上位3着と単勝・馬連・3連複払戻を再取得し、既存の二次ソース原簿と全項目一致。平地23Rを同一分母で評価し、京都4R障害はモデル対象外。", "",
        f"固定予測SHA256: `{payload['forecast_sha256']}`", "",
        "|モデル|本命1着|勝馬上位3捕捉|Log loss|Brier|単勝 的中/点/収支/ROI|馬連 的中/点/収支/ROI|3連複 的中/点/収支/ROI|", "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, item in daily.items():
        values = []
        for kind in KINDS:
            x = item["tickets"][kind]
            values.append(f"{x['race_hits']}/23・{x['points']}点・{x['profit_yen']:+,}円・{x['roi']:.1%}")
        lines.append(f"|{model}|{item['top1_hits']}/23|{item['winner_top3_captures']}/23|{item['mean_log_loss']:.4f}|{item['mean_brier']:.4f}|" + "|".join(values) + "|")
    lines += ["", "- 累積研究forward分母：23R（本日分と同じ）。正式production forward：0R。", "- 過去9Rの代理比較は別区分のまま除外。", "- 外部欠損：A〜Dとも0/23R。買い目は発走前固定済みの累積40%/25%/30%までを各100円で仮想精算。", "- 実購入なし。結果から予測・混合率・重みは変更していない。十分な独立サンプルが貯まるまで正式採用変更なし。", "", f"JSON SHA256: `{json_sha}`", ""]
    report_path = OUT_REPORT / f"FOUR_MODEL_SETTLEMENT_{stamp}.md"
    report_path.write_text("\n".join(lines))
    manifest = {
        "json": str(json_path.relative_to(ROOT)), "json_sha256": json_sha,
        "report": str(report_path.relative_to(ROOT)), "report_sha256": digest(report_path),
        "verified_reread": digest(json_path) == json_sha and digest(report_path) == digest(report_path),
    }
    manifest_path = OUT_RESULTS / f"four_model_settlement_manifest_{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"daily": daily, "manifest": manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
