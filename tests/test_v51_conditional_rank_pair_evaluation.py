import unittest
from scripts.v51_conditional_rank_pair_evaluation import compare

ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
RACE="2026-11-14 Tokyo 1R"

def example():
    a={"schema":"jra-v50-weight-paired-preoff-v1","forecast_asof":ASOF,
       "races":[{"race":RACE,"original_off_at":OFF,"horses":[
           {"number":1,"v50_p1":.5},{"number":2,"v50_p1":.3},
           {"number":3,"v50_p1":.2}]}]}
    rank={"races":[{"race":RACE,"deployment_status":"experimental_rank_shadow",
       "strict_production_validated":False,"created_at":ASOF,"off_timestamp":OFF,
       "runners":[{"horse_number":1,"p_first":.4,"p_second":.4,"p_third":.2},
                  {"horse_number":2,"p_first":.4,"p_second":.3,"p_third":.3},
                  {"horse_number":3,"p_first":.2,"p_second":.3,"p_third":.5}],
       "winner_pick":2,"top3_pick":[1,2,3],"ordered_pick":[2,1,3]}]}
    results={"observed_at":"2026-11-14T12:00:00+09:00",
             "races":[{"race":RACE,"finish_order":[2,1,3]}]}
    return a,rank,results

class V51ConditionalRankPairTest(unittest.TestCase):
    def test_paired_same_race(self):
        a,b,c=example()
        report=compare(a,b,c)
        self.assertEqual(report["n_races"],1)
        self.assertEqual(report["metrics"]["conditional_rank_shadow"]["winner_hit"],1)
        self.assertEqual(report["metrics"]["v50"]["winner_hit"],0)
        self.assertEqual(report["metrics"]["conditional_rank_shadow"]["ordered_full_podium_hit"],1)
    def test_future_rank_rejected(self):
        a,b,c=example()
        b["races"][0]["created_at"]="2026-11-14T09:01:00+09:00"
        with self.assertRaises(ValueError):compare(a,b,c)
    def test_wrong_athlete_count(self):
        a,b,c=example()
        b["races"][0]["runners"].pop()
        with self.assertRaises(ValueError):compare(a,b,c)
    def test_bad_probability_normalization(self):
        a,b,c=example()
        b["races"][0]["runners"][0]["p_second"]=.2
        with self.assertRaises(ValueError):compare(a,b,c)
    def test_no_results_before_off(self):
        a,b,c=example()
        c["observed_at"]=ASOF
        with self.assertRaises(ValueError):compare(a,b,c)
if __name__=="__main__":unittest.main()
