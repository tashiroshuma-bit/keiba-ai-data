"""End-to-end canonical-shaped SQLite -> 14 historical features.

Fixtures are synthetic; this is a data-ingestion regression test, NOT a
2025 backtest. Historical results become eligible only at least two days later.
"""
import json
import sqlite3
import unittest

import numpy as np
from scripts.v51_four_axis_historical_features import (
    FEATURE_NAMES,align_with_original,build_features,_select_metadata
)

def runner(race,date,num,horse,jockey,rank):
    return {"race":race,"date":date,"num":num,"rank":rank,
            "horse_id":horse,"jockey_id":jockey,
            "track":"Tokyo","surface":"turf","dist":1600}

class FourAxisCanonicalSQLiteIntegration(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(":memory:")
        self.con.executescript("""
            CREATE TABLE annual_report_races(
                race_id TEXT PRIMARY KEY, status TEXT,
                expected_runners INTEGER, race_name TEXT);
            CREATE TABLE annual_report_runners(
                race_id TEXT, horse_number INTEGER, payload_json TEXT);
        """)
        self.races={}
        dates=["2025-01-04","2025-01-05","2025-01-06"]
        for k,rid in enumerate(("A","B","C")):
            self.con.execute("INSERT INTO annual_report_races VALUES(?,?,?,?)",
                (rid,"validated_result",3,"2勝クラス" if k<2 else "3勝クラス"))
            self.races[rid]=[
                runner(rid,dates[k],1,"jra:h1","jra:j1",1 if k==0 else 2),
                runner(rid,dates[k],2,"jra:h2","jra:j2",2 if k==0 else 1),
                runner(rid,dates[k],3,"jra:h3","jra:j3",3),
            ]
            for n,corner,delta in ((1,"2 2","+8"),(2,"3 3","-4"),(3,"1 1","+0")):
                self.con.execute("INSERT INTO annual_report_runners VALUES(?,?,?)",
                    (rid,n,json.dumps({"corner_positions":corner,
                        "body_weight_raw":"480",
                        "body_weight_change_raw":delta},ensure_ascii=False)))

    def tearDown(self):
        self.con.close()

    def test_canonical_source_and_day2_embargo_and_alignment(self):
        source,coverage=_select_metadata(self.con,self.races)
        self.assertEqual(coverage["runner_observations"],9)
        self.assertEqual(coverage["class_reported"],9)
        self.assertEqual(coverage["corner4_reported"],9)
        self.assertEqual(coverage["weight_delta_reported"],9)
        self.assertEqual(source[("A",1)]["class_level"],3)
        self.assertEqual(source[("A",1)]["corner4"],2)
        history,counts=build_features(self.races,source,minimum_days=2)
        self.assertEqual(counts["feature_rows"],9)
        self.assertEqual(history[("A",1)][2],1.) # no historical class
        self.assertEqual(history[("B",1)][2],1.) # day 1 embargo
        self.assertEqual(history[("C",1)][2],0.) # day 2 eligible prior A
        self.assertAlmostEqual(history[("C",1)][0],3/9)
        self.assertAlmostEqual(history[("C",1)][4],0.5)
        self.assertAlmostEqual(history[("C",1)][11],(100*8/472)/10)
        self.assertGreater(history[("C",1)][8],0)
        ids=[rid for rid in ("A","B","C") for _ in (1,2,3)]
        numbers=[n for rid in ("A","B","C") for n in (1,2,3)]
        arr=align_with_original(history,ids,numbers)
        self.assertEqual(arr.shape,(9,len(FEATURE_NAMES)))
        self.assertTrue(np.isfinite(arr).all())

    def test_invalid_corner_missing_stays_missing(self):
        self.con.execute("UPDATE annual_report_runners SET payload_json=? WHERE race_id='A' AND horse_number=1",
            (json.dumps({"corner_positions":"not-a-corner",
                "body_weight_raw":"not announced","body_weight_change_raw":"-"}),))
        source,_=_select_metadata(self.con,self.races)
        f,_=build_features(self.races,source,minimum_days=2)
        self.assertEqual(f[("C",1)][7],1.)
        self.assertEqual(f[("C",1)][13],1.)
        self.assertEqual(f[("C",1)][2],0.)
        self.assertEqual(f[("C",1)][10],0.) # past jockey is still valid

if __name__=="__main__":
    unittest.main()
