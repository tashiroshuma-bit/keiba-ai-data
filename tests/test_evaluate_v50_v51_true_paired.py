import unittest
from scripts.evaluate_v50_v51_true_paired import joined,score
class TruePairedTests(unittest.TestCase):
    def setUp(self):
        time="2026-11-08T10:00:00+09:00"
        base={"race":"東京12R","source_model":"v50","asof":time,
          "original_off_at":"2026-11-08T16:10:00+09:00",
          "horses":[]}
        for i,p in enumerate((.55,.3,.15),1):
            base["horses"].append({"number":i,"name":f"馬{i}",
               "horse_id":f"jra:201710000{i}","p1":p,
               "horse_id_evidence_url":"https://www.jra.go.jp/JRADB/official",
               "horse_id_evidence_sha256":"a"*64,
               "historical_feature_published_at":"2026-11-07T07:00:00+09:00"})
        cand={**base,"source_model":"v51","horses":[{**x,"p1":p} for x,p in
                                   zip(base["horses"],(.15,.3,.55))]}
        self.base={"races":[base]};self.cand={"races":[cand]}
        self.truth={"races":[{"race":"東京12R","date":"2026-11-08",
            "official_sha256":"b"*64,"field_size":3,"winner_number":3}]}
    def test_computes_correct_same_race_result(self):
        matched,reject=joined(self.base,self.cand,self.truth)
        self.assertEqual(len(matched),1)
        outcome=score(matched)
        self.assertEqual(outcome["models"]["base"]["hit"],0)
        self.assertEqual(outcome["models"]["candidate"]["hit"],1)
        self.assertFalse(outcome["allow_promotion"])
    def test_missing_candidate_never_fakes_comparison(self):
        matched,reject=joined(self.base,{"weights":[.1]},self.truth)
        self.assertEqual(len(matched),0)
        self.assertEqual(reject["missing_v51_preoff_snapshot"],1)
    def test_postoff_features_rejected(self):
        self.cand["races"][0]["horses"][1]["historical_feature_published_at"]="2026-11-08T17:00:00+09:00"
        matched,reject=joined(self.base,self.cand,self.truth)
        self.assertEqual(len(matched),0)
        self.assertTrue(any("post-asof" in v for v in reject))
    def test_name_or_horse_id_conflict_rejected(self):
        self.cand["races"][0]["horses"][1]["horse_id"]="jra:unverified"
        matched,reject=joined(self.base,self.cand,self.truth)
        self.assertEqual(len(matched),0)
    def test_untimestamped_fails(self):
        self.base["races"][0]["asof"]="2026-11-08T10:00:00"
        matched,reject=joined(self.base,self.cand,self.truth)
        self.assertEqual(len(matched),0)
if __name__=="__main__":unittest.main()
