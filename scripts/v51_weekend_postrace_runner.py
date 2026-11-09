"""Same-race postoff evaluation of frozen v50/v51, conditional rank, calibration.

This is not an external JRA fetcher: official outcome original bytes, observed
timestamp and URL must be supplied and verified. Writes immutable audit only.
"""
import argparse
import json
import hashlib
from pathlib import Path
from scripts.capture_v50_bodyweight import raw, immutable_save
from scripts.evaluate_v50_v51_weight_pairs import evaluate
from scripts.v51_calibration_audit import metrics as calibration
from scripts.v51_conditional_rank_pair_evaluation import compare

def evaluate_bundle(archive_path,official_results_path,official_original_bytes,
                    output,*,rank_snapshots=None):
    archive,archive_sha=raw(archive_path)
    official,official_sha=raw(official_results_path)
    metadata=official.get("source_evidence")
    if not isinstance(metadata,dict) or not str(metadata.get("source_url","")).startswith("https://"):
        raise ValueError("official result provenance URL required")
    if not metadata.get("observed_at") or metadata["observed_at"]!=official.get("observed_at"):
        raise ValueError("result original observation and manifest time mismatch")
    expected=metadata.get("original_source_sha256")
    if not isinstance(expected,str) or len(expected)!=64:
        raise ValueError("official result source raw SHA256 required")
    if hashlib.sha256(Path(official_original_bytes).read_bytes()).hexdigest()!=expected:
        raise ValueError("official original result source bytes missing/tampered")
    joined=evaluate(archive,official)
    calib=calibration(archive,official)
    out={"schema":"jra-v50-v51-official-paired-weekend-bundle-v1",
         "status":"EVALUATED_GENUINE_SOURCE_REQUIRED_NO_PROMOTION",
         "frozen_archive_sha256":archive_sha,
         "official_result_manifest_sha256":official_sha,
         "official_original_source_sha256":expected,
         "official_source_url":metadata["source_url"],
         "evaluation":joined,"calibration":calib,
         "production_model":"v50","v51_promoted":False}
    if rank_snapshots:
        rank,ranksha=raw(rank_snapshots)
        out["conditional_rank"]={"source_sha256":ranksha,
            "evaluation":compare(archive,rank,official)}
    else:
        out["conditional_rank"]={"status":"NO_AUTHENTIC_PREOFF_LEARNED_RANK_SNAPSHOT"}
    dest=Path(output)
    saved=immutable_save(dest,out)
    return {"status":out["status"],"races":joined["evaluation_races"],
            "output":str(dest),"sha256":saved,
            "learned_rank_evaluated":bool(rank_snapshots)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--official-results",required=True)
    p.add_argument("--official-original-bytes",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--rank-snapshots")
    args=p.parse_args()
    print(json.dumps(evaluate_bundle(args.archive,args.official_results,
        args.official_original_bytes,args.output,rank_snapshots=args.rank_snapshots),
        ensure_ascii=False))
if __name__=="__main__":main()
