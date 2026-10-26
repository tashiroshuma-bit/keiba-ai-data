import copy
import unittest
import numpy as np
from actor_indices import ActorIndices,targets,HEADS


def field(rid='r1',day=1,available=None):
    return [dict(race_id=rid,horse_number=str(i+1),horse_id=f'jra:h{i}',jockey_id=f'jra:j{i}',
        off_timestamp=f'2024-01-{day:02d}T12:00:00+09:00',
        result_available_at=available or f'2024-01-{day:02d}T18:00:00+09:00',
        finish_position=i+1,field_size=4,track='東京',surface='turf',distance_m=1600,going='良',
        source_url='https://example.test/result',horse_name=f'horse{i}',jockey_name=f'jockey{i}') for i in range(4)]


class ActorIndexTests(unittest.TestCase):
    def test_rider_signal_does_not_become_horse_signal_when_horses_rotate(self):
        rows=[]
        for day in range(1,17):
            rs=field(f'r{day}',day)
            for i,r in enumerate(rs):
                rider=(i+day)%4;r['jockey_id']=f'jra:j{rider}';r['finish_position']=rider+1
            rows+=rs
        model=ActorIndices(rows,'2024-02-01T00:00:00+09:00')
        self.assertGreater(model.entity('jockey','jra:j0')['adjusted_indices']['finish_performance'],50)
        self.assertAlmostEqual(model.entity('horse','jra:h0')['adjusted_indices']['finish_performance'],50,delta=.05)
        self.assertTrue(model.audit['solver_within_1e_4'])
    def test_partial_fields_keep_individual_records_but_not_adjusted_fit(self):
        model=ActorIndices(field()[:2],'2024-02-01T00:00:00+09:00')
        self.assertEqual(model.entity('horse','jra:h0')['overall']['starts'],1)
        self.assertEqual(model.entity('jockey','jra:j0')['overall']['win_rate'],1)
        self.assertIsNone(model.entity('horse','jra:h0')['adjusted_indices'])
        self.assertEqual(model.audit['adjusted_fields'],0)
    def test_asof_and_target_exclusion_and_future_results(self):
        rows=field()+field('late',2,'2024-02-01T00:00:00+09:00')+field('future',9)
        a=ActorIndices(rows,'2024-01-05T00:00:00+09:00')
        self.assertEqual(a.entity('horse','jra:h0')['overall']['starts'],1)
        self.assertEqual(a.audit['adjusted_fields'],1)
        b=ActorIndices(rows,'2024-01-05T00:00:00+09:00',exclude_race_id='r1')
        self.assertIsNone(b.entity('horse','jra:h0')['adjusted_indices'])
        self.assertIsNone(b.entity('jockey','jra:missing')['overall']['win_rate'])

    def test_ties_and_nonfinishers_do_not_gain_artificial_order(self):
        rows=field();rows[2]['finish_position']=2
        y,_=targets(rows)
        np.testing.assert_allclose(y.mean(axis=0),0,atol=1e-12)
        np.testing.assert_array_equal(y[1],y[2])
        rows[3]['finish_position']=None;rows[3]['runner_status']='nonfinisher'
        y,p=targets(rows)
        self.assertEqual(p[3],0)

    def test_horse_and_jockey_are_separate_and_pair_has_own_support(self):
        rows=[]
        for day in range(1,17):
            race=field(f'r{day}',day)
            # Rotate jockeys across horses to identify both sets of components.
            for i,r in enumerate(race):r['jockey_id']=f'jra:j{(i+day)%4}'
            rows+=race
        model=ActorIndices(rows,'2024-02-01T00:00:00+09:00')
        horse=model.entity('horse','jra:h0');jockey=model.entity('jockey','jra:j0')
        self.assertEqual(horse['adjusted_starts'],16)
        self.assertEqual(jockey['adjusted_starts'],16)
        self.assertEqual(jockey['counterpart_count'],4)
        self.assertEqual(horse['adjusted_counterpart_count'],4)
        self.assertGreater(horse['adjusted_indices']['finish_performance'],50)
        self.assertAlmostEqual(jockey['adjusted_indices']['finish_performance'],50,delta=.05)
        self.assertEqual(model.pair('jra:h0','jra:j0')['overall']['starts'],4)
        self.assertIsNone(model.pair('jra:h0','jra:new')['compatibility_index'])

    def test_missing_identity_is_not_neutral_rating(self):
        rows=field();rows[0]['horse_id']='unlinked:r1_1'
        model=ActorIndices(rows,'2024-02-01T00:00:00+09:00')
        self.assertEqual(model.audit['adjusted_fields'],0)
        self.assertIsNone(model.entity('horse','unlinked:r1_1')['adjusted_indices'])
        self.assertIsNone(model.entity('jockey','jra:j1')['adjusted_indices'])
        self.assertEqual(model.entity('jockey','jra:j1')['overall']['starts'],1)

    def test_outcomes_in_current_card_and_market_never_change_indices(self):
        model=ActorIndices(field(),'2024-02-01T00:00:00+09:00')
        card=field('next',8);poison=copy.deepcopy(card)
        for r in poison:r.update(finish_position=99,final_win_odds=999,payouts={'win:1':999})
        self.assertEqual(model.runners(card),model.runners(poison))
        for r in model.runners(card):self.assertFalse(r['used_as_new_probability_features'])

    def test_unsafe_or_duplicate_input_rejected(self):
        rows=field();rows[0]['availability_basis']='assumed_calendar_day_lag_for_research_only'
        with self.assertRaises(ValueError):ActorIndices(rows,'2024-02-01T00:00:00+09:00')
        with self.assertRaises(ValueError):ActorIndices(field()+field(),'2024-02-01T00:00:00+09:00')
        rows=field();rows[0]['horse_id']='horse name'
        with self.assertRaises(ValueError):ActorIndices(rows,'2024-02-01T00:00:00+09:00')


if __name__=='__main__':unittest.main()
