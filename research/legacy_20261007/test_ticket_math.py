import itertools
import unittest

from ticket_math import forecast, settle, hit


def plan(tickets):
    return {"race_id": "test|東京|11", "field": list(range(1, 9)),
            "scheduled_start": "2026-10-04T15:45:00+09:00",
            "locked_at": "2026-10-04T15:40:00+09:00",
            "odds_observed_at": "2026-10-04T15:39:00+09:00",
            "odds_source_url": "https://www.jra.go.jp/",
            "budget_yen": 5000, "tickets": tickets}


def ticket(kind, horses, stake, floor=1000):
    return {"type": kind, "horses": horses, "stake_yen": stake,
            "price_floor_per_100_yen": floor}


class TicketMathTest(unittest.TestCase):
    def test_five_to_seven_starters_place_only_top_two_but_wide_top_three(self):
        small = plan([ticket("PLACE", [3], 100)])
        small["field"] = [1, 2, 3, 4, 5, 6]
        self.assertFalse(hit(small["tickets"][0], (1, 2, 3), 6))
        self.assertTrue(hit(ticket("WIDE", [2, 3], 100), (1, 2, 3), 6))
        small["tickets"] = [ticket("WIDE", [2, 3], 100)]
        actual = {"race_id": "test|東京|11", "confirmed_at": "2026-10-04T16:20:00+09:00",
                  "result_status": "final_all_started_no_dead_heat", "source_url": "https://sp.jra.jp/example",
                  "top3": [1, 2, 3], "jra_payout_per_100_yen": {"WIDE:2-3": 330}}
        self.assertEqual(settle(small, actual)["payout_yen"], 330)
    def test_joint_hit_is_not_sum_of_individual_hits(self):
        tickets = [ticket("WIDE", [1, 2], 2500), ticket("WIDE", [1, 3], 2500)]
        rows = [{"order": order, "probability": 1 / 336}
                for order in itertools.permutations(range(1, 9), 3)]
        scenarios = {"race_id": "test|東京|11", "generated_at": "2026-10-04T15:35:00+09:00",
                     "validation_status": "independently_validated", "validation_report_id": "synthetic-test-only",
                     "top3": rows}
        report = forecast(plan(tickets), scenarios)
        # Two wide tickets overlap exactly when 1,2,3 all finish top three.
        self.assertAlmostEqual(report["at_least_one_hit_probability"], 2 * 3 / 28 - 1 / 56)
        self.assertAlmostEqual(report["recover_investment_probability_at_price_floor"], report["at_least_one_hit_probability"])
        self.assertEqual(report["investment_yen"], 5000)
        self.assertEqual(report["unspent_budget_yen"], 0)
        scenarios["top3"].pop()
        with self.assertRaises(ValueError):
            forecast(plan(tickets), scenarios)

    def test_real_world_anchor_loss_and_exact_jra_payout(self):
        tickets = [ticket("WIDE", [2, 8], 1500), ticket("QUINELLA", [2, 8], 1000)]
        results = {"race_id": "test|東京|11", "confirmed_at": "2026-10-04T16:20:00+09:00",
                   "result_status": "final_all_started_no_dead_heat",
                   "source_url": "https://sp.jra.jp/JRADB/example", "top3": [1, 3, 4],
                   "jra_payout_per_100_yen": {}}
        report = settle(plan(tickets), results)
        self.assertFalse(report["ticket_hit"])
        self.assertEqual((report["investment_yen"], report["net_yen"], report["unspent_budget_yen"]),
                         (2500, -2500, 2500))
        results["top3"] = [2, 8, 4]
        results["jra_payout_per_100_yen"] = {"WIDE:2-8": 400, "QUINELLA:2-8": 800}
        report = settle(plan(tickets), results)
        self.assertEqual(report["payout_yen"], 15 * 400 + 10 * 800)
        self.assertTrue(report["recovered_investment"])

    def test_no_unsupported_probability_or_result(self):
        scenarios = {"race_id": "test|東京|11", "generated_at": "2026-10-04T15:35:00+09:00",
                     "validation_status": "exploratory", "validation_report_id": "none", "top3": []}
        with self.assertRaises(ValueError):
            forecast(plan([ticket("WIN", [1], 100)]), scenarios)
        actual = {"race_id": "test|東京|11", "confirmed_at": "2026-10-04T16:20:00+09:00",
                  "result_status": "final_all_started_no_dead_heat", "source_url": "https://sp.jra.jp/example",
                  "top3": [1, 2, 3], "jra_payout_per_100_yen": {}}
        with self.assertRaises(ValueError):
            settle(plan([ticket("WIN", [1], 100)]), actual)  # no official payout provided
        stale = plan([ticket("WIN", [1], 100)])
        stale["odds_observed_at"] = "2026-10-04T15:16:00+09:00"
        scenarios["validation_status"] = "independently_validated"
        with self.assertRaisesRegex(ValueError, "odds are too old"):
            forecast(stale, scenarios)
        over_budget = plan([ticket("WIN", [1], 5100)])
        with self.assertRaisesRegex(ValueError, "exceed"):
            settle(over_budget, actual)


if __name__ == "__main__":
    unittest.main()

