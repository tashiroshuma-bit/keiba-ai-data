"""V51 hard provenance gate for attributable pre-start horse/JRA features.

Official horse identity requires primary keyed evidence, never name similarity.
Historical publication timestamps must be externally evidenced and strictly
earlier than the target race; the annual JRA results archive PDF metadata is
NOT a proof that a result was public prior to its historical race.
"""
from __future__ import annotations
from datetime import datetime

def strict_time(value):
    v=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if v.tzinfo is None:
        raise ValueError("evidence timestamp needs timezone")
    return v

def check_historical_observation(source, *, race_off_at, forecast_asof):
    """Return verified evidence; never silently replace with estimated 2d lag."""
    for field in ("source_url","source_sha256","off_at","published_at","observed_at"):
        if not source.get(field):
            raise ValueError("missing historical provenance: "+field)
    if not str(source["source_url"]).startswith("https://"):
        raise ValueError("historical source must be HTTPS")
    digest=str(source["source_sha256"])
    if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise ValueError("source sha256 proof missing")
    if source.get("availability_basis") in ("assumed_calendar_day_lag_for_research_only",
                                            "postrace_pdf_metadata","unknown"):
        raise ValueError("unverified historical publication date")
    off=strict_time(race_off_at)
    asof=strict_time(forecast_asof)
    src_off=strict_time(source["off_at"])
    published=strict_time(source["published_at"])
    captured=strict_time(source["observed_at"])
    if not (src_off < published <= captured <= asof < off):
        raise ValueError("future label/publication/source or invalid asof ordering")
    return {"source_sha256":digest,"source_url":source["source_url"],
      "observation_at":captured.isoformat(),
      "historical_off_at":src_off.isoformat(),
      "publication_at":published.isoformat(),
      "asof":asof.isoformat(),"validated_asof":True}

def match_horse_identity(row,proof):
    """Only same official race ID, runner number and name with a primary ref."""
    for field in ("race_id","horse_number","horse_name"):
        if str(row.get(field,""))!=str(proof.get(field,"")):
            raise ValueError("horse race/number/name mismatch")
    if not proof.get("horse_id","").startswith("jra:"):
        raise ValueError("unverified JRA horse identity")
    if not str(proof.get("source_url","")).startswith("https://www.jra.go.jp/"):
        raise ValueError("official JRA source URL required")
    digest=str(proof.get("source_sha256",""))
    if len(digest)!=64:
        raise ValueError("official source SHA256 required")
    # DB's official evidence can be found after the historical race: IDs
    # themselves are intrinsic, but that does not prove their early discovery.
    # Downstream production must also check the observation_at against asof.
    if not proof.get("observed_at"):
        raise ValueError("identity proof observation time required")
    return proof["horse_id"]
