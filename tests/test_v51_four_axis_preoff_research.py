"""Source time and missingness regression tests; synthetic fixtures not efficacy."""
import copy
import unittest

from scripts.v51_four_axis_preoff_research import (
    build,bodyweight_announcement,class_level
)

ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
OLD_OFF="2026-11-07T10:00:00+09:00"
OLD_PUBLISHED="2026-11-07T11:00:00+09:00"
OLD_CAPTURED="2026-11-07T11:15:00+09:00"
EVIDENCE={"source_url":"https://www.jra.go.jp/datafile/seiseki/",
          "source_sha256":"a"*64,
          "published_at":OLD_PUBLISHED,
          "observed_at":OLD_CAPTURED}

def prior(horse_id,jockey_id,*,race_id="past-1",pos=3,corner=2,delta=8):
    return {"race_id":race_id,"horse_id":horse_id,
       "jockey_id":jockey_id,
       "off_at":OLD_OFF,
       "field_size":12,"finish_order":pos,
       "corner4_position":corner,
       "track":"Tokyo","surface":"turf","distance_m":1600,
       "race_class":"2勝クラス",
       "opponent_strength_preoff":0.65,
       "opponent_strength_basis":"preoff_prior_runner_histories",
       "bodyweight_kg":484,"bodyweight_change_kg":delta,
       **EVIDENCE}

def field():
    f=[]
    for n in (1,2,3):
        hid=f"jra:202310000{n}"
        jid=f"jra-jockey-{n}"
        f.append({"number":n,"horse_id":hid,"jockey_id":jid,
           "official_identity_proof":{
              "horse_id":hid,
              "source_url":"https://www.jra.go.jp/JRADB/",
              "source_sha256":"b"*64,"observed_at":"2026-11-14T07:00:00+09:00"},
           "horse_history":[],
           "jockey_history":[]})
    return f

def invoke(f,**kw):
    return build(f,forecast_asof=ASOF,race_off_at=OFF,
        track="Tokyo",surface="turf",distance_m=1600,
        current_class="3勝クラス",current_class_proof={
          "source_url":"https://www.jra.go.jp/keiba/tokubetsu/",
          "source_sha256":"d"*64,
          "observed_at":"2026-11-14T07:00:00+09:00"},**kw)

class V51FourAxisPreoff(unittest.TestCase):
    def test_jra_class_order_no_confusion_gi_with_1win(self):
        self.assertEqual(class_level("皐月賞（GⅠ）"),9)
        self.assertEqual(class_level("京王杯2歳S（GⅡ）"),8)
        self.assertEqual(class_level("レース 3勝クラス"),4)
        self.assertEqual(class_level("2歳新馬"),0)
        self.assertEqual(class_level("3歳未勝利"),1)
        self.assertIsNone(class_level("競走名のみ"))

    def test_verified_four_axis_features_and_prior_weight(self):
        f=field()
        f[0]["horse_history"]=[prior(f[0]["horse_id"],f[0]["jockey_id"])]
        f[0]["jockey_history"]=[prior("jra:other",f[0]["jockey_id"],
                                    race_id="jockey-past",pos=2,corner=4)]
        doc=invoke(f)
        row=doc["runners"][0]
        self.assertEqual(row["class_strength_last3"],3)
        self.assertEqual(row["class_change_from_last"],1)
        self.assertEqual(row["rivals_preoff_strength_last3"],0.65)
        self.assertEqual(row["style_front_or_prominent_rate"],1)
        self.assertEqual(row["style_closer_rate"],0)
        self.assertEqual(row["style_observed_races"],1)
        self.assertEqual(row["jockey_condition_starts"],1)
        self.assertGreater(row["jockey_condition_residual"],0)
        self.assertAlmostEqual(row["previous_bodyweight_pct_last3"],100*8/476)
        self.assertFalse(row["bodyweight_available"])
        self.assertIsNone(row["bodyweight_pct"])
        self.assertFalse(doc["production_model_updated"])

    def test_announced_weight_authentic_preoff_required(self):
        f=field()
        f[0]["bodyweight_announcement"]={
           "horse_id":f[0]["horse_id"],"status":"発表済",
           "bodyweight_kg":486,"bodyweight_change_kg":8,
           "source_url":"https://www.jra.go.jp/keiba/",
           "source_sha256":"a"*64,
           "published_at":"2026-11-14T08:20:00+09:00",
           "observed_at":"2026-11-14T08:30:00+09:00"}
        d=invoke(f)
        self.assertAlmostEqual(d["runners"][0]["bodyweight_pct"],100*8/478)
        self.assertTrue(d["runners"][0]["bodyweight_available"])

    def test_not_announced_is_missing_not_zero(self):
        f=field()
        f[0]["bodyweight_announcement"]={"status":"未発表",
           "horse_id":f[0]["horse_id"]}
        d=invoke(f)
        self.assertIsNone(d["runners"][0]["bodyweight_pct"])
        self.assertEqual(d["runners"][0]["bodyweight_missing_reason"],
                         "not_announced_or_no_verified_snapshot")

    def test_future_weight_rejected_even_when_preoff_race(self):
        f=field()
        f[0]["bodyweight_announcement"]={
           "horse_id":f[0]["horse_id"],"status":"発表済",
           "bodyweight_kg":486,"bodyweight_change_kg":8,
           "source_url":"https://www.jra.go.jp/keiba/",
           "source_sha256":"a"*64,
           "published_at":"2026-11-14T09:10:00+09:00",
           "observed_at":"2026-11-14T09:10:00+09:00"}
        with self.assertRaisesRegex(ValueError,"post-asof"):
            invoke(f)

    def test_post_race_result_history_rejected_without_published_at(self):
        f=field()
        h=prior(f[0]["horse_id"],f[0]["jockey_id"])
        del h["published_at"]
        f[0]["horse_history"]=[h]
        with self.assertRaisesRegex(ValueError,"published_at"):
            invoke(f)

    def test_unsupported_opponent_strength_is_missing(self):
        f=field()
        h=prior(f[0]["horse_id"],f[0]["jockey_id"])
        h["opponent_strength_basis"]="from_final_result"
        f[0]["horse_history"]=[h]
        r=invoke(f)["runners"][0]
        self.assertIsNone(r["rivals_preoff_strength_last3"])
        self.assertEqual(r["rivals_strength_observed_races"],0)

    def test_same_day_or_future_history_rejected(self):
        f=field()
        h=prior(f[0]["horse_id"],f[0]["jockey_id"])
        h["off_at"]=OFF
        h["published_at"]="2026-11-14T10:01:00+09:00"
        h["observed_at"]="2026-11-14T10:10:00+09:00"
        f[0]["horse_history"]=[h]
        with self.assertRaisesRegex(ValueError,"future label|ordering"):
            invoke(f)

    def test_jockey_history_cannot_join_another_jockey(self):
        f=field()
        f[0]["jockey_history"]=[prior("jra:other","wrong-jockey")]
        with self.assertRaisesRegex(ValueError,"jockey identity mismatch"):
            invoke(f)

    def test_duplicate_runner_identity_rejected(self):
        f=field()
        f[1]["horse_id"]=f[0]["horse_id"]
        with self.assertRaisesRegex(ValueError,"duplicate JRA horse"):
            invoke(f)

    def test_no_imputed_feature_for_debut(self):
        f=field()
        row=invoke(f)["runners"][0]
        self.assertIsNone(row["corner4_position_last3"])
        self.assertEqual(row["style_observed_races"],0)
        self.assertIsNone(row["class_strength_last3"])
        self.assertIsNone(row["jockey_condition_residual"])
        self.assertIsNone(row["previous_bodyweight_pct_last3"])

if __name__=="__main__":
    unittest.main()
