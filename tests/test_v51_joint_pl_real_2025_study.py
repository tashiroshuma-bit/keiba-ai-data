"""Research-only probability and validation tests, no claimed 2025 uplift."""
import unittest
import numpy as np
from scripts.v51_joint_pl_real_2025_study import (
    _score_choice,paired_day_bootstrap,combine_rows
)

class V51ModernStatisticalValidation(unittest.TestCase):
    def test_multiple_comparisons_choose_validation_only_by_proper_score(self):
        base={"winner_logloss":2.30,"conditional_second_logloss":2.3,"conditional_third_logloss":2.4,"winner_brier":.86,
              "ece_confidence":.06,"top1_accuracy":.25}
        good={"winner_logloss":2.20,"conditional_second_logloss":2.2,"conditional_third_logloss":2.35,"winner_brier":.84,
              "ece_confidence":.055,"top1_accuracy":.26}
        overconfident={"winner_logloss":2.34,"conditional_second_logloss":2.1,"conditional_third_logloss":2.2,"winner_brier":.82,
              "ece_confidence":.055,"top1_accuracy":.49}
        self.assertEqual(_score_choice({"baseline":base,"good":good,
                                        "overfit":overconfident},base),"good")
        self.assertEqual(_score_choice({"baseline":base,"overfit":overconfident},base),"baseline")

    def test_date_block_bootstrap_jointly_assesses_proper_scores_and_podium(self):
        base={};new={}
        for day in range(1,21):
            for race in (1,2,3):
                key=f"{day}-{race}"
                common={"race":key,"date":f"2025-05-{day:02d}"}
                base[key]={**common,"top1_hit":0,
                     "winner_logloss":2.0,"winner_brier":.9,
                     "ordered_hit":0,"unordered_hit":0}
                new[key]={**common,"top1_hit":1,
                     "winner_logloss":1.5,"winner_brier":.8,
                     "ordered_hit":1,"unordered_hit":1}
        x=paired_day_bootstrap(base,new,repetitions=250)
        self.assertEqual((x["n_dates"],x["n_races"]),(20,60))
        self.assertGreater(x["paired_calendar_day_95ci"]["top1_hit"][0],0)
        self.assertLess(x["paired_calendar_day_95ci"]["winner_logloss"][1],0)
        self.assertGreaterEqual(x["paired_calendar_day_95ci"]["ordered_hit"][0],0)
        with self.assertRaisesRegex(ValueError,"different heldout"):
            paired_day_bootstrap(base,{**new,"wrong":new["1-1"]},repetitions=3)

    def test_only_true_podium_is_assessed(self):
        s=combine_rows({"r1":{"date":"2025-01-01","top1_hit":1}},
                       {"r1":{"ordered_hit":1,"unordered_hit":1}})
        self.assertEqual(s["r1"]["ordered_hit"],1)
        self.assertEqual(s["r1"]["top1_hit"],1)

if __name__=="__main__":
    unittest.main()
