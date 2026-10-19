"""Regression cases discovered by the integrated-data deep audit."""
import json
from pathlib import Path
import tempfile
import unittest

from completion_validation import settlement
from exceptional_results import field_rejection_reasons, ticket_hit
from live_predict import activate
from risk_replay import capital_replay
from strategy import validate_field
from test_improvements import field
from archive_completion import pdf_class_info


def ranked(ranks):
    return [dict(horse_id='jra:h'+str(i),horse_number=str(i),finish_position=rank,
                 runner_status='finished',field_size=len(ranks),off_timestamp='2025-01-01T10:00:00+09:00',
                 distance_m=1600,surface='turf') for i,rank in enumerate(ranks,1)]


class SettlementAuditTests(unittest.TestCase):
    def test_pdf_class_after_off_time_is_recovered_without_result_text(self):
        for level in (1,2,3):
            raw=f'特別競走\n発走14時15分\n3歳以上,{level}勝クラス;負担重量は55\n本 賞 100万円\nGIII優勝馬'
            self.assertEqual(pdf_class_info(raw),(level,'nongraded',None))

    def test_weight_conditions_do_not_create_grade_or_maiden_class(self):
        raw='特別競走\n発走15時25分\n3歳以上,除未出走馬および未勝利馬;負担重量はGI競走1着馬5増,GIII競走1着馬1増\n本賞 100円'
        self.assertEqual(pdf_class_info(raw),(None,'unknown',None))
    def test_two_third_place_horses_are_not_a_winning_pair_or_trio(self):
        rows=ranked([1,2,3,3,5])
        self.assertFalse(ticket_hit(rows,[2,3],'wide'))
        self.assertFalse(ticket_hit(rows,[0,2,3],'trio'))
        self.assertTrue(ticket_hit(rows,[0,2],'wide'))
        self.assertTrue(ticket_hit(rows,[0,1,3],'trio'))
        for row in rows:row['payouts']={}
        answer=settlement(rows,[.01,.01,.49,.48,.01])
        self.assertFalse(answer['wide']['hit']);self.assertFalse(answer['trio']['hit'])
        self.assertTrue(answer['wide']['fully_settled']);self.assertEqual(answer['wide']['payout_yen'],0)

    def test_second_place_tie_can_fill_two_slots_but_not_three(self):
        rows=ranked([1,2,2,2,5])
        self.assertTrue(ticket_hit(rows,[1,2],'wide'))
        self.assertTrue(ticket_hit(rows,[0,1,2],'trio'))
        self.assertFalse(ticket_hit(rows,[1,2,3],'trio'))

    def test_missing_losing_runner_cannot_masquerade_as_complete_field(self):
        rows=ranked([1,2,3,4])[:-1]
        self.assertIn('incomplete_expected_runner_count',field_rejection_reasons(rows))
        for row in rows:row.pop('field_size')
        self.assertIn('missing_expected_runner_count',field_rejection_reasons(rows))

    def test_forward_field_attestation_does_not_override_headcount(self):
        rows=field()
        for row in rows:row['expected_runners']=4
        with self.assertRaisesRegex(ValueError,'runner count'):
            validate_field(rows)

    def test_absent_promotion_approval_is_a_veto(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'model.json').write_text('{}');(p/'report.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'explicit evaluated model promotion approval'):
                activate(p/'model.json',p/'report.json',p/'active')
            self.assertFalse((p/'active').exists())


class CapitalAccountingAuditTests(unittest.TestCase):
    def race(self,rid='x',available='2025-01-01T10:10:00+09:00',payouts=(0,0,0)):
        return dict(race_id=rid,cutoff_timestamp='2025-01-01T09:55:00+09:00',result_available_at=available,
                    markets=[dict(fully_settled=value is not None,stake_yen=100,payout_yen=value) for value in payouts])

    def test_initial_capital_and_race_unit_match_actual_cash_flow(self):
        r,_=capital_replay([self.race()],initial=10000,race_fraction=1,exposure_fraction=1)
        self.assertEqual(r['initial_bankroll'],10000);self.assertEqual(r['bet_races'],1)
        self.assertEqual(r['maximum_single_race_loss'],300);self.assertEqual(r['longest_losing_streak'],1)
        self.assertAlmostEqual(r['maximum_drawdown'],.03)
        self.assertEqual(r['cash_after_known_settlements'],9700)

    def test_drawdown_follows_observation_not_entry_order(self):
        win=self.race('a',available='2025-01-01T12:00:00+09:00',payouts=(2000,))
        loss=self.race('b',available='2025-01-01T11:00:00+09:00',payouts=(0,))
        r,_=capital_replay([win,loss],initial=10000,race_fraction=1,exposure_fraction=1)
        self.assertAlmostEqual(r['maximum_drawdown'],.01)
        self.assertEqual([e['equity_at_cost'] for e in r['equity_events']],[9900,11800])

    def test_partial_race_is_excluded_from_roi_but_known_cash_is_released(self):
        r,_=capital_replay([self.race(payouts=(200,None))],initial=10000,race_fraction=1,exposure_fraction=1)
        self.assertEqual(r['pending_races'],1);self.assertEqual(r['bet_races'],0)
        self.assertIsNone(r['return_pct']);self.assertEqual(r['unresolved_reserved_cost'],100)
        self.assertEqual(r['cash_after_known_settlements'],10000)

    def test_pre_cutoff_settlement_and_duplicate_races_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'must follow'):
            capital_replay([self.race(available='2025-01-01T09:54:00+09:00')])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            capital_replay([self.race(),self.race()])
