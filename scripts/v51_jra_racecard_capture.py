"""Fetch and archive actual JRA preoff racecard; never synthesize identities.

A capture with missing official horse/jockey IDs is archived as INCOMPLETE
rather than passed to the V51 model. Original HTML and SHA are retained.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup


HORSE = re.compile(r"(?:pw01dud\d{2}|sj01ude00)(\d{10})/")
JOCKEY = re.compile(r"(?:pw04kmk|sw04kmk)(\d{6})/")
JRA_HOSTS = {"www.jra.go.jp", "jra.jp", "sp.jra.jp", "app.jra.jp"}


def official_link(href, base):
    link = urljoin(base, href)
    parts = urlparse(link)
    if parts.scheme != "https" or parts.hostname not in JRA_HOSTS:
        return None
    return link


def extract_ids(cell, base):
    horse_ids, jockey_ids = set(), set()
    for tag in cell.select("a[href], a[onclick]"):
        target = (tag.get("href", "") + " " + tag.get("onclick", ""))
        target = unquote(target)
        # JRA links may wrap CNAME in a URL query or a JavaScript action.
        horse_ids.update(HORSE.findall(target))
        jockey_ids.update(JOCKEY.findall(target))
    return horse_ids, jockey_ids


def capture(url, output, timeout=25):
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in JRA_HOSTS:
        raise ValueError("JRA_OFFICIAL_HTTPS_REQUIRED")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=(10, timeout), allow_redirects=False,
                            headers={"User-Agent": "KeibaResearch/1.0"})
    observed = dt.datetime.now(dt.timezone.utc).isoformat()
    meta = {"schema": "jra-v51-racecard-source-capture-v1", "url": url,
            "observed_at": observed, "http_status": response.status_code,
            "source_sha256": hashlib.sha256(response.content).hexdigest()}
    (output / "capture_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    if response.status_code in (401, 403, 429):
        raise PermissionError(f"OFFICIAL_SOURCE_REFUSED_{response.status_code}")
    if response.status_code != 200:
        raise RuntimeError(f"OFFICIAL_SOURCE_HTTP_{response.status_code}")
    (output / "source.html").write_bytes(response.content)
    soup = BeautifulSoup(response.content, "lxml")
    # Detect official racecard rows without claiming a complete field from
    # the mere presence of historical form lines.
    tables = soup.find_all("table")
    audit = []
    for table in tables:
        for tr in table.select("tr"):
            text = tr.get_text(" ", strip=True)
            horse_ids, jockey_ids = extract_ids(tr, url)
            if horse_ids or jockey_ids:
                audit.append({"text_excerpt": text[:180],
                              "horse_ids": sorted(horse_ids),
                              "jockey_ids": sorted(jockey_ids)})
    # Mobile JRA racecards use DIV-based runners and sj01ude00 / sw04kmk links.
    # Audit IDs at the anchor level as well as table rows; neither proves a full field.
    anchor_audit = []
    for a in soup.select("a[href],a[onclick]"):
        horses, jockeys = extract_ids(a, url)
        if horses or jockeys:
            anchor_audit.append({"label": a.get_text(" ", strip=True)[:100],
                                 "horse_ids": sorted(horses), "jockey_ids": sorted(jockeys)})
    result = {**meta, "status": "SOURCE_CAPTURED_FIELD_UNVERIFIED",
              "linked_rows": audit, "linked_row_count": len(audit),
              "linked_anchors": anchor_audit, "linked_anchor_count": len(anchor_audit),
              "verified_live_racecard": False,
              "note": "Official IDs alone do not establish field, off-time, number, or jockey linkage."}
    (output / "extraction_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = capture(args.url, args.output_dir)
    print(json.dumps({"status": result["status"], "linked_row_count": result["linked_row_count"]}, ensure_ascii=False))
