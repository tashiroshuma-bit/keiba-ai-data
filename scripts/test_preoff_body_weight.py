import copy
import datetime as dt
import unittest
from preoff_body_weight import attach, markdown, records_from_card
from apply_preoff_body_weights import apply

NOW=dt.datetime.fromisoformat('2026-11-01T15:15:00+09:00')
OFF='2026-11-01T15:40:00+09:00'


class BodyWeightTest(unittest.TestCase):
    def setUp(self):
        self.horse={'number':1,'name':'試験馬','horse_profile_url':'https://example.org/horse/123', 'starts':4}
        self.race={'date':'2026-11-01','race':'東京11R','off_at':OFF,'runners':[self.horse],
                   'models':{'A':{'p1':[.2,.3,.5]}}}
        self.record=dict(number=1,name='試験馬',body_weight_kg=486,change_kg=18,
            basis='announced_preoff',observed_at=NOW.isoformat(),source_url='https://race.sp.netkeiba.com/race/shutuba.html?race_id=1',
            source_sha256='a'*64,hash_basis='observed_text_export')

    def test_reference_uses_previous_mass_not_current_denominator_and_preserves_model(self):
        out=attach(self.race,[self.record],NOW,True)
        ref=out['runners'][0]['body_weight_reference']
        self.assertAlmostEqual(ref['change_pct'],100*18/468)
        self.assertEqual(out['models'],self.race['models'])
        self.assertNotIn('body_weight_reference',self.horse)
        self.assertFalse(ref['probability_adjustment_applied'])

    def test_missing_is_provisional_and_final_gate_fails(self):
        self.assertIn('暫定',markdown(attach(self.race,[],NOW)))
        with self.assertRaises(ValueError):attach(self.race,[],NOW,True)

    def test_result_screen_not_allowed(self):
        for value in ('https://race.sp.netkeiba.com/?pid=race_result&race_id=1','https://race.netkeiba.com/race/result.html?id=1'):
            with self.subTest(url=value), self.assertRaises(ValueError):
                attach(self.race,[dict(self.record,source_url=value)],NOW)

    def test_old_day_and_future_and_postoff_observations_rejected(self):
        for value in ('2026-10-31T15:00:00+09:00','2026-11-01T15:16:00+09:00','2026-11-01T15:40:00+09:00'):
            with self.subTest(at=value),self.assertRaises(ValueError):
                attach(self.race,[dict(self.record,observed_at=value)],NOW)

    def test_cannot_create_final_reference_after_race(self):
        with self.assertRaises(ValueError):attach(self.race,[self.record],dt.datetime.fromisoformat(OFF),True)

    def test_carried_weight_and_nan_rejected(self):
        for value in (55,True,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                attach(self.race,[dict(self.record,body_weight_kg=value)],NOW)

    def test_wrong_name_number_or_duplicate_rejected(self):
        for r in (dict(self.record,name='別馬'),dict(self.record,number=2)):
            with self.assertRaises(ValueError):attach(self.race,[r],NOW)
        with self.assertRaises(ValueError):attach(self.race,[self.record,self.record],NOW)

    def test_initial_start_does_not_impute_change_zero(self):
        out=attach(self.race,[dict(self.record,first_start=True,change_kg=None)],NOW)
        self.assertIsNone(out['runners'][0]['body_weight_reference']['change_pct'])
        self.assertIn('初出走',markdown(out))
        with self.assertRaises(ValueError):attach(self.race,[dict(self.record,change_kg=None)],NOW)

    def test_zero_change_not_automatically_good_and_absence_not_zero(self):
        zero=attach(self.race,[dict(self.record,change_kg=0)],NOW)
        self.assertEqual(zero['runners'][0]['body_weight_reference']['change_pct'],0)
        absent=attach(self.race,[],NOW)
        self.assertNotIn('change_pct',absent['runners'][0]['body_weight_reference'])

    def test_history_requires_same_horse_and_preobservation_evidence(self):
        h=dict(horse_profile_url=self.horse['horse_profile_url'],body_weight_kg=470,
            source_url='https://example.org/result/1',source_sha256='b'*64,
            off_at='2026-10-01T15:00:00+09:00',observed_at='2026-10-02T00:00:00+09:00')
        out=attach(self.race,[dict(self.record,history=[h])],NOW)
        self.assertEqual(out['runners'][0]['body_weight_reference']['recent_range_kg'],[470,470])
        for bad in (dict(h,horse_profile_url='https://example.org/horse/other'),dict(h,observed_at='2026-11-02T00:00:00+09:00')):
            with self.assertRaises(ValueError):attach(self.race,[dict(self.record,history=[bad])],NOW)

    def test_parser_reads_current_weight_column_not_assigned_weight(self):
        snap={'at':NOW.isoformat(),'url':self.record['source_url'],'sha256':'c'*64,'rows':[
            {'cells':[{'class':['Umaban'],'text':'1'},{'class':['Jockey'],'text':'55.0'}, {'class':['Weight'],'text':'486 (+18)'}],
             'links':[{'href':'https://db.netkeiba.com/horse/123','text':'試験馬のデータベース'}]}]}
        rs=records_from_card(snap,[self.horse],OFF)
        self.assertEqual(rs[0]['body_weight_kg'],486)
        out=attach(self.race,rs,NOW)
        self.assertTrue(out['preoff_body_weight_review']['all_active_observed'])
        snap['rows'][0]['cells'][0]['text']='2'
        with self.assertRaises(ValueError):records_from_card(snap,[self.horse],OFF)

    def test_runner_sets_and_date_scope_in_revision(self):
        observation={'races':[{'date':'2026-11-01','race':'東京11R','runners':[self.record]}]}
        out=apply({'races':[self.race]},observation,NOW,True,'2026-11-01')
        self.assertEqual(out['races'][0]['models'],self.race['models'])
        with self.assertRaises(ValueError):apply({'races':[self.race]},observation,NOW,date='2026-11-02')

    def test_mobile_card_number_cell_is_frame_colored_but_prints_horse_number(self):
        snap={'at':NOW.isoformat(),'url':self.record['source_url'],'sha256':'c'*64,'rows':[
            {'cells':[{'class':['Waku6'],'text':'11'},{'class':['Weight'],'text':'486(+18)'}],
             'links':[{'href':'https://db.netkeiba.com/horse/123','text':'試験馬のデータベース'}]}]}
        horse=dict(self.horse,number=11)
        record=records_from_card(snap,[horse],OFF)[0]
        self.assertEqual(record['number'],11)
        self.assertEqual(record['body_weight_kg'],486)


if __name__=='__main__':unittest.main()
