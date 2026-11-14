"""Validate live JRA racecards and source evidence before feature engineering."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def parse_ts(value):
    ts = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return ts


def validate(card):
    if card.get("schema") != "jra-v51-live-racecard-v1":
        raise ValueError("UNSUPPORTED_RACECARD_SCHEMA")
    asof = parse_ts(card["captured_at"])
    if asof > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise ValueError("FUTURE_CAPTURE_TIMESTAMP")
    url = card["source_url"]
    if not url.startswith("https://www.jra.go.jp/"):
        raise ValueError("OFFICIAL_JRA_SOURCE_REQUIRED")
    source_sha = card["source_sha256"]
    if len(source_sha) != 64 or any(c not in "0123456789abcdef" for c in source_sha):
        raise ValueError("SOURCE_SHA256_REQUIRED")
    races = card.get("races")
    if not isinstance(races, list) or not races:
        raise ValueError("NO_RACES")
    ids = set()
    for race in races:
        rid = race["race"]
        if rid in ids:
            raise ValueError("DUPLICATE_RACE")
        ids.add(rid)
        if parse_ts(race["race_off_at"]) <= asof:
            raise ValueError("RACECARD_NOT_PREOFF")
        runners = race.get("horses", [])
        if len(runners) < 3:
            raise ValueError("INCOMPLETE_RACE_FIELD")
        nums = set()
        horses = set()
        for runner in runners:
            n = runner["number"]
            hid = runner["horse_id"]
            if type(n) is not int or n < 1 or n in nums:
                raise ValueError("INVALID_RUNNER_NUMBER")
            if not isinstance(hid, str) or not hid.startswith("jra:") or hid in horses:
                raise ValueError("MISSING_OR_DUPLICATE_OFFICIAL_HORSE_ID")
            if not runner.get("name") or not runner.get("jockey_id"):
                raise ValueError("MISSING_RUNNER_OR_JOCKEY_ID")
            proof = runner.get("official_identity_proof")
            if not isinstance(proof, dict) or proof.get("horse_id") != hid or proof.get("horse_number") != n:
                raise ValueError("MISSING_OFFICIAL_IDENTITY_PROOF")
            if not str(proof.get("source_url", "")).startswith("https://www.jra.go.jp/"):
                raise ValueError("IDENTITY_PROOF_NOT_OFFICIAL")
            if parse_ts(proof["observed_at"]) > asof:
                raise ValueError("IDENTITY_PROOF_AFTER_ASOF")
            nums.add(n)
            horses.add(hid)
    return {"status": "RACECARD_VALIDATED", "races": len(races), "horses": sum(len(r["horses"]) for r in races)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--racecard", required=True)
    a = p.parse_args()
    print(json.dumps(validate(json.loads(Path(a.racecard).read_text(encoding="utf-8"))), ensure_ascii=False))
