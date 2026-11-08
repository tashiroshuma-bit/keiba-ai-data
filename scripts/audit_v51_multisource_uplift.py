"""Measure real 5-source observation coverage and V51 uplift eligibility.

No synthetic data and no backtest is called an accuracy improvement without
matching full-field source observations and pre-off V50/V51 predictions.
"""
import argparse,collections,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"operations/data_updates/multisource_overlay_20261108.sqlite"
AUDIT=ROOT/"operations/data_updates/multisource_overlay_20261108_audit.json"
FROZEN=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
RESULTS=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
CANDIDATE=ROOT/"operations/prediction_policy/v51_candidate_fitted_research.json"
OUT=ROOT/"reports/v51/V51_MULTISOURCE_UPLIFT_AUDIT.json"
MD=ROOT/"reports/v51/V51_MULTISOURCE_UPLIFT_AUDIT.md"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def audit(db=DB,manifest=AUDIT,forecast=FROZEN,results=RESULTS):
    db=Path(db)
    saved=json.loads(Path(manifest).read_text())
    if sha(db)!=saved["overlay_sha256"] or db.stat().st_size!=saved["overlay_size_bytes"]:
        raise ValueError("overlay SHA256 / size differs from previously verified artifact")
    conn=sqlite3.connect(f"file:{db.resolve()}?mode=ro",uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("sqlite corrupt")
        if conn.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("foreign key violations")
        counts={
          "providers":conn.execute("SELECT count(*) FROM multi_source_registry").fetchone()[0],
          "official_race_checkpoints":conn.execute("SELECT count(*) FROM jra_official_race_checkpoint").fetchone()[0],
          "quarantined_conflicts":conn.execute("SELECT count(*) FROM external_race_quarantine").fetchone()[0],
          "observations":conn.execute("SELECT count(*) FROM multi_source_observation").fetchone()[0],
          "preoff_usable_observations":conn.execute("SELECT count(*) FROM multi_source_observation WHERE usable_for_v50_v51_preoff=1").fetchone()[0]}
        groups=dict(conn.execute("SELECT source_id, count(*) FROM multi_source_observation GROUP BY source_id").fetchall())
        byrace=dict(conn.execute("""SELECT official_race_id,count(distinct horse_number)
               FROM multi_source_observation
               WHERE usable_for_v50_v51_preoff=1 AND verified_jra_horse_id IS NOT NULL
                  AND published_at IS NOT NULL
               GROUP BY official_race_id""").fetchall())
    finally:conn.close()
    if counts!={"providers":5,"official_race_checkpoints":36,
                 "quarantined_conflicts":1,"observations":0,
                 "preoff_usable_observations":0}:
        # This fixed sample is the explicitly audited Nov8 overlay. Any
        # later changes require creating and verifying a new evidence manifest.
        raise ValueError("actual SQLite does not match the Nov8 verified cohort")
    frozen=json.loads(Path(forecast).read_text())
    truth=json.loads(Path(results).read_text())
    valid={r["race"] for r in truth["races"] if r["status"]=="evaluated"}
    rows=[r for r in frozen["races"] if r.get("date")=="2026-11-08" and r.get("status")=="abcd_reconnected"]
    eligible=0
    coverage=[]
    for r in rows:
        name=r["race"]
        n=len(r["models"]["C"]["horses"])
        f=byrace.get(name,0)
        coverage.append({"race":name,"runners":n,"proven_preoff_horse_count":f,
                         "result_verified":name in valid,
                         "complete_feature_coverage":f==n,
                         "has_frozen_same_asof_v51":False})
        eligible+=int(f==n and name in valid)
    v51=json.loads(CANDIDATE.read_text())
    if v51["production_enabled"] is not False:raise ValueError("v51 must remain off")
    return {"schema":"v51-multisource-real-data-uplift-audit-v1",
      "sqlite_sha256":sha(db),"integrity_check":"ok",
      "counts":counts,"by_provider":groups,
      "saved_abcd_research_predictions":len(rows),
      "official_results_paired":sum(r["result_verified"] for r in coverage),
      "complete_feature_races":eligible,
      "same_asof_frozen_v50_v51_pairs":0,
      "eligible_for_improvement_measurement":0,
      "observed_uplift":None,"cannot_estimate_uplift":True,
      "v51_old_2025_2026_research_holdouts":v51["holdouts"],
      "model_upgraded":False,"standard_version":"v50",
      "reasons":["0 new horse-level features in the verified overlay",
                 "no timestamp-verified full-field preoff horse data",
                 "no same-asof frozen v51 forecast for the existing races",
                 "official result summaries alone cannot serve as preoff predictors"],
      "coverage_by_race":coverage}

def write_report(result,out=OUT,md=MD):
    out=Path(out);md=Path(md)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    c=result["counts"]
    lines=["# V51：4サイト補助DBの実データ効果検証","",
      "判定：追加の馬別特徴量0件。V51の的中率改善は算定不能。正式v50維持。","",
      "|対象|実測|","|---|---:|",
      f"|提供元登録|{c['providers']}|",
      f"|JRA結果レース|{c['official_race_checkpoints']}|",
      f"|隔離不一致|{c['quarantined_conflicts']}|",
      f"|馬別特徴量|{c['observations']}|",
      f"|発走前として確認済みの特徴量|{c['preoff_usable_observations']}|",
      f"|発走前全頭特徴量が完備したレース|{result['complete_feature_races']}|",
      f"|同一時刻のv50/v51直接検証可能レース|{result['same_asof_frozen_v50_v51_pairs']}|",
      "","## 根拠と解釈","",
      "GitHub保存済みSQLiteのSHA256・全テーブル件数・整合性を直接再検査した。",
      "JRA公式のレース結果36Rは正しい教師ラベルであるが、血統・騎手・走破内容・調教の追加事前特徴量ではない。",
      "過去の研究V51候補は2025・2026の両年で全評価指標を改善していない。追加ソース0件を新学習成功と表現しない。",
      "利用権限がない他サイトの大量抽出・契約回避は実施しない。",
      "次に必要なのは使用許可と公開時刻を確認できる全出走馬の公式ID・事前特徴量・同一時刻のV50/V51凍結予測。",
      "",
      "## データの参照先","",
      "- operations/data_updates/multisource_overlay_20261108.sqlite",
      "- operations/data_updates/multisource_overlay_20261108_audit.json",
      "- operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json",
      "- operations/results/2026-11-08/v50_abcd_settlement.json",
      "- operations/prediction_policy/v51_candidate_fitted_research.json",
      ""]
    md.write_text("\n".join(lines)+"\n")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",default=str(DB))
    p.add_argument("--output",default=str(OUT))
    p.add_argument("--report",default=str(MD))
    args=p.parse_args()
    result=audit(db=args.database)
    write_report(result,args.output,args.report)
    print(json.dumps({"observations":result["counts"]["observations"],
      "usable":result["counts"]["preoff_usable_observations"],
      "paired":result["same_asof_frozen_v50_v51_pairs"],
      "uplift":result["observed_uplift"]},ensure_ascii=False))

if __name__=="__main__":main()
