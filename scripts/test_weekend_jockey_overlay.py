import base64,json,unittest,zlib
from pathlib import Path
from recalculate_weekend_riders import ROOT,RankModel,card_rows,decode_odds,digest,official_rider,recalculate
from jockey_overlay_ticket_math import calculate_model

class WeekendRiderTests(unittest.TestCase):
    def test_unlinked_foreign_rider_is_not_trainer_anchor(self):
        row={'text':'ミエルモーサ 牝2 / 黒鹿 前4走 C.デムーロ(55.0) 松下武士 (栗東)',
             'links':[{'text':'松下武士','onclick':"doAction('/JRADB/accessC.html','sw05cmk011149/E8')"}]}
        self.assertEqual(official_rider(row),('C.デムーロ',None,None))

    def test_rider_link_has_source_code_and_missing_name_fails(self):
        row={'text':'騎手未定','links':[]}
        with self.assertRaises(ValueError):official_rider(row)
        row['links']=[{'text':'C.ルメール','onclick':"doAction('/JRADB/accessK.html','sw04kmk015339/72')"}]
        self.assertEqual(official_rider(row)[::2],('C.ルメール','5339'))

    def test_excluded_horse_footer_does_not_inflate_field(self):
        horse={'text':'対象馬','cells':[{'class':['uma']}],'links':[{'href':'https://sp.jra.jp/JRADB/accessU.html?CNAME=x'}]}
        footer={'text':'除外馬一覧','cells':[{'class':[]}],'links':[{'href':'https://sp.jra.jp/JRADB/accessU.html?CNAME=y'}]}
        self.assertEqual(card_rows({'rows':[horse,footer]}),[horse])

    def test_predicted_odds_never_become_current_odds(self):
        data={'odds':{'1':{'01':['2.5','0',1]}}}
        body=base64.b64encode(zlib.compress(json.dumps(data).encode())).decode()
        response='odds_callback('+json.dumps({'status':'yoso','data':body})+')'
        result=decode_odds({'url':'https://race.sp.netkeiba.com/','at':'2026-10-31T03:00:00+09:00','sha256':'a'*64,'text':response})
        self.assertEqual(result['status'],'yoso')

    def test_unpublished_numbers_remain_names_in_tickets(self):
        horses=[{'number':None,'display_key':'馬番未定:'+n,'name':n} for n in ('A','B','C')]
        result=calculate_model(horses,[.5,.3,.2])
        self.assertEqual(result['priority']['single']['tickets'][0]['numbers'],['馬番未定:A'])
        self.assertAlmostEqual(sum(h['p3'] for h in result['horses']),1)

    def test_saved_full_weekend_reproduces_from_sources(self):
        folder=ROOT/'reports/weekend_20261031_1101'
        paths={
            'saturday':ROOT/'operations/predictions/2026-10-31/preoff_20261031T011832+0900.json',
            'sunday':ROOT/'operations/predictions/2026-11-01/preoff_20261031T011832+0900.json',
            'evidence':folder/'ALL_FLAT_CARD_ODDS_20261030T183252Z.json',
            'riders':folder/'OBSERVED_JOCKEY_FEATURES_20261031T033200.json'}
        expected=json.loads((folder/'ALL_FLAT_RIDER_RECALC_20261031T033252.json').read_text())
        self.assertEqual({key:digest(path) for key,path in paths.items()},expected['source_file_sha256'])
        inputs={key:json.loads(path.read_text()) for key,path in paths.items()}
        model=RankModel.from_dict(json.loads((ROOT/'keiba_v48/reports/exact_rank/model_lag7.json').read_text()))
        actual=recalculate({inputs['saturday']['date']:inputs['saturday'],inputs['sunday']['date']:inputs['sunday']},inputs['evidence'],inputs['riders'],model)
        self.assertEqual(actual['race_failures'],[])
        self.assertEqual(len(actual['races']),46)
        self.assertEqual(sum(len(r['runners']) for r in actual['races']),599)
        self.assertEqual(sum(h['jockey_id'] is not None for r in actual['races'] for h in r['runners']),568)
        def rounded(value):
            if isinstance(value,float):return round(value,10)
            if isinstance(value,dict):return {k:rounded(v) for k,v in value.items()}
            if isinstance(value,list):return [rounded(v) for v in value]
            return value
        self.assertEqual(rounded(actual['races']),rounded(expected['races']))

if __name__=='__main__':unittest.main()
