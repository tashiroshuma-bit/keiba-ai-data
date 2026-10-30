#!/usr/bin/env python3
"""Freeze Oct 31 / Nov 1 2026 weekend research-shadow four-model forecasts.

This deliberately does not promote a production model.  It uses the same
career-total proxy used by the prior Oct 25 shadow, then compares an external
public index on an identical runner set. Missing or mismatched inputs fail
closed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "keiba_v48"))
from ranking_model import RankModel, NAMES  # noqa: E402

def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(JST)
MODEL = BASE / "keiba_v48/reports/exact_rank/model_lag7.json"
SELECTION = BASE / "keiba_v48/reports/exact_rank/selection_lag7.json"
DB_SHA = "5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc"
ACTIVE_SHA = "21a7a19490fe1cb7415b9c866e6e4f0ba8184962b0c3a62a2ee838ebd5933395"
WEIGHTS = {"A": (1.0, 0.0), "B": (.75, .25), "C": (.5, .5), "D": (.25, .75)}
THRESHOLDS = {"single": .40, "quinella": .25, "trio": .30}

MEETINGS = {
    "2026-10-31": {
        "東京": {"code": "26050410", "surface": ["dirt","turf","turf","dirt","turf","dirt","turf","dirt","dirt","turf","dirt","turf"]},
        "京都": {"code": "26080410", "surface": ["dirt","turf","turf","obstacle","turf","dirt","dirt","dirt","turf","dirt","turf","turf"]},
    },
    "2026-11-01": {
        "東京": {"code": "26050411", "surface": ["turf","dirt","turf","turf","turf","dirt","dirt","turf","turf","dirt","turf","dirt"]},
        "京都": {"code": "26080411", "surface": ["dirt","dirt","turf","obstacle","turf","dirt","dirt","turf","dirt","turf","turf","turf"]},
    },
}

PROGRAM = {
    "2026-10-31": "https://www.jra.go.jp/keiba/calendar2026/2026/10/1031.html",
    "2026-11-01": "https://www.jra.go.jp/keiba/calendar2026/2026/11/1101.html",
}

def get(url: str) -> bytes:
    last = None
    for attempt in range(4):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KeibaResearchFreeze/1.0)"})
            with urlopen(req, timeout=30) as response:
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(attempt + 1)
    raise last

def parse_internal_roster(date: str, track: str, code: str, race: int):
    url = "https://sports.yahoo.co.jp/keiba/race/achievement/all/" + code + f"{race:02d}"
    raw = get(url)
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True)
    jpdate = f"{date[:4]}年{int(date[5:7])}月{int(date[8:])}日"
    if jpdate not in text:
        raise ValueError("DATE_MISMATCH")
    horses = []
    for table in soup.select("table"):
        header = " ".join(x.get_text(" ", strip=True) for x in table.select("th"))
        if not ("馬番" in header and "馬名" in header and "全レース" in header):
            continue
        for tr in table.select("tr"):
            cells = [x.get_text(" ", strip=True) for x in tr.find_all("td", recursive=False)]
            if len(cells) < 5 or not re.fullmatch(r"\d+", cells[1]):
                continue
            rec = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", cells[4])
            if not rec:
                continue
            w, s, t, o = map(int, rec.groups())
            horses.append({"number": int(cells[1]), "name": cells[2], "starts": w+s+t+o, "wins": w, "seconds": s, "thirds": t})
        if horses:
            break
    if not horses:
        url = "https://sports.yahoo.co.jp/keiba/race/denma/" + code + f"{race:02d}"
        raw = get(url)
        soup = BeautifulSoup(raw, "html.parser")
        if jpdate not in soup.get_text(" ", strip=True):
            raise ValueError("DATE_MISMATCH_ROSTER")
        for table in soup.select("table"):
            header = " ".join(x.get_text(" ", strip=True) for x in table.select("th"))
            if not ("馬番" in header and "馬名" in header):
                continue
            for tr in table.select("tr"):
                cells = tr.find_all("td", recursive=False)
                if len(cells) < 3:
                    continue
                no = cells[1].get_text(" ", strip=True)
                if not no.isdigit():
                    continue
                a = cells[2].find("a")
                name = a.get_text(" ", strip=True) if a else cells[2].get_text(" ", strip=True).split(" ")[0]
                horses.append({"number": int(no), "name": name, "starts": 0, "wins": 0, "seconds": 0, "thirds": 0})
            if horses:
                break
    if not 3 <= len(horses) <= 18 or len({x["number"] for x in horses}) != len(horses):
        raise ValueError(f"FIELD_INCOMPLETE_{len(horses)}")
    return horses, url, hashlib.sha256(raw).hexdigest()

def load_model():
    selected = json.loads(SELECTION.read_text())
    if sha(MODEL) != selected["model_sha256"]:
        raise ValueError("MODEL_SELECTION_SHA_MISMATCH")
    return RankModel.from_dict(json.loads(MODEL.read_text())), sha(MODEL)

def internal_probabilities(model, horses, track, surface):
    ix = {name: i for i, name in enumerate(NAMES)}
    features = []
    for horse in horses:
        values = model.mean.tolist()
        starts = horse["starts"]
        updates = {
            "ability": (horse["wins"] + 1) / (starts + 4),
            "recent_quality": (horse["wins"] + horse["seconds"] + horse["thirds"] + 1) / (starts + 2),
            "history_log": math.log1p(starts) / 5,
            "horse_identity_missing": 1, "jockey_identity_missing": 1, "age_missing": 1,
        }
        for name, value in updates.items():
            if name in ix:
                values[ix[name]] = value
        features.append({"values": values, "group": f"{track}/{surface}", "cutoff_timestamp": NOW.isoformat()})
    p, _ = model.predict(features)
    values = [float(x) for x in p[:, 0]]
    total = sum(values)
    return [x / total for x in values]

def external_listing():
    raw = get("https://muryou-keiba-ai.jp/predict/")
    soup = BeautifulSoup(raw, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        label = " ".join(a.get_text(" ", strip=True).split())
        m = re.search(r"(東京|京都)\s+(10月31日|11月1日)\s+(\d{1,2})R", label)
        if not m:
            continue
        date = "2026-10-31" if m.group(2) == "10月31日" else "2026-11-01"
        url = urljoin("https://muryou-keiba-ai.jp", a["href"])
        if url.startswith("https://muryou-keiba-ai.jp/predict/2026/"):
            found[(date, m.group(1), int(m.group(3)))] = url
    return found, hashlib.sha256(raw).hexdigest()

def parse_external(url):
    raw = get(url)
    soup = BeautifulSoup(raw, "html.parser")
    updated = None
    m = re.search(r"競馬予想の更新日：\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2})時\s*(\d{1,2})分", soup.get_text(" ", strip=True))
    if m:
        updated = dt.datetime(*map(int, m.groups()), tzinfo=JST).isoformat()
    rows = []
    for table in soup.select("table"):
        header = " ".join(x.get_text(" ", strip=True) for x in table.select("th"))
        if "AI予想" not in header:
            continue
        for tr in table.select("tr"):
            cells = [x.get_text(" ", strip=True) for x in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) < 4 or not cells[0].strip().isdigit():
                continue
            score = re.search(r"(\d+(?:\.\d+)?)", cells[-1])
            if score:
                raw_name = re.sub(r"(?:軸|紐|穴|消|◎|○|▲|△|☆)+.*$", "", cells[1]).strip()
                rows.append({"number": int(cells[0]), "name_raw": raw_name, "index": float(score.group(1)), "mark_raw": cells[-1]})
        if rows:
            break
    if not rows:
        raise ValueError("EXTERNAL_TABLE_MISSING")
    return rows, updated, hashlib.sha256(raw).hexdigest()

def softmax(values, temperature=20.0):
    mx = max(values)
    ex = [math.exp((x - mx) / temperature) for x in values]
    total = sum(ex)
    return [x / total for x in ex]

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
    numbers = [h["number"] for h in horses]
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

def main():
    model, model_sha = load_model()
    ext_pages, listing_sha = external_listing()
    commit = "${GITHUB_SHA}" if "${GITHUB_SHA}" != "$" + "{GITHUB_SHA}" else None
    all_summary = []
    for date, tracks in MEETINGS.items():
        races, failures = [], []
        for track, meta in tracks.items():
            for race in range(1, 13):
                surface = meta["surface"][race - 1]
                if surface == "obstacle":
                    failures.append({"track": track, "race": race, "reason": "OBSTACLE_OUT_OF_MODEL_DOMAIN"})
                    continue
                try:
                    horses, roster_url, roster_sha = parse_internal_roster(date, track, meta["code"], race)
                    p_internal = internal_probabilities(model, horses, track, surface)
                    key = (date, track, race)
                    if key not in ext_pages:
                        raise ValueError("EXTERNAL_PAGE_NOT_FOUND")
                    ext_rows, page_updated, ext_sha = parse_external(ext_pages[key])
                    by_no = {x["number"]: x for x in ext_rows}
                    if set(by_no) != {h["number"] for h in horses}:
                        raise ValueError("EXTERNAL_ROSTER_MISMATCH")
                    p_external = softmax([by_no[h["number"]]["index"] for h in horses])
                    models = {}
                    for label, (wi, we) in WEIGHTS.items():
                        mixed = [wi * a + we * b for a, b in zip(p_internal, p_external)]
                        models[label] = calculate_model(horses, mixed)
                    races.append({
                        "race": f"{track}{race}R", "track": track, "race_number": race, "surface": surface,
                        "runner_count": len(horses), "roster_source": roster_url, "roster_sha256": roster_sha,
                        "external_source": ext_pages[key], "external_sha256": ext_sha, "external_page_updated_at": page_updated,
                        "external_indices": ext_rows, "models": models,
                    })
                    print("OK", date, track, race, len(horses), flush=True)
                except Exception as exc:
                    failures.append({"track": track, "race": race, "reason": str(exc)})
                    print("FAIL", date, track, race, exc, flush=True)
        payload = {
            "schema": "keiba-weekend-four-model-research-freeze-v1", "date": date,
            "captured_at": NOW.isoformat(), "status": "RESEARCH_SHADOW_NOT_FORMAL_PREDICTION",
            "program_source": PROGRAM[date], "official_full_card_independently_replayed": False,
            "canonical_db": {"version": 10, "size_bytes": 322121728, "sha256_expected": DB_SHA, "sha256_observed_outside_action": DB_SHA},
            "active_model": {"sha256": ACTIVE_SHA, "strict_production_validated": False, "live_bet_generation": False, "changed": False},
            "research_model_sha256": model_sha, "external_listing_sha256": listing_sha,
            "weights": WEIGHTS, "external_temperature": 20, "placing_approximation": "Plackett-Luce",
            "ticket_thresholds": THRESHOLDS, "per_race_budget_yen_max": 10000, "actual_purchase": False,
            "covered_flat_races": len(races), "failures": failures, "races": races,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        payload_sha = hashlib.sha256(raw.encode()).hexdigest()
        outdir = BASE / "operations/predictions" / date
        outdir.mkdir(parents=True, exist_ok=True)
        stamp = NOW.strftime("%Y%m%dT%H%M%S%z")
        json_path = outdir / f"preoff_{stamp}.json"
        json_path.write_text(raw, encoding="utf-8")
        top = sorted(races, key=lambda r: -r["models"]["A"]["horses"][0]["p1"])[:5]
        graded = [r for r in races if (date == "2026-10-31" and r["race"] == "京都11R") or (date == "2026-11-01" and r["race"] == "東京11R")]
        lines = [f"# {date} JRA平地4モデル前日研究予測", "", f"固定時刻: {NOW.isoformat()}", "", "正式モデルではなく、通算成績代理特徴量による研究シャドー。公式全出馬表の独立再現ゲートは未通過。", "", f"対象 {len(races)}R／未算出・除外 {len(failures)}R。入力JSON SHA256 `{payload_sha}`。", "", "## 上位5レース＋重賞", ""]
        for r in top + [x for x in graded if x not in top]:
            lines += [f"### {r['race']}", "", "|方式|◎|p1|○|▲|☆|△|順序|単/馬連/3連複|", "|---|---|---:|---|---|---|---|---|---:|"]
            for label in WEIGHTS:
                m = r["models"][label]; h = m["horses"][0]; marks = m["marks"]
                lines.append(f"|{label}|{marks.get('◎')} {h['name']}|{h['p1']:.2%}|{marks.get('○')}|{marks.get('▲')}|{marks.get('☆')}|{marks.get('△')}|{'→'.join(map(str,m['ordered_top3']))}|{m['priority']['single']['count']}/{m['priority']['quinella']['count']}/{m['priority']['trio']['count']}|")
            lines += ["", "研究用買い目金額: 0円（発走前オッズ欠損・未校正。1レース最大1万円を無理に使用しない）", ""]
        if failures:
            lines += ["## 未算出・除外", "", "```json", json.dumps(failures, ensure_ascii=False, indent=2), "```", ""]
        report_path = outdir / f"REPORT_{stamp}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        # Re-read verification and immutable sidecar.
        if hashlib.sha256(json_path.read_bytes()).hexdigest() != payload_sha:
            raise RuntimeError("SAVED_JSON_REREAD_SHA_MISMATCH")
        manifest = {"json": str(json_path.relative_to(BASE)), "json_sha256": payload_sha, "report": str(report_path.relative_to(BASE)), "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(), "verified_reread": True}
        (outdir / f"freeze_manifest_{stamp}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        all_summary.append(manifest)
    print(json.dumps(all_summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
