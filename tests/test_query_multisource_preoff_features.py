import json,sqlite3,tempfile,unittest
from pathlib import Path
from scripts.enrich_v11_multisource import SCHEMA,normalize,PROVIDERS
from scripts.query_multisource_preoff_features import export_asof

class AsOfImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite"
        con=sqlite3.connect(self.db)
        con.executescript(SCHEMA)
        con.execute("INSERT INTO multi_source_registry VALUES(?,?,?,?,?,?)",(
            "jra_official","jra.go.jp","free_public","manual","verified","2026-11-07T00:00:00+09:00"))
        con.commit();con.close()
        self.example={"source_id":"jra_official",
          "official_race_id":"202605050211","horse_number":1,
          "feature_key":"bloodline_sire","value":"父A",
          "source_url":"https://www.jra.go.jp/results","source_sha256":"a"*64,
          "observed_at":"2026-11-07T12:00:00+09:00",
          "published_at":"2026-11-07T10:00:00+09:00",
          "forecast_asof":"2026-11-08T10:00:00+09:00",
          "off_at":"2026-11-08T15:00:00+09:00",
          "rights_basis":"official_public_factual",
          "verified_jra_horse_id":"jra:2020100001",
          "horse_id_evidence":{"race_id":"202605050211","horse_number":1,
             "horse_id":"jra:2020100001","url":"https://www.jra.go.jp/official",
             "sha256":"b"*64,"observed_at":"2026-11-07T10:59:00+09:00"}}
        self.roster=[{"number":i,"horse_id":f"jra:202010000{i}"} for i in range(1,4)]
    def insert(self,r):
        fields=["observation_id","source_id","official_race_id","horse_number",
          "source_horse_id","verified_jra_horse_id","feature_key","value_text",
          "value_num","observed_at","published_at","forecast_asof","off_at",
          "source_url","source_sha256","rights_basis","rights_reference",
          "phase","usable_for_v50_v51_preoff","created_at"]
        placeholders=",".join("?" for _ in fields)
        con=sqlite3.connect(self.db)
        con.execute(f"INSERT INTO multi_source_observation VALUES ({placeholders})",normalize(r))
        con.commit();con.close()
    def query(self,roster=None):
        return export_asof(self.db,"202605050211",
          "2026-11-08T10:00:00+09:00",
          "2026-11-08T15:00:00+09:00",roster or self.roster)
    def test_eligible_proven_bloodline(self):
        self.insert(self.example)
        out=self.query()
        self.assertEqual(len(out["usable_external_fields"]),1)
        self.assertFalse(out["ranking_or_v50_probabilities_modified"])
    def test_anonymous_horse_does_not_appear(self):
        self.insert(self.example)
        roster=[{**h,"horse_id":"jra:9999999999"} if h["number"]==1 else h
                for h in self.roster]
        out=self.query(roster)
        self.assertEqual(out["usable_external_fields"],[])
        self.assertEqual(out["rejected_records"],1)
    def test_single_horse_odds_cannot_be_used(self):
        r={**self.example,"feature_key":"preoff_win_odds","value":2.3,
           "odds_kind":"observed_actual","complete_market_snapshot":True}
        self.insert(r)
        out=self.query()
        self.assertFalse(out["complete_preoff_odds_snapshot"])
        self.assertEqual(out["usable_external_fields"],[])
    def test_all_horses_same_timestamp_market_allowed(self):
        for n in range(1,4):
            r={**self.example,"horse_number":n,"verified_jra_horse_id":f"jra:202010000{n}",
                "horse_id_evidence":{**self.example["horse_id_evidence"],
                  "horse_number":n,"horse_id":f"jra:202010000{n}"},
                "feature_key":"preoff_win_odds","value":1+n,
                "odds_kind":"observed_actual","complete_market_snapshot":True}
            self.insert(r)
        out=self.query()
        self.assertTrue(out["complete_preoff_odds_snapshot"])
        self.assertEqual(len(out["usable_external_fields"]),3)
    def test_late_forecast_rejected(self):
        self.insert(self.example)
        with self.assertRaises(ValueError):
            export_asof(self.db,"202605050211",
                "2026-11-08T16:00:00+09:00",
                "2026-11-08T15:00:00+09:00",self.roster)

if __name__=="__main__":unittest.main()
