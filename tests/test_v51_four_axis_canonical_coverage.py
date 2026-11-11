"""Canonical DB audit fixtures; not a real V51 performance test."""
import json
import sqlite3
import unittest

from scripts.v51_four_axis_canonical_coverage import field_audit

class V51CanonicalFourAxisAudit(unittest.TestCase):
    def db(self):
        conn=sqlite3.connect(":memory:")
        conn.execute("""create table annual_report_races
           (race_id text,race_date text,status text,track text,surface text,
            distance_m integer,race_name text)""")
        conn.execute("""create table annual_report_runners
           (race_id text,horse_number integer,horse_id text,
            jockey_id text,payload_json text)""")
        for rid,date,name in (
            ("A","2025-01-04","2勝クラス"),
            ("B","2025-01-04","2勝クラス"),
            ("C","2025-01-05","3勝クラス")):
            conn.execute("insert into annual_report_races values (?,?,?,?,?,?,?)",
                         (rid,date,"validated_result","Tokyo","turf",1600,name))
        for rid,horse,jockey,record in (
            ("A","jra:h1","jra:j1",{"body_weight_raw":"486",
                     "body_weight_change_raw":"+8"}),
            ("B","jra:h1","jra:j1",{"corner4_position":2}),
            ("C","jra:h1","jra:j1",{"corner4_position":4,
                     "body_weight_raw":"490","body_weight_change_raw":"+4"})):
            conn.execute("insert into annual_report_runners values (?,?,?,?,?)",
                         (rid,1,horse,jockey,json.dumps(record)))
        return conn

    def test_day_boundary_not_same_day_history(self):
        c=self.db()
        out=field_audit(c)
        self.assertEqual(out["n_validated_runner_rows_scanned"],3)
        self.assertEqual(out["distinct_races_scanned"],3)
        self.assertEqual(out["source_coverage_counts"]
                         ["previous_calendar_day_horse_start"],1)
        self.assertEqual(out["source_coverage_counts"]
                         ["previous_calendar_day_jockey_start"],1)
        self.assertEqual(out["source_coverage_counts"]
                         ["postrace_delta_reported"],2)
        self.assertEqual(out["source_coverage_counts"]
                         ["runner_corner_related_payload_present"],2)
        self.assertEqual(out["source_coverage_counts"]
                         ["race_class_label_present_in_race_columns"],3)
        self.assertIsNone(out["preoff_current_bodyweight_count_proven"])
        self.assertFalse(out["official_v51_model_changed"])
        c.close()

    def test_row_limit_is_explicit(self):
        c=self.db()
        x=field_audit(c,max_runners=1)
        self.assertEqual(x["n_validated_runner_rows_scanned"],1)
        self.assertEqual(x["source_coverage_counts"]["postrace_weight_reported"],1)
        c.close()

    def test_missing_table_or_wrong_schema_fails(self):
        c=sqlite3.connect(":memory:")
        with self.assertRaisesRegex(ValueError,"canonical"):
            field_audit(c)
        c.close()

if __name__=="__main__":
    unittest.main()
