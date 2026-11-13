"""V52 candidate production checks (synthetic fixtures are NOT real JRA evidence)."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.v51_joint_pl_new_statistics import design_matrix
from scripts.v52_joint_pl_live_features import transform_live_features
from scripts.v52_real_promotion_gate import (
    check_promotion_evidence,staged_to_production_model,
    DB_SHA,OVERLAY_SHA,REPORT_SCHEMA,
)
from scripts.standard_v52_forecast import forecast,validate_extra_provenance
from scripts.jra_historical_horse_id_ablation import FEATURES
from scripts.v51_four_axis_historical_features import FEATURE_NAMES


def metrics(n,h):
    return {"races":n,"top1_hits":h,"top1_accuracy":h/n,
            "winner_logloss":2.0,"winner_brier":.86,
            "ece_confidence":.04,
            "conditional_second_logloss":2.1,
            "conditional_third_logloss":2.15}

def simulated_evidence():
    # Test fixture invented solely to check that the gate is fail closed.
    cfg={"ridge":.05,"coupling":.15,"half_life_days":365}
    name="joint_pl_r0.05_couple0.15_half365"
    podium=lambda n:{"n_valid":n,"ordered_hits":4,"unordered_hits":15}
    report={
        "schema":REPORT_SCHEMA,
        "sources":{"v12_sha256":DB_SHA,"review_sha256":OVERLAY_SHA},
        "cohorts":{"train_2023_2024":5865,
          "2025":{"fit_races":1145,"search_races":1186,
                  "confirm_races":594,"all_2025_races":2925},
          "audit_2026":2411},
        "total_feature_count":71,"chosen_on_middle_2025":name,
        "candidate_optimizations":{name:{"config":cfg}},
        "late_2025_confirmation":{
            "baseline":metrics(594,149),"candidate":metrics(594,160),
            "baseline_podium":podium(594),
            "candidate_podium":podium(594),
            "promotion_gate_passed":True,
            "paired_day_bootstrap":{
                "paired_calendar_day_95ci":{
                    "top1_hit":[.001,.03],
                    "winner_logloss":[-.1,-.001],
                    "winner_brier":[-.02,0.0],
                    "ordered_hit":[0.,.01],"unordered_hit":[0.,.01]}}},
        "2026_postselection_audit":{
            "legacy_baseline":metrics(2411,603),
            "joint_candidate":metrics(2411,620),
            "legacy_podium":podium(2411),
            "joint_podium":podium(2411)},
        "2026_used_to_select_hyperparameters":False,
        "same_race_result_used_as_feature":False,
        "minimum_prior_result_age_calendar_days":2
    }
    model={
        "schema":REPORT_SCHEMA,
        "production_enabled":False,
        "source_db_sha256":DB_SHA,
        "selected_hyperparameters":{"config":cfg},
        "feature_manifest":{"input_names":list(FEATURES)+list(FEATURE_NAMES),
                            "basis_names":["feature"+str(i) for i in range(71)]},
        "coefficients_joint_top3":np.zeros((3,71)).tolist(),
        "calibration":{"global_stage_temperatures":{"1":1.0,"2":1.0,"3":1.0}},
    }
    smoke={
        "schema":"jra-v52-real-preoff-smoke-v1",
        "canonical_db_sha256":DB_SHA,"model_candidate":name,
        "completed":True,"all_45_features_observed_before_asof":True,
        "verified_full_field":True,"official_identity_evidence":True,
        "published_at_before_forecast":True,
        "source_sha256":"a"*64,
    }
    return report,model,smoke

class V52ReleaseTests(unittest.TestCase):
    def test_design_reuses_training_moments_and_preserves_71_order(self):
        rng=np.random.default_rng(52)
        old=rng.normal(size=(120,len(FEATURES)))
        new=rng.normal(size=(120,len(FEATURE_NAMES)))
        old[:,0]=12.0
        z,m=design_matrix(old,new,FEATURES,FEATURE_NAMES,np.arange(100))
        reconstructed=transform_live_features(np.c_[old,new],m)
        self.assertEqual(z.shape,(120,71))
        self.assertTrue(np.allclose(z,reconstructed,atol=1e-10))

    def test_invalid_raw_live_features_fails(self):
        _,manifest=design_matrix(
            np.ones((10,31)),np.ones((10,14)),
            FEATURES,FEATURE_NAMES,np.arange(8))
        with self.assertRaisesRegex(ValueError,"45 full"):
            transform_live_features(np.ones((4,31)),manifest)
        with self.assertRaisesRegex(ValueError,"nonfinite"):
            x=np.ones((4,45));x[0,8]=np.nan
            transform_live_features(x,manifest)
        with self.assertRaisesRegex(ValueError,"ordered basis"):
            altered=dict(manifest);altered["basis_names"]=list(reversed(manifest["basis_names"]))
            transform_live_features(np.ones((4,45)),altered)

    def test_no_v52_active_without_trained_source_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            state=root/"state.json";policy=root/"policy.json";model=root/"model.json"
            snap=root/"race.json";db=root/"db.sqlite";out=root/"forecast.json"
            state.write_text(json.dumps({"standard_forecast":{"version":"v51"}}))
            policy.write_text("{}");model.write_text("{}")
            snap.write_text("{}");db.write_bytes(b"")
            with self.assertRaisesRegex(ValueError,"NOT the official"):
                forecast(snap,db,out,state_path=state,policy_path=policy,model_path=model)
            self.assertFalse(out.exists())

    def test_promotion_rejects_missing_real_results_before_model_write(self):
        report,model,smoke=simulated_evidence()
        # Schema-preserving synthetic fake demonstrates gate wiring, not true
        # JRA evidence. No files are deployed by this test.
        done=check_promotion_evidence(report,model,smoke)
        self.assertEqual(done["trained_features"],71)
        product=staged_to_production_model(model,done)
        self.assertEqual(product["standard_version"],"v52")
        self.assertTrue(product["production_enabled"])
        bad=dict(report);bad["late_2025_confirmation"]={
            **report["late_2025_confirmation"],"promotion_gate_passed":False}
        with self.assertRaisesRegex(ValueError,"acceptance failed"):
            check_promotion_evidence(bad,model,smoke)
        bad2=dict(model);bad2["coefficients_joint_top3"]=[[0.]*31]*3
        with self.assertRaisesRegex(ValueError,"3x71"):
            check_promotion_evidence(report,bad2,smoke)
        bad3=dict(smoke);bad3["all_45_features_observed_before_asof"]=False
        with self.assertRaisesRegex(ValueError,"unverified"):
            check_promotion_evidence(report,model,bad3)

    def test_live_race_history_proof_rejects_future_and_wrong_source(self):
        from datetime import datetime,timezone,timedelta
        off=datetime(2026,11,14,6,0,tzinfo=timezone.utc)
        asof=off-timedelta(hours=2)
        values={}
        for name in ("opponent_class","running_style","jockey_condition","previous_weight"):
            values[name]={"missing":False,"source_url":"https://www.jra.go.jp/source",
                "source_sha256":"a"*64,
                "published_at":(off-timedelta(days=4)).isoformat(),
                "observed_at":(asof-timedelta(hours=1)).isoformat()}
        validate_extra_provenance({"v52_feature_evidence":values},asof,off)
        later={**values,"previous_weight":{**values["previous_weight"],
               "observed_at":(off+timedelta(minutes=1)).isoformat()}}
        with self.assertRaisesRegex(ValueError,"post-asof"):
            validate_extra_provenance({"v52_feature_evidence":later},asof,off)
        wrong={**values,"running_style":{**values["running_style"],
               "source_url":"https://invalid.example.invalid"}}
        with self.assertRaisesRegex(ValueError,"official JRA"):
            validate_extra_provenance({"v52_feature_evidence":wrong},asof,off)

if __name__=="__main__":unittest.main()
