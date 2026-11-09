import unittest
from scripts.body_weight_audit import analyze,bucket,number

class BodyWeightAuditTests(unittest.TestCase):
    def test_bins(self):
        self.assertEqual(bucket(-10),"-19..-10")
        self.assertEqual(bucket(0),"-3..+3")
        self.assertEqual(bucket(10),"+10..+19")
    def test_only_previous_official_identity(self):
        rows=[
          dict(horse_id="A",race_date="2025-01-01",surface="turf",distance_m=1600,finish_order=4,payload={"body_weight":480}),
          dict(horse_id="A",race_date="2025-03-01",surface="turf",distance_m=1600,finish_order=1,payload={"body_weight":488}),
          dict(horse_id="B",race_date="2025-03-01",surface="turf",distance_m=1600,finish_order=2,payload={"body_weight":502}),
          dict(horse_id=None,race_date="2025-03-01",surface="turf",distance_m=1600,finish_order=1,payload={"body_weight":488})]
        result=analyze(rows)
        self.assertEqual(result["coverage"]["paired_valid"],1)
        self.assertEqual(result["cells"][0]["bucket"],"+4..+9")
        self.assertEqual(result["cells"][0]["win_rate"],1)
    def test_conflicting_reported_delta_rejected(self):
        rows=[
          dict(horse_id="A",race_date="2025-01-01",surface="dirt",distance_m=1200,finish_order=3,payload={"body_weight":490}),
          dict(horse_id="A",race_date="2025-02-01",surface="dirt",distance_m=1200,finish_order=2,payload={"body_weight":500,"weight_change":-4})]
        self.assertEqual(analyze(rows)["coverage"]["conflicting_explicit_change"],1)

if __name__=="__main__":unittest.main()
