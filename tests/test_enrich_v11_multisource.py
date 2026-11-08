import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from scripts.enrich_v11_multisource import normalize,upgrade,PROVIDERS

T="2026-11-07T12:00:00+09:00"
class MultiSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.db=self.base/"v11.sqlite"
        c=sqlite3.connect(self.db)
        c.execute("CREATE TABLE annual_report_races(race_id TEXT PRIMARY KEY)")
        c.execute("INSERT INTO annual_report_races VALUES('202605050211')")
        c.commit();c.close()
        self.fact={"source_id":"jra_official","official_race_id":"202605050211",
            "horse_number":6,"feature_key":"bloodline_sire",
            "value":"父馬テスト","source_url":"https://www.jra.go.jp/JRADB/accessS.html",
            "source_sha256":"a"*64,
            "observed_at":T,"published_at":"2026-11-06T09:00:00+09:00",
            "forecast_asof":"2026-11-08T09:00:00+09:00",
            "off_at":"2026-11-08T15:30:00+09:00",
            "rights_basis":"official_public_factual",
            "verified_jra_horse_id":"jra:2020100006",
            "horse_id_evidence":{
              "race_id":"202605050211","horse_number":6,
              "horse_id":"jra:2020100006",
              "url":"https://www.jra.go.jp/JRADB/accessS.html",
              "sha256":"b"*64,"observed_at":"2026-11-07T10:00:00+09:00"}}
    def test_official_evidenced_asof_can_be_preoff(self):
        row=normalize(self.fact)
        self.assertEqual(row[17],"preoff_proven")
        self.assertEqual(row[18],1)
    def test_unknown_horse_not_automatically_joined(self):
        r={**self.fact,"verified_jra_horse_id":None}
        self.assertIsNone(normalize(r)[5])
        self.assertEqual(normalize(r)[18],0)
    def test_false_historical_publication_not_preoff(self):
        r={**self.fact,"published_at":None}
        self.assertEqual(normalize(r)[18],0)
        with self.assertRaises(ValueError):
            normalize({**r,"requires_preoff":True})
    def test_odds_not_from_final_race(self):
        r={**self.fact,"feature_key":"preoff_win_odds","value":3.4}
        self.assertEqual(normalize(r)[18],0)
        r["complete_market_snapshot"]=True;r["odds_kind"]="observed_actual"
        self.assertEqual(normalize(r)[18],1)
        r["feature_key"]="final_win_odds"
        self.assertEqual(normalize(r)[18],0)
    def test_no_unlicensed_vendor_or_bulk_scrape(self):
        r={**self.fact,"source_id":"netkeiba",
            "source_url":"https://race.netkeiba.com/race/shutuba.html"}
        with self.assertRaises(ValueError):normalize(r)
        r.update({"rights_basis":"specific_permission","rights_reference":"written agreement ref 123",
                  "acquisition_mode":"bulk_scrape"})
        with self.assertRaises(ValueError):normalize(r)
    def test_no_vendor_host_impersonation(self):
        r={**self.fact,"source_id":"umarand",
            "source_url":"https://otherdomain.com/data",
            "rights_basis":"specific_permission","rights_reference":"written agreement"}
        with self.assertRaises(ValueError):normalize(r)
    def test_migrate_preserves_history_and_appends_authorized_records(self):
        data=self.base/"sample.jsonl"
        data.write_text(json.dumps(self.fact,ensure_ascii=False)+"\n")
        output=self.base/"v12.sqlite"
        audit=upgrade(self.db,data,output)
        self.assertEqual(audit["records"],1)
        self.assertEqual(audit["preoff_usable"],1)
        conn=sqlite3.connect(output)
        self.assertEqual(conn.execute("SELECT count(*) FROM annual_report_races").fetchone()[0],1)
        self.assertEqual(conn.execute("SELECT count(*) FROM multi_source_registry").fetchone()[0],5)
        self.assertEqual(conn.execute("SELECT verified_jra_horse_id FROM multi_source_observation").fetchone()[0],
                        "jra:2020100006")
        self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0],"ok")
        conn.close()
        self.assertNotEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),audit["output_sha256"])
    def test_reject_invalid_data_without_partial_database(self):
        data=self.base/"bad.jsonl"
        data.write_text(json.dumps({**self.fact,"horse_number":100},ensure_ascii=False)+"\n")
        output=self.base/"invalid.sqlite"
        with self.assertRaises(ValueError):
            upgrade(self.db,data,output)
        self.assertFalse(output.exists())
    def test_preexisting_output_not_overwritten(self):
        data=self.base/"one.jsonl"
        data.write_text(json.dumps(self.fact,ensure_ascii=False)+"\n")
        out=self.base/"exist.sqlite";out.write_text("immutable")
        with self.assertRaises(FileExistsError):upgrade(self.db,data,out)
        self.assertEqual(out.read_text(),"immutable")

if __name__=="__main__": unittest.main()
