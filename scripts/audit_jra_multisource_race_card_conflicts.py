"""Audit cached/manual third-party race cardinality against official frozen JRA outcomes.

Never merge conflicting third-party records automatically. Report discrepancies,
and separate posted race results from historical pre-off snapshots.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JRA=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
OBS=ROOT/"operations/data_updates/multisource_20261108_manual_observations.json"
OUT=ROOT/"reports/v51/multisource_race_conflict_audit_20261108.json"
MD=ROOT/"reports/v51/multisource_race_conflict_audit_20261108.md"

def audit(official,observed):
    race_by={r["race"]:r for r in official["official"] if r.get("status")=="official_verified"}
    found=[]
    for o in observed["observations"]:
        race=race_by.get(o["race"])
        if not race:raise ValueError("no official JRA counterpart")
        if o.get("snapshot_phase") not in ("unverified_postrace_site_observation","proven_preoff"):
            raise ValueError("source phase missing")
        if o.get("official_results_comparability") is not True:
            state="NOT_COMPARABLE_PHASE"
        elif o["advertised_field_size"]!=race["headcount"]:
            state="QUARANTINE_FIELD_CONFLICT"
        else:state="FIELD_COUNT_MATCH_ONLY"
        found.append({"race":o["race"],"source":o["source_id"],
          "external_field_size":o["advertised_field_size"],
          "official_jra_field_size":race["headcount"],"state":state,
          "official_source":race["url"],"external_source":o["source_url"],
          "preoff_feature_eligible":state=="FIELD_COUNT_MATCH_ONLY" and
               o["snapshot_phase"]=="proven_preoff" and
               o.get("published_at") is not None and
               o.get("official_horse_ids_confirmed") is True,
          "caution":"count match alone does not prove runner identity or a pre-off snapshot"})
    return {"schema":"keiba-jra-multisource-race-card-conflict-v1",
      "official_races_verified":len(race_by),"external_observations":len(found),
      "conflicts":sum(x["state"]=="QUARANTINE_FIELD_CONFLICT" for x in found),
      "results":found,
      "no_direct_import_without_license_or_preoff_proof":True}

def main():
    d=audit(json.loads(JRA.read_text()),json.loads(OBS.read_text()))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
    rows=["# 外部出馬表とJRA公式結果の突合・隔離レポート","",
        "これは別サイトの公開ページに記載された頭数の比較であり、データ取得時点・出走取消などの違いがあり得る。",
        "特定サイトの誤りを断定せず、公式結果との差を手動確認対象として隔離する。","",
        "|対象|外部出馬表頭数|JRA公式結果頭数|処理|","|---|---:|---:|---|"]
    for x in d["results"]:
        rows.append(f"|{x['race']}|{x['external_field_size']}|{x['official_jra_field_size']}|{x['state']}|")
    rows+=["","公式ID・発走前の公開時刻を証明できないため、当該外部観測は予測用特徴量に使用しない。",""]
    MD.write_text("\n".join(rows))
    print(json.dumps({"external":d["external_observations"],"quarantined":d["conflicts"]},
                     ensure_ascii=False))
if __name__=="__main__":main()
