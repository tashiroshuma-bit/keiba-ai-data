#!/usr/bin/env python3
"""Capture and compare pre-off public predictions from muryou-keiba-ai.jp.

Independent external signal only: never convert proprietary AI indices to
probabilities or blend into model odds without an out-of-sample calibration.
"""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

JST = timezone(timedelta(hours=9))
HOST = "muryou-keiba-ai.jp"

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.tables = []
        self.rows = []
        self.row = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.rows = []
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.row = []
        elif tag in ("th", "td") and self.in_row:
            self.in_cell = True
            self.parts = []

    def handle_data(self, data):
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.in_cell:
            self.row.append(" ".join("".join(self.parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False
        elif tag == "table" and self.in_table:
            self.tables.append(self.rows)
            self.in_table = False

def parse_prediction(html):
    parser = TableParser()
    parser.feed(html)
    for table in parser.tables:
        if not table or not any("AI予想" in cell for cell in table[0]):
            continue
        horses = []
        for row in table[1:]:
            if len(row) < 4 or not row[0].strip().isdigit():
                continue
            num = int(row[0].strip())
            # Last field is e.g. ◎78.4 / 消20.5; not a probability.
            match = re.search(r"(\d+(?:\.\d+)?)", row[-1])
            if not match:
                continue
            horses.append({
                "horse_number": num,
                "horse_name_and_jockey_raw": row[1],
                "popularity_odds_raw": row[2],
                "index": float(match.group(1)),
                "mark_raw": row[-1],
            })
        if horses:
            return horses
    raise ValueError("Prediction table missing or page format changed")

def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.username or parsed.password or parsed.port:
        raise ValueError("Only exact HTTPS host muryou-keiba-ai.jp is allowed")
    if not parsed.path.startswith("/predict/"):
        raise ValueError("A specific /predict/ race page is required")

def snapshot(url, asof, off, html=None):
    validate_url(url)
    if asof.tzinfo is None or off.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")
    if asof >= off - timedelta(minutes=5):
        raise ValueError("Snapshot must be at least 5 minutes before off")
    if html is None:
        req = Request(url, headers={"User-Agent": "keiba-ai-research/1.0 (public-reference)"})
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
    # The page's own update time can be later than the fetch time if cache or
    # source is inconsistent. This is not a safe pre-off snapshot.
    m = re.search(r"競馬予想の更新日：\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})時(\d{1,2})分", html)
    page_updated = None
    if m:
        page_updated = datetime(*map(int, m.groups()), tzinfo=JST)
        if page_updated > asof or page_updated >= off - timedelta(minutes=5):
            raise ValueError("Page update timestamp is after capture or too close to off")
    return {
        "status": "EXTERNAL_REFERENCE_ONLY_NOT_PROBABILITY",
        "url": url,
        "captured_at": asof.isoformat(),
        "off_at": off.isoformat(),
        "page_updated_at": page_updated.isoformat() if page_updated else None,
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "source": HOST,
        "model": "origin_ai_display",
        "horses": parse_prediction(html),
        "disclaimer": "External AI index is NOT a win probability; no automatic probability blending.",
    }

def compare(snapshot_data, internal_ranked):
    ext = snapshot_data["horses"]
    ext_rank = {r["horse_number"]: i + 1 for i, r in enumerate(sorted(ext, key=lambda r: -r["index"]))}
    internal = {int(r["number"]): i + 1 for i, r in enumerate(internal_ranked)}
    if set(ext_rank) != set(internal):
        return {"status": "ROSTER_MISMATCH", "external_only": sorted(set(ext_rank)-set(internal)), "internal_only": sorted(set(internal)-set(ext_rank))}
    diffs = [{"horse_number": n, "internal_rank": internal[n], "external_rank": ext_rank[n], "rank_delta": internal[n]-ext_rank[n]} for n in sorted(internal)]
    return {"status": "COMPARED_INDEPENDENTLY", "differences": diffs, "external_top3": [n for n,_ in sorted(ext_rank.items(),key=lambda kv:kv[1])[:3]], "internal_top3": [n for n,_ in sorted(internal.items(),key=lambda kv:kv[1])[:3]]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--off", required=True, help="ISO8601 local scheduled off time")
    p.add_argument("--out", required=True)
    p.add_argument("--internal-json", help="Existing all_races.json; optional")
    p.add_argument("--track", help="Required with --internal-json")
    p.add_argument("--race", type=int, help="Required with --internal-json")
    args = p.parse_args()
    captured = datetime.now(JST)
    data = snapshot(args.url, captured, datetime.fromisoformat(args.off))
    if args.internal_json:
        if not args.track or not args.race:
            p.error("--track and --race required with --internal-json")
        races = json.loads(Path(args.internal_json).read_text(encoding="utf-8"))["races"]
        matched = [r for r in races if r["track"] == args.track and r["race"] == args.race]
        if len(matched) != 1:
            raise ValueError("Internal race missing or ambiguous")
        data["comparison"] = compare(data, matched[0]["ranked"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": data["status"], "horses": len(data["horses"]), "out": str(out)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
