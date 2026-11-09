"""Synthetic CLI smoke test only: does not prove real JRA data availability."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False)+"\n",encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()

class PairedPipelineCLITest(unittest.TestCase):
    def test_end_to_end_synthetic(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            asof="2026-11-14T09:00:00+09:00"
            off="2026-11-14T10:00:00+09:00"
            race="2026-11-14 Tokyo 1R"
            source={"source_model":"A","asof":asof,"races":[{"race":race,
                "original_off_at":off,"surface":"turf",
                "horses":[{"number":i,"name":chr(64+i),"jockey_id":str(i),"p1":p}
                          for i,p in ((1,0.5),(2,0.3),(3,0.2))]}]}
            src=root/"original_a.json"
            a_sha=write(src,source)
            v={"version":"v50","standard_forecast":True,"live_bet_generation":False,
               "canonical_database_sha256":"a"*64,"policy_sha256":"b"*64,
               "forecast_sha256":a_sha,"rider_sha256":"c"*64,
               "forecast_asof":asof,
               "races":[{"race":race,"v50":{"horses":[
                   {"number":1,"name":"A","p1":0.5},
                   {"number":2,"name":"B","p1":0.3},
                   {"number":3,"name":"C","p1":0.2}]}}]}
            vp=root/"v50.json";write(vp,v)
            w={"asof":asof,"races":[{"race":race,"original_off_at":off,
               "observed_at":asof,"source_url":"https://example.org/synthetic",
               "source_sha256":"d"*64,
               "horses":[{"number":i,"body_weight_kg":480+i*2,
                          "weight_change_kg":(i-2)*4,"weight_observed_at":asof}
                         for i in (1,2,3)]}]}
            source_bytes=b"EXAMPLE_SYNTHETIC_PREOFF_RACE_HTML"
            source_sha=hashlib.sha256(source_bytes).hexdigest()
            w["races"][0]["source_sha256"]=source_sha
            source_dir=root/"weight_source_bytes"
            source_dir.mkdir()
            (source_dir/(source_sha+".bin")).write_bytes(source_bytes)
            wp=root/"weights.json";write(wp,w)
            cmd=[sys.executable,"-m","scripts.capture_v50_bodyweight",
                 "--forecast-source",str(src),"--v50",str(vp),
                 "--weights",str(wp),"--weight-source-archive",str(source_dir),"--output-dir",str(root/"frozen")]
            p=subprocess.run(cmd,check=True,capture_output=True,text=True)
            (source_dir/(source_sha+".bin")).write_bytes(b"TAMPERED SOURCE")
            bad=subprocess.run([sys.executable,"-m","scripts.capture_v50_bodyweight",
                "--forecast-source",str(src),"--v50",str(vp),"--weights",str(wp),
                "--weight-source-archive",str(source_dir),
                "--output-dir",str(root/"tampered")],capture_output=True)
            self.assertNotEqual(bad.returncode,0)
            (source_dir/(source_sha+".bin")).write_bytes(source_bytes)
            capture_json=Path(json.loads(p.stdout)["saved"])
            self.assertTrue(capture_json.exists())
            self.assertIn('"production_model": "v50"',capture_json.read_text())
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            results=root/"official_results.json"
            write(results,{"observed_at":"2026-11-14T12:00:00+09:00",
               "races":[{"race":race,"finish_order":[1,3,2]}]})
            out=root/"paired_result.json"
            p2=subprocess.run([sys.executable,"-m","scripts.evaluate_v50_v51_weight_pairs",
                "--archive",str(capture_json),"--official-results",str(results),
                "--output",str(out)],check=True,capture_output=True,text=True)
            report=json.loads(out.read_text())
            self.assertEqual(report["evaluation_races"],1)
            self.assertEqual(report["metrics"]["v50"]["winner_hit"],1)
            self.assertEqual(report["status"],
                             "PAIRED_HISTORICAL_EVALUATION_NO_AUTOMATIC_PROMOTION")
            self.assertEqual(json.loads(p2.stdout)["races"],1)

if __name__=="__main__":unittest.main()
