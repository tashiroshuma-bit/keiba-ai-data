"""Deterministic research-only ticket ranking; no prediction/model mutation."""
import unittest
from jockey_overlay_ticket_math import calculate_model, threshold


class StableTicketTieTests(unittest.TestCase):
    def test_numerical_noise_does_not_flip_name_order(self):
        names = ("ロイヤルヴェイズ", "キャナルタウン", "テストホース", "ホースデルタ")
        horses = [{"name": name, "number": "馬番未定:" + name} for name in names]
        first = calculate_model(horses, [.300000000000001, .3, .25, .15])
        second = calculate_model(horses, [.3, .300000000000001, .25, .15])
        self.assertEqual(first["marks"], second["marks"])
        self.assertEqual(first["ordered_top3"], second["ordered_top3"])
        for kind in ("single", "quinella", "trio"):
            self.assertEqual(
                [x["numbers"] for x in first["priority"][kind]["tickets"]],
                [x["numbers"] for x in second["priority"][kind]["tickets"]])
        self.assertEqual(first["marks"]["◎"], "馬番未定:キャナルタウン")
        self.assertFalse(first["research_stake_yen"])

    def test_probability_is_not_quantized(self):
        items = {("A",): .300000000000001, ("B",): .3, ("C",): .4}
        selected = threshold(items, .7)
        self.assertEqual([x["numbers"] for x in selected["tickets"]],
                         [["C"], ["A"]])
        self.assertEqual(selected["tickets"][1]["p"], .300000000000001)

    def test_material_difference_still_controls_rank(self):
        horses = [{"name": str(i), "number": i} for i in range(4)]
        result = calculate_model(horses, [.3, .30000001, .25, .14999999])
        self.assertEqual(result["marks"]["◎"], 1)


if __name__ == "__main__":
    unittest.main()
