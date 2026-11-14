import datetime as dt
import unittest
from scripts.v51_live_racecard_contract import validate


class LiveRacecardContractTests(unittest.TestCase):
    def make_card(self):
        return {
            "schema": "jra-v51-live-racecard-v1",
            "captured_at": "2026-11-14T10:00:00+09:00",
            "source_url": "https://www.jra.go.jp/example",
            "source_sha256": "a" * 64,
            "races": [{
                "race": "test-1",
                "race_off_at": "2026-11-15T15:00:00+09:00",
                "horses": [
                    {"number": n, "name": "TEST", "horse_id": f"jra:{n:010d}",
                     "jockey_id": "jra:000001",
                     "official_identity_proof": {
                         "horse_id": f"jra:{n:010d}", "horse_number": n,
                         "source_url": "https://www.jra.go.jp/example",
                         "observed_at": "2026-11-14T09:00:00+09:00",
                     }} for n in (1, 2, 3)
                ],
            }],
        }

    def test_valid_contract(self):
        self.assertEqual(validate(self.make_card())["horses"], 3)

    def test_duplicate_horse_id_rejected(self):
        doc = self.make_card()
        doc["races"][0]["horses"][1]["horse_id"] = "jra:0000000001"
        with self.assertRaisesRegex(ValueError, "PROOF|DUPLICATE"):
            validate(doc)

    def test_postoff_capture_rejected(self):
        doc = self.make_card()
        doc["captured_at"] = "2026-11-16T10:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "PREOFF"):
            validate(doc)


if __name__ == "__main__":
    unittest.main()
