import unittest
from scripts.body_weight_audit import number,bucket,analyze

def row(rid,field,position,weight,delta):
    return {"race_id":rid,"expected_runners":field,"finish_order":position,
            "payload":{"body_weight_raw":weight,
                       "body_weight_change_raw":delta,
                       "finish_position":position}}

class BodyWeightAuditTests(unittest.TestCase):
    def test_reported_delta_parser(self):
        self.assertEqual(number("＋10"),10)
        self.assertEqual(number("−4"),-4)
        self.assertIsNone(number("計不"))
        self.assertEqual(bucket(-20),"<=-20")
        self.assertEqual(bucket(-10),"-19..-10")
        self.assertEqual(bucket(0),"-3..+3")
        self.assertEqual(bucket(20),">=+20")

    def test_complete_field_and_unknown(self):
        rows=[row("R1",3,1,"480","+10"),
              row("R1",3,2,"492","---"),
              row("R1",3,3,"510","-10")]
        result=analyze(rows)
        self.assertEqual(result["complete_races"],1)
        by_bucket={r["bucket"]:r for r in result["cells"]}
        self.assertEqual(by_bucket["+10..+19"]["wins"],1)
        self.assertEqual(by_bucket["unknown"]["n"],1)
        self.assertEqual(by_bucket["-19..-10"]["top3"],1)

    def test_reject_partial_field(self):
        result=analyze([row("R1",3,1,"480","+10"),
                        row("R1",3,2,"490","-2")])
        self.assertEqual(result["complete_races"],0)
        self.assertEqual(result["coverage"]["excluded_incomplete_races"],1)

if __name__=="__main__": unittest.main()
