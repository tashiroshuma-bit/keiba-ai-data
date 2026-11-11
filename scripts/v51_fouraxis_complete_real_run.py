"""Single real-data V51 14-feature retrain + 2025 rank comparison runner.

Requires the exact canonical v12 SQLite and verified overlay *locally*.
No network downloads, no inferred data, no live prediction modifications.
A failure is an error, never an empty pseudo-result or a successful model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from scripts.v51_four_axis_canonical_coverage import run as source_coverage
from scripts.v51_four_axis_rank_residual_study import study as rank_study

EXPECTED_DB_SHA="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
EXPECTED_OVERLAY_SHA="5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea"
EXPECTED_DB_BYTES=362139648
EXPECTED_OVERLAY_BYTES=6254592

def digest(path):
    sha=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            sha.update(chunk)
    return sha.hexdigest()

def inspect_sqlite(path,sha256,bytes_expected):
    f=Path(path)
    if not f.is_file():
        raise FileNotFoundError("required source file is absent: "+f.name)
    if f.stat().st_size!=bytes_expected:
        raise ValueError(f.name+" bytes differ from vetted source")
    observed=digest(f)
    if observed!=sha256:
        raise ValueError(f.name+" SHA256 differs from vetted source")
    conn=sqlite3.connect(f.resolve().as_uri()+"?mode=ro",uri=True)
    try:
        check=conn.execute("PRAGMA quick_check").fetchone()[0]
        if check!="ok":
            raise ValueError(f.name+" SQLite quick_check failed")
    finally:
        conn.close()
    return {"sha256":observed,"bytes":f.stat().st_size,"sqlite_quick_check":"ok"}

def _pct(x):
    return f"{100*float(x):.3f}%"

def _printable(report):
    confirm=report["2025_late_confirmation"]
    year=report["2025_full_year_descriptive_in_sample_calibration"]
    hold=report["2026_frozen_audit_only"]
    o=confirm["original"];n=confirm["candidate"]
    p=confirm["podium_original"];q=confirm["podium_selected"]
    x=year["baseline"];y=year["selected_proposal"]
    b=hold["original_official_v51"];a=hold["selected_research_proposal_not_promoted"]
    bp=hold["podium_original"];ap=hold["podium_selected_proposal_not_promoted"]
    return (
      "# V51 新14特徴量・正本全期間の順位比較\n\n"
      "**研究結果。正式V51の係数・将来予測は変更していません。**\n\n"
      "| コホート | 現行V51 1着的中率 | 研究14特徴量候補 1着的中率 | "
      "現行Log Loss | 候補Log Loss |\n"
      "|---|---:|---:|---:|---:|\n"
      f"| 2025後期・独立確認 {o['races']}R | {_pct(o['top1_accuracy'])} | "
      f"{_pct(n['top1_accuracy'])} | {o['winner_logloss']:.6f} | {n['winner_logloss']:.6f} |\n"
      f"| 2025全期（温度は同年内適合） {x['races']}R | {_pct(x['top1_accuracy'])} | "
      f"{_pct(y['top1_accuracy'])} | {x['winner_logloss']:.6f} | {y['winner_logloss']:.6f} |\n"
      f"| 2026固定事後監査 {b['races']}R | {_pct(b['top1_accuracy'])} | "
      f"{_pct(a['top1_accuracy'])} | {b['winner_logloss']:.6f} | {a['winner_logloss']:.6f} |\n\n"
      "| コホート | 現行Brier | 候補Brier | 現行ECE | 候補ECE |\n"
      "|---|---:|---:|---:|---:|\n"
      f"| 2025後期 | {o['winner_brier']:.6f} | {n['winner_brier']:.6f} | "
      f"{_pct(o['ece_confidence'])} | {_pct(n['ece_confidence'])} |\n"
      f"| 2025全期（同年校正・参考） | {x['winner_brier']:.6f} | {y['winner_brier']:.6f} | "
      f"{_pct(x['ece_confidence'])} | {_pct(y['ece_confidence'])} |\n"
      f"| 2026監査 | {b['winner_brier']:.6f} | {a['winner_brier']:.6f} | "
      f"{_pct(b['ece_confidence'])} | {_pct(a['ece_confidence'])} |\n\n"
      "| 評価 | 現行順序3頭 | 候補順序3頭 | 現行順不同3頭 | 候補順不同3頭 |\n"
      "|---|---:|---:|---:|---:|\n"
      f"| 2025後期 | {p['ordered_exact_hits']}/{p['valid_unique_podium_races']} | "
      f"{q['ordered_exact_hits']}/{q['valid_unique_podium_races']} | "
      f"{p['unordered_exact_hits']}/{p['valid_unique_podium_races']} | "
      f"{q['unordered_exact_hits']}/{q['valid_unique_podium_races']} |\n"
      f"| 2026監査 | {bp['ordered_exact_hits']}/{bp['valid_unique_podium_races']} | "
      f"{ap['ordered_exact_hits']}/{ap['valid_unique_podium_races']} | "
      f"{bp['unordered_exact_hits']}/{bp['valid_unique_podium_races']} | "
      f"{ap['unordered_exact_hits']}/{ap['valid_unique_podium_races']} |\n\n"
      f"- 2025中期に選択した候補：`{report['chosen_on_2025_search_only']}`\n"
      f"- 2025後期の正式採用基準を通過：**{report['2025_late_confirmation']['strict_gate_pass']}**\n"
      "- Log Loss・Brier・ECEはJSONの同じコホート・同じレースから比較。\n"
      "- 2025全期は同期間で温度を合わせているため確率評価は独立した予測値ではない。\n"
      "- 2026データは候補選択に一切使用していないが、以前の研究で閲覧済み。\n"
      "- 過去年度のPDF初回公開時刻は全件実証されず、保守的な2暦日制限を使用。\n"
      "- 当該レース結果PDFの馬体重は当該レースの予測には使用していない。\n"
    )

def execute(db,overlay,history_script,model_path,output_dir):
    original=inspect_sqlite(db,EXPECTED_DB_SHA,EXPECTED_DB_BYTES)
    sidecar=inspect_sqlite(overlay,EXPECTED_OVERLAY_SHA,EXPECTED_OVERLAY_BYTES)
    target=Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("output folder must be empty; never overwrite past research")
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v51_real_fouraxis_",dir=target.parent) as t:
        temp=Path(t)
        coverage=source_coverage(db)
        sourcefile=temp/"v51_four_axis_source_coverage.json"
        sourcefile.write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        report=rank_study(db,overlay,history_script,model_path,temp)
        if report["source_db_sha256"]!=EXPECTED_DB_SHA or report["overlay_sha256"]!=EXPECTED_OVERLAY_SHA:
            raise ValueError("source drift across audit and training")
        if report["2025_splits"]["all_2025_races"]!=2925:
            raise ValueError("2025 expected 2925-race evaluation cohort changed")
        if report["2026_frozen_audit_only"]["original_official_v51"]["top1_hits"]!=603:
            raise ValueError("official prior-year baseline not reproduced")
        receipt={"schema":"jra-v51-fouraxis-authenticated-real-execution-v1",
           "status":"ACTUAL_SOURCE_TRAINED_AND_COMPARED",
           "official_model_changed":False,
           "source_canonical_v12":original,"review_overlay":sidecar,
           "2025_late_gate":report["2025_late_confirmation"]["strict_gate_pass"],
           "selected_research_candidate":report["chosen_on_2025_search_only"],
           "generated_outputs":["v51_four_axis_source_coverage.json",
             "v51_four_axis_2025_rank_research_report.json",
             "v51_four_axis_2025_research_proposal.json",
             "v51_four_axis_2025_rank_summary.md"]}
        (temp/"v51_four_axis_2025_rank_summary.md").write_text(_printable(report),encoding="utf-8")
        (temp/"v51_four_axis_run_receipt.json").write_text(
            json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        for f in temp.iterdir():
            os.replace(f,target/f.name)
    return receipt

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",required=True)
    parser.add_argument("--review-overlay",required=True)
    parser.add_argument("--historical-feature-script",required=True)
    parser.add_argument("--model",required=True)
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()
    receipt=execute(args.database,args.review_overlay,
                    args.historical_feature_script,args.model,args.output_dir)
    print(json.dumps(receipt,ensure_ascii=False))
if __name__=="__main__":
    main()
