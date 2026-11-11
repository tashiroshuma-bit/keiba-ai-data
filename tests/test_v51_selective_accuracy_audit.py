import json
import unittest
from pathlib import Path
from scripts.v51_rank_selective_accuracy_audit import audit, DEFAULT_INPUT

class V51SelectiveRankingAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=audit(json.loads(Path(DEFAULT_INPUT).read_text(encoding="utf-8")))
    def test_entire_cohort_reproduces_real_v51_hits(self):
        self.assertEqual(self.report["years"]["2025"]["races"],2925)
        self.assertEqual(self.report["years"]["2025"]["winner_hits"],719)
        self.assertEqual(self.report["years"]["2026"]["races"],2411)
        self.assertEqual(self.report["years"]["2026"]["winner_hits"],603)
    def test_confidence_04_prespecified_real_2026_coverage_and_hits(self):
        c=self.report["years"]["2026"]["selected_race_thresholds"][1]
        self.assertEqual((c["races"],c["winner_hits"]),(255,100))
        self.assertAlmostEqual(c["winner_hit_rate_selected_only"],100/255)
        self.assertTrue(c["not_full_race_model_accuracy"])
        p=self.report["years"]["2025"]["selected_race_thresholds"][1]
        self.assertEqual((p["races"],p["winner_hits"]),(273,84))
    def test_high_confidence_selection_never_changes_full_cohort_metric(self):
        self.assertAlmostEqual(self.report["years"]["2026"]["all_races_winner_hit_rate"],603/2411)
        self.assertTrue(self.report["not_full_population_rank_improvement"])
    def test_source_fabrication_refused(self):
        d=json.loads(Path(DEFAULT_INPUT).read_text(encoding="utf-8"))
        d["modes"]["full"]["2026_calibrated_on_2025"]["top1_hits"]=700
        with self.assertRaisesRegex(ValueError,"unexpected"):
            audit(d)
if __name__=="__main__":unittest.main()
