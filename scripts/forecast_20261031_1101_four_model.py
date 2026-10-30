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
from urllib.error import HTTPError

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
THRESHOLDS = {"single": .80, "quinella": .50, "trio": .60, "wide": .50}

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

JRA_MOBILE_SEEDS = {
    ("2026-10-31", "東京"): "https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0105202604100120261031%2F01",
    ("2026-10-31", "京都"): "https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0108202604100120261031%2FDF",
    ("2026-11-01", "東京"): "https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0105202604110120261101%2FE1",
    ("2026-11-01", "京都"): "https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0108202604110120261101%2FBF",
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
        except HTTPError as exc:
            if exc.code == 403:
                raise
            last = exc
            time.sleep(attempt + 1)
        except Exception as exc:
            last = exc
            time.sleep(attempt + 1)
    raise last

def official_race_urls(date: str, track: str):
    """Resolve the 12 race URLs from JRA's official mobile meeting page."""
    seed = JRA_MOBILE_SEEDS[(date, track)]
    raw = get(seed)
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True)
    jpdate = f"{date[:4]}年{int(date[5:7])}月{int(date[8:])}日"
    if jpdate not in text or track not in text:
        raise ValueError("JRA_SEED_IDENTITY_MISMATCH")
    found = {1: seed}
    for anchor in soup.find_all("a", href=True):
        match = re.fullmatch(r"(\d{1,2})R", anchor.get_text(" ", strip=True))
        if match:
            found[int(match.group(1))] = urljoin(seed, anchor["href"])
    if set(found) != set(range(1, 13)):
        raise ValueError(f"JRA_RACE_LINKS_INCOMPLETE_{sorted(found)}")
    return found, hashlib.sha256(raw).hexdigest()

def row_number_and_frame(cells, horse_cell):
    # rowspan means the second horse in a frame has no frame cell.
    explicit = next((c for c in cells if "uban" in c.get("class", [])), None)
    if explicit is not None:
        value = explicit.get_text(" ", strip=True)
        frame_cell = next((c for c in cells if "wban" in c.get("class", [])), None)
        f = frame_cell.get_text(" ", strip=True) if frame_cell else ""
        m = re.search(r"\d{1,2}", value)
        return int(m[0]) if m else None, int(f) if f.isdigit() else None
    left = cells[:horse_cell]
    values = []
    for cell in left:
        value = cell.get_text(" ", strip=True)
        if re.fullmatch(r"\d{1,2}", value):
            values.append(int(value))
    if not values or not 1 <= values[-1] <= 18:
        return None, None
    return values[-1], values[-2] if len(values) > 1 else None


def validate_complete_field(horses, allow_unnumbered=False):
    numbers = [h["number"] for h in horses]
    if len({h["name"] for h in horses}) != len(horses):
        raise ValueError("DUPLICATE_RUNNER_NAME")
    if allow_unnumbered and numbers and all(n is None for n in numbers):
        if not 3 <= len(numbers) <= 18:
            raise ValueError("UNNUMBERED_HEADCOUNT_INVALID")
        return
    if any(n is None for n in numbers):
        raise ValueError("HORSE_NUMBERS_NOT_YET_PUBLISHED:"+repr([(h["name"],h["number"]) for h in horses]))
    if not 3 <= len(numbers) <= 18 or len(set(numbers)) != len(numbers):
        raise ValueError(f"FIELD_DUPLICATE_OR_INCOMPLETE_{numbers}")
    if set(numbers) != set(range(1, max(numbers) + 1)):
        raise ValueError(f"FIELD_NUMBER_GAPS_{numbers}")
    if any(not h["name"] or not 45 <= h.get("assigned_weight_kg", 55) <= 70 for h in horses):
        raise ValueError("FIELD_NAME_OR_WEIGHT_INVALID")


def parse_official_html(raw, date, track, race):
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True)
    jpdate = f"{date[:4]}年{int(date[5:7])}月{int(date[8:])}日"
    if jpdate not in text or track not in text or not re.search(rf"(?:{race}R|{race}レース)", text):
        raise ValueError("JRA_CARD_IDENTITY_MISMATCH")
    horses = []
    for table in soup.select("table"):
        header = " ".join(x.get_text(" ", strip=True) for x in table.select("th"))
        if not ("馬番" in header and "馬名" in header):
            continue
        candidate = []
        for tr in table.select("tr"):
            cells = tr.find_all(["td", "th"], recursive=False)
            horse_indexes = [i for i, c in enumerate(cells) if c.select_one("a[href*='accessU.html']")]
            if len(horse_indexes) != 1:
                continue
            hi = horse_indexes[0]
            link = cells[hi].select_one("a[href*='accessU.html']")
            number, frame = row_number_and_frame(cells, hi)
            record = re.search(r"[（(](\d+)\s*[,．.]\s*(\d+)\s*[,．.]\s*(\d+)\s*[,．.]\s*(\d+)[）)]", cells[hi].get_text(" ", strip=True))
            future_unassigned = date > NOW.date().isoformat() and number is None
            if record is None and not future_unassigned:
                raise ValueError(f"CAREER_RECORD_MISSING_{number}")
            w, second, third, other = map(int, record.groups()) if record else (None, None, None, None)
            horse_text = cells[hi].get_text(" ", strip=True)
            anchors = [a for a in cells[hi].find_all("a") if a.get_text(" ", strip=True)]
            # Mobile compact cards keep current jockey and weight inside td.uma.
            wm = re.search(r"[（(]((?:4[5-9]|[56]\d|70)(?:\.\d)?)[）)]", horse_text)
            if wm:
                assigned_weight = float(wm[1])
                jockey = anchors[1].get_text(" ", strip=True) if len(anchors)>1 else None
                trainer = anchors[2].get_text(" ", strip=True) if len(anchors)>2 else None
            else:
                weight_cell = next((c for c in cells[hi+1:] if re.search(r"(?:牡|牝|せん|セン|セ)\s*\d+", c.get_text(" ", strip=True)) and re.search(r"\d{2}(?:\.\d)?\s*kg", c.get_text(" ", strip=True))), None)
                if weight_cell is None:
                    raise ValueError(f"ASSIGNED_WEIGHT_CELL_MISSING_{number}")
                wm = re.search(r"(?<!\d)(\d{2}(?:\.\d)?)\s*kg", weight_cell.get_text(" ", strip=True))
                assigned_weight = float(wm[1]); ja=weight_cell.find_all("a")
                jockey = ja[-1].get_text(" ", strip=True) if ja else None
                trainer = anchors[-1].get_text(" ", strip=True) if len(anchors)>1 else None
            candidate.append({"number": number, "frame": frame, "name": link.get_text(" ", strip=True),
                              "jockey": jockey, "trainer": trainer, "assigned_weight_kg": assigned_weight,
                              "career_missing": record is None,
                              "starts": w + second + third + other if record else None, "wins": w, "seconds": second, "thirds": third})
        if candidate:
            horses = candidate
            break
    validate_complete_field(horses, allow_unnumbered=date > NOW.date().isoformat())
    # Headers precede horse histories. Do not mistake a past race's going for today's.
    prefix = text[:text.index(horses[0]["name"])][-2500:]
    weather_match = re.search(r"天候\s*[:：]?\s*(晴|曇|雨|小雨|雪|小雪)", prefix)
    going_match = re.search(r"(?:芝|ダート)\s*[:：]?\s*(不良|稍重|良|重)", prefix)
    course = re.search(r"コース[：:]?\s*[\d,，]+\s*メートル\s*[（(]([^）)]+)", prefix)
    if not course:
        raise ValueError("CURRENT_COURSE_MISSING:"+prefix[-500:])
    surface = "dirt" if "ダート" in course[1] else "turf" if "芝" in course[1] else None
    off = re.search(r"発走時刻[：:]?\s*(\d{1,2})時(\d{1,2})分", prefix)
    if surface is None or off is None:
        raise ValueError("CURRENT_SURFACE_OR_OFF_TIME_MISSING:"+prefix[-500:])
    off_at = dt.datetime.fromisoformat(date).replace(hour=int(off[1]), minute=int(off[2]), tzinfo=JST)
    return horses, weather_match[1] if weather_match else None, going_match[1] if going_match else None, surface, off_at.isoformat()


def parse_official_roster(url, date, track, race):
    raw = get(url)
    horses, weather, going, surface, off_at = parse_official_html(raw, date, track, race)
    return horses, hashlib.sha256(raw).hexdigest(), weather, going, surface, off_at


def parse_internal_roster(date, track, code, race):
    url = "https://sports.yahoo.co.jp/keiba/race/achievement/all/" + code + f"{race:02d}"
    raw = get(url)
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True)
    jpdate = f"{date[:4]}年{int(date[5:7])}月{int(date[8:])}日"
    if jpdate not in text or track not in text:
        raise ValueError("SECONDARY_DATE_TRACK_MISMATCH")
    horses = []
    for table in soup.select("table"):
        header = " ".join(x.get_text(" ", strip=True) for x in table.select("th"))
        if "馬番" not in header or "馬名" not in header or "全レース" not in header:
            continue
        for tr in table.select("tr"):
            cells = tr.find_all(["td", "th"], recursive=False)
            ix = next((i for i,c in enumerate(cells) if c.select_one("a[href*='/horse/']")), None)
            if ix is None:
                continue
            number, _ = row_number_and_frame(cells, ix)
            link = cells[ix].select_one("a[href*='/horse/']")
            rec = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)\.(\d+)(?!\d)", " ".join(c.get_text(" ", strip=True) for c in cells[ix+1:]))
            if rec is None:
                raise ValueError("SECONDARY_CAREER_MISSING")
            w,se,t,o=map(int,rec.groups())
            horses.append({"number":number,"name":link.get_text(" ",strip=True),"starts":w+se+t+o,"wins":w,"seconds":se,"thirds":t})
        if horses:
            break
    validate_complete_field(horses, allow_unnumbered=date > NOW.date().isoformat())
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
    # The public race pages for this weekend are sequential.  Populate all
    # expected pages, but parse_external still verifies date/track/race text so
    # a changed or incorrect URL fails closed instead of binding the wrong race.
    bases = {
        ("2026-10-31", "東京"): 25260,
        ("2026-10-31", "京都"): 25272,
        ("2026-11-01", "東京"): 25284,
        ("2026-11-01", "京都"): 25296,
    }
    for (date, track), base in bases.items():
        for race in range(1, 13):
            found.setdefault((date, track, race), f"https://muryou-keiba-ai.jp/predict/2026/10/29/{base + race}/")
    return found, hashlib.sha256(raw).hexdigest()

def parse_external(url, date, track, race):
    raw = get(url)
    soup = BeautifulSoup(raw, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    jpdate = f"{date[:4]}年{int(date[5:7])}月{int(date[8:])}日"
    if jpdate not in page_text or track not in page_text or f"{race}R" not in page_text:
        raise ValueError("EXTERNAL_PAGE_IDENTITY_MISMATCH")
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
            dom = tr.find_all(["th", "td"], recursive=False)
            cells = [x.get_text(" ", strip=True) for x in dom]
            if len(cells) < 4 or not cells[0].strip().isdigit():
                continue
            score = re.search(r"(\d+(?:\.\d+)?)", cells[-1])
            if score:
                links = [a.get_text(" ", strip=True) for a in dom[1].find_all("a") if a.get_text(" ", strip=True)]
                raw_name = links[0] if links else re.sub(r"(?:軸|紐|穴|消|◎|○|▲|△|☆)+.*$", "", cells[1]).strip()
                rows.append({"number": int(cells[0]), "name": raw_name, "index": float(score.group(1)), "mark_raw": cells[-1]})
        if rows:
            break
    if not rows:
        raise ValueError("EXTERNAL_TABLE_MISSING")
    if len({x["name"] for x in rows}) != len(rows):
        raise ValueError("EXTERNAL_DUPLICATE_NAMES")
    if any(x["number"] <= 0 for x in rows) and not all(x["number"] == 0 for x in rows):
        raise ValueError("EXTERNAL_PARTIAL_HORSE_NUMBERS")
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
    numbers = [h["number"] if h["number"] is not None else "馬番未定:"+h["name"] for h in horses]
    p2, p3, triples, pairs, trios = plackett_luce(p1)
    order = sorted(range(len(horses)), key=lambda i: (-p1[i], numbers[i]))
    exact = max(triples, key=triples.get)
    single = {(numbers[i],): p1[i] for i in range(len(horses))}
    pair_no = {tuple(sorted((numbers[i], numbers[j]))): p for (i, j), p in pairs.items()}
    trio_no = {tuple(sorted((numbers[i], numbers[j], numbers[k]))): p for (i, j, k), p in trios.items()}
    ranked = [{"number": numbers[i], "name": horses[i]["name"], "p1": p1[i], "p2": p2[i], "p3": p3[i]} for i in order]
    wide_no = {pair: 0.0 for pair in pair_no}
    for trio, probability in trio_no.items():
        for pair in itertools.combinations(trio, 2):
            wide_no[pair] += probability
    wide_tickets, union = [], 0.0
    uncovered = dict(trio_no)
    for pair, probability in sorted(wide_no.items(), key=lambda x: (-x[1], x[0])):
        hit_trios = [trio for trio in uncovered if all(n in trio for n in pair)]
        union += sum(uncovered.pop(trio) for trio in hit_trios)
        wide_tickets.append({"numbers":list(pair),"p":probability,"cumulative":union})
        if union >= THRESHOLDS["wide"]:
            break
    for column in (p1, p2, p3):
        if not all(math.isfinite(x) and 0 <= x <= 1 for x in column) or abs(sum(column)-1) > 1e-8:
            raise ValueError("INVALID_FULL_FIELD_PROBABILITY_MASS")
    return {
        "ordered_top3_probability": triples[exact],
        "marks": dict(zip(["◎","○","▲","☆","△"], [r["number"] for r in ranked[:5]])),
        "ordered_top3": [numbers[i] for i in exact], "horses": ranked,
        "priority": {"single": threshold(single, THRESHOLDS["single"]), "quinella": threshold(pair_no, THRESHOLDS["quinella"]), "trio": threshold(trio_no, THRESHOLDS["trio"]), "wide": {"threshold": THRESHOLDS["wide"], "count":len(wide_tickets), "cumulative":union, "tickets":wide_tickets}},
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
            try:
                official_urls, official_seed_sha = official_race_urls(date, track)
            except Exception as exc:
                official_urls, official_seed_sha = {}, None
                failures.append({"track": track, "race": None, "reason": f"JRA_MEETING_UNAVAILABLE:{exc}"})
            for race in range(1, 13):
                surface = meta["surface"][race - 1]
                if surface == "obstacle":
                    failures.append({"track": track, "race": race, "reason": "OBSTACLE_OUT_OF_MODEL_DOMAIN"})
                    continue
                try:
                    key = (date, track, race)
                    ext_rows = page_updated = ext_sha = None
                    ext_error = None
                    try:
                        if key not in ext_pages:
                            raise ValueError("EXTERNAL_PAGE_NOT_FOUND")
                        ext_rows, page_updated, ext_sha = parse_external(ext_pages[key], date, track, race)
                    except Exception as exc:
                        ext_error = str(exc)
                    roster_method = "JRA_OFFICIAL_CARD_CAREER_TOTALS_PROXY"
                    weather = going = None
                    try:
                        roster_url = official_urls[race]
                        horses, roster_sha, weather, going, surface, off_at = parse_official_roster(roster_url, date, track, race)
                    except Exception as roster_exc:
                        raise ValueError(f"OFFICIAL_ROSTER_UNAVAILABLE:{roster_exc}")
                    secondary, secondary_url, secondary_sha = parse_internal_roster(date, track, meta["code"], race)
                    norm = lambda name: re.sub(r"[\s　]", "", name)
                    official_names={norm(h["name"]) for h in horses}
                    if official_names != {norm(h["name"]) for h in secondary}:
                        raise ValueError("INDEPENDENT_FULL_ROSTER_NAME_MISMATCH")
                    numbered=all(h["number"] is not None for h in horses)
                    if numbered and {h["number"]:norm(h["name"]) for h in horses} != {h["number"]:norm(h["name"]) for h in secondary}:
                        raise ValueError("INDEPENDENT_FULL_ROSTER_NUMBER_MISMATCH")
                    secondary_by_name={norm(h["name"]):h for h in secondary}
                    for horse in horses:
                        if horse.get("career_missing"):
                            for stat in ("starts","wins","seconds","thirds"):
                                horse[stat]=secondary_by_name[norm(horse["name"])][stat]
                            horse["career_source"]=secondary_url
                    p_internal = internal_probabilities(model, horses, track, surface)
                    models = {"A": calculate_model(horses, p_internal)}
                    if not ext_rows:
                        models.update({label: None for label in ("B", "C", "D")})
                        external_indices = None
                    else:
                        by_name = {norm(x["name"]): x for x in ext_rows}
                        if set(by_name) != official_names or (numbered and any(by_name[norm(h["name"])]["number"] != h["number"] for h in horses)):
                            ext_error = "EXTERNAL_ROSTER_MISMATCH"
                            models.update({label: None for label in ("B", "C", "D")})
                            external_indices = None
                        else:
                            p_external = softmax([by_name[norm(h["name"])]["index"] for h in horses])
                            for label, (wi, we) in WEIGHTS.items():
                                if label == "A":
                                    continue
                                mixed = [wi * a + we * b for a, b in zip(p_internal, p_external)]
                                models[label] = calculate_model(horses, mixed)
                            external_indices = ext_rows
                    races.append({
                        "race": f"{track}{race}R", "track": track, "race_number": race, "surface": surface,
                        "runner_count": len(horses), "roster_source": roster_url, "roster_sha256": roster_sha, "roster_method": roster_method,
                        "jra_meeting_seed_sha256": official_seed_sha, "weather_observed": weather, "going_observed": going,
                        "runners": horses, "horse_numbers_published": numbered, "off_at": off_at, "captured_before_off": NOW < dt.datetime.fromisoformat(off_at),
                        "independent_roster_source": secondary_url, "independent_roster_sha256": secondary_sha,
                        "external_source": ext_pages.get(key), "external_sha256": ext_sha, "external_page_updated_at": page_updated,
                        "external_error": ext_error, "external_indices": external_indices, "models": models,
                    })
                    print("OK", date, track, race, len(horses), flush=True)
                except Exception as exc:
                    failures.append({"track": track, "race": race, "reason": str(exc)})
                    print("FAIL", date, track, race, exc, flush=True)
        input_snapshot = {
            "captured_at": NOW.isoformat(), "program_source": PROGRAM[date],
            "races": [{
                "race": r["race"], "roster_sha256": r["roster_sha256"], "runners": r["runners"],
                "weather": r["weather_observed"], "going": r["going_observed"],
                "external_sha256": r["external_sha256"], "external_indices": r["external_indices"],
            } for r in races],
        }
        input_sha = hashlib.sha256(json.dumps(input_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        official_covered = sum(1 for r in races if r["roster_method"].startswith("JRA_OFFICIAL"))
        payload = {
            "schema": "keiba-weekend-four-model-research-freeze-v1", "date": date,
            "captured_at": NOW.isoformat(), "status": "RESEARCH_SHADOW_NOT_FORMAL_PREDICTION",
            "program_source": PROGRAM[date], "official_full_card_independently_replayed": official_covered == 23,
            "canonical_db": {"version": 10, "size_bytes": 322121728, "sha256_expected": DB_SHA, "sha256_observed_this_run": None},
            "active_model": {"sha256": ACTIVE_SHA, "strict_production_validated": False, "live_bet_generation": False, "changed": False},
            "research_model_sha256": model_sha, "external_listing_sha256": listing_sha,
            "input_snapshot_sha256": input_sha,
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
        gate_text = "公式全出馬表を再読込確認済み" if official_covered == 23 else f"公式出馬表確認 {official_covered}/23R（未通過）"
        lines = [f"# {date} JRA平地4モデル前日研究予測", "", f"固定時刻: {NOW.isoformat()}", "", f"正式モデルではなく、通算成績代理特徴量による研究シャドー。{gate_text}。", "", f"対象 {len(races)}R／未算出・除外 {len(failures)}R。入力SHA256 `{input_sha}`、予測JSON SHA256 `{payload_sha}`、モデルSHA256 `{model_sha}`。", "", "## 上位5レース＋重賞", ""]
        lines += ["## 全レース一覧（モデル内確率・実測的中率ではありません）", "", "|レース|頭数|A本命|単勝1点|馬連1点|ワイド1点|3連複1点|B/C/D|", "|---|---:|---|---:|---:|---:|---:|---|"]
        for r in races:
            m=r["models"]["A"]; h=m["horses"][0]; pr=m["priority"]
            availability="/".join("計算済" if r["models"].get(label) else "欠損" for label in ("B","C","D"))
            lines.append(f"|{r['race']}|{r['runner_count']}|{h['number']} {h['name']}|{h['p1']:.2%}|{pr['quinella']['tickets'][0]['p']:.2%}|{pr['wide']['tickets'][0]['p']:.2%}|{pr['trio']['tickets'][0]['p']:.2%}|{availability}|")
        lines += ["", "## ベスト5・重賞の全優先組合せ", "", "単勝累積80%、馬連50%、ワイドの少なくとも1点50%、3連複60%まで。ワイドの重複的中は和集合で計算。未校正の研究参考値。", ""]
        for r in top + [x for x in graded if x not in top]:
            lines += (["", "馬番未発表：馬名での暫定比較。番号による買い目は未確定。", ""] if not r.get("horse_numbers_published", True) else [])
            lines += [f"### {r['race']}", "", "|方式|◎|p1|○|▲|☆|△|順序|単/馬連/3連複|", "|---|---|---:|---|---|---|---|---|---:|"]
            for label in WEIGHTS:
                m = r["models"][label]
                if m is None:
                    lines.append(f"|{label}|未算出|—|—|—|—|—|—|—|")
                    continue
                h = m["horses"][0]; marks = m["marks"]
                lines.append(f"|{label}|{marks.get('◎')} {h['name']}|{h['p1']:.2%}|{marks.get('○')}|{marks.get('▲')}|{marks.get('☆')}|{marks.get('△')}|{'→'.join(map(str,m['ordered_top3']))}|{m['priority']['single']['count']}/{m['priority']['quinella']['count']}/{m['priority']['trio']['count']}|")
            for label in WEIGHTS:
                m=r["models"].get(label)
                if m is None:
                    continue
                lines += ["", f"#### {label}：全優先組合せ", "", "|券種|組合せ|個別確率|累積確率|", "|---|---|---:|---:|"]
                for key,title in (("single","単勝"),("quinella","馬連"),("wide","ワイド"),("trio","3連複")):
                    for t in m["priority"][key]["tickets"]:
                        lines.append(f"|{title}|{'-'.join(map(str,t['numbers']))}|{t['p']:.2%}|{t['cumulative']:.2%}|")
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

