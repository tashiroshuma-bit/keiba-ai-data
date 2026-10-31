import copy
import unittest
from refresh_sunday_20261101 import refresh, markets, timestamp, card_export
from jockey_overlay_ticket_math import calculate_model

class SundayRefreshTest(unittest.TestCase):
    def setUp(self):
        self.now=timestamp('2026-11-01T09:00:00+09:00')
        horses=[dict(number=None,display_key='馬番未定:'+name,frame=None,name=name,starts=2,
            horse_profile_url='https://example.org/'+name) for name in ('甲','乙','丙')]
        self.race=dict(date='2026-11-01',race='東京1R',off_at='2026-11-01T10:00:00+09:00',
            runners=horses,models={k:calculate_model(horses,[.5,.3,.2]) for k in 'ABCD'})
        rows=[]
        for i,name in enumerate(('甲','乙','丙'),1):
            rows.append(dict(text=name,cells=[{'class':['Waku1'],'text':str(i)},{'class':['Weight'],'text':''}],
                links=[{'text':name+'のデータベース','href':f'https://db.netkeiba.com/horse/{i}/'},
                       {'text':'騎手','href':f'https://db.netkeiba.com/jockey/{i}/'}]))
        self.old=dict(rows=copy.deepcopy(rows))
        self.obs=dict(netkeiba=dict(url='https://race.sp.netkeiba.com/race/shutuba.html?id=1',
            sha256='a'*64,at=self.now.isoformat(),rows=rows),odds={'error':'not observed'})

    def test_published_numbers_join_by_name_not_row_order_and_probabilities_unchanged(self):
        self.obs['netkeiba']['rows'].reverse()
        r=refresh(self.race,self.obs,self.old,self.now)
        self.assertEqual([(h['number'],h['name']) for h in r['runners']],[(1,'甲'),(2,'乙'),(3,'丙')])
        self.assertEqual([h['p1'] for h in r['models']['A']['horses']],[.5,.3,.2])
        self.assertEqual(r['models']['A']['ordered_top3'],[1,2,3])
        self.assertIsNone(self.race['runners'][0]['number'])
        self.assertFalse(r['preoff_body_weight_review']['all_active_observed'])

    def test_duplicate_numbers_and_roster_mismatch_rejected(self):
        for mutation in ('duplicate','missing'):
            obs=copy.deepcopy(self.obs)
            if mutation=='duplicate':obs['netkeiba']['rows'][1]['cells'][0]['text']='1'
            else:obs['netkeiba']['rows'].pop()
            with self.assertRaises(ValueError):refresh(self.race,obs,self.old,self.now)

    def test_other_horselist_tables_are_not_entry_rows(self):
        html=b'<title>Entry</title><table class="Shutuba_Table"><tr class="HorseList"><td class="Weight"></td></tr></table><table><tr class="HorseList"><td>pace template</td></tr></table>'
        out=card_export(html,{'url':'https://example.org/card'})
        self.assertEqual(len(out['rows']),1)
        self.obs['netkeiba']['rows'].append({'text':'pace','cells':[],'links':[]})
        self.assertEqual(len(refresh(self.race,self.obs,self.old,self.now)['runners']),3)

    def test_new_link_for_previously_unlinked_rider_keeps_unlinked_prior(self):
        old=self.old['rows'][0];old['links'].pop()
        info={'class':['Horse_Info'],'text':'甲のデータベース 客員騎手 56.0'}
        old['cells'].append(copy.deepcopy(info));self.obs['netkeiba']['rows'][0]['cells'].append(copy.deepcopy(info))
        r=refresh(self.race,self.obs,self.old,self.now)
        self.assertIn('prior identity/history remains unlinked',r['runners'][0]['current_rider_link_note'])
        self.obs['netkeiba']['rows'][0]['cells'][-1]['text']='甲のデータベース 別騎手 56.0'
        with self.assertRaises(ValueError):refresh(self.race,self.obs,self.old,self.now)

    def test_rider_change_withdrawal_and_late_observation_rejected(self):
        for mutation in ('rider','withdrawal','late','yesterday'):
            obs=copy.deepcopy(self.obs)
            if mutation=='rider':obs['netkeiba']['rows'][0]['links'][1]['href']='https://db.netkeiba.com/jockey/other/'
            if mutation=='withdrawal':obs['netkeiba']['rows'][0]['text']+='取消'
            if mutation=='late':obs['netkeiba']['at']=self.race['off_at']
            if mutation=='yesterday':obs['netkeiba']['at']='2026-10-31T09:00:00+09:00'
            with self.subTest(case=mutation),self.assertRaises(ValueError):refresh(self.race,obs,self.old,self.now)

    def test_market_probability_mass_and_place_cutoff(self):
        r=refresh(self.race,self.obs,self.old,self.now);m=markets(r,'A')
        for kind in ('単勝','馬連','3連複','馬単','3連単','枠連'):
            self.assertAlmostEqual(sum(m[kind].values()),1)
        self.assertAlmostEqual(sum(m['複勝'].values()),2)
        self.assertAlmostEqual(sum(m['ワイド'].values()),3)

if __name__=='__main__':unittest.main()
