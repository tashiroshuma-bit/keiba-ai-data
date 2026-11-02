"""No network/Library dependency: fail-closed research replay unit tests."""
import importlib.util
import math
import random
import sys
import unittest
from collections import defaultdict
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'v50_historical_overlay_audit.py'
spec = importlib.util.spec_from_file_location('v50_historical_overlay_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class HistoricalOverlayAuditTests(unittest.TestCase):
    def test_temperature_softmax_normalized(self):
        p = [.2,.3,.5]
        q = audit.overlay(p,[0.0,0.1,-0.2],.7)
        logits = [(math.log(x)+r)/.7 for x,r in zip(p,[0.0,0.1,-0.2])]
        z = sum(math.exp(x) for x in logits)
        for actual,expected in zip(q,[math.exp(x)/z for x in logits]):
            self.assertAlmostEqual(actual,expected,places=12)
        self.assertAlmostEqual(sum(q),1.0,places=12)
        self.assertEqual(p,[.2,.3,.5])

    def test_reject_bad_probabilities(self):
        for p in ([0.0,.5,.5],[.2,.2,.2],[float('nan'),.2,.8]):
            with self.assertRaises(ValueError):
                audit.overlay(p,[0]*len(p),.7)
        with self.assertRaises(ValueError):
            audit.overlay([.5,.5],[0,0],0)
        with self.assertRaises(ValueError):
            audit.overlay([.5,.5],[0,float('inf')],.7)

    def test_history_day_is_simultaneous_not_intra_day(self):
        history = defaultdict(lambda:defaultdict(list))
        history['2025-01-05']['r1']=[('turf','a','r1',1,3),('turf','b','r2',2,3),('turf','c','r3',3,3)]
        history['2025-01-05']['r2']=[('turf','a','r1',3,3),('turf','b','r2',2,3),('turf','c','r3',1,3)]
        horse=defaultdict(lambda:[0,0.0]);rider=defaultdict(lambda:[0,0.0])
        audit.add_history_day(history['2025-01-05'],horse,rider)
        self.assertEqual(horse['a'][0],2)
        self.assertEqual(rider[('turf','r1')][0],2)
        self.assertAlmostEqual(rider[('turf','r1')][1],0.0)

    def test_invalid_podium_is_rejected(self):
        with self.assertRaises(ValueError):
            audit.race_scores(['1','2','3'],['1','1','2'],[.5,.3,.2],[.5,.3,.2])

    def test_paired_scores_and_cluster_bootstrap(self):
        a = audit.race_scores(['1','2','3'],['2','1','3'],[.5,.3,.2],[.2,.6,.2])
        self.assertEqual(a['base']['winner_hit'],0)
        self.assertEqual(a['overlay']['winner_hit'],1)
        self.assertEqual(a['base']['unordered_top3'],1)
        rows=[{'date':'2025-01-05','runners':3,'jockey_residual_covered':2,**a},
              {'date':'2025-01-06','runners':3,'jockey_residual_covered':3,**a}]
        summary=audit.aggregate(rows)
        self.assertEqual(summary['races'],2)
        self.assertEqual(summary['overlay_minus_base']['winner_hit'],1)
        ci=audit.date_bootstrap(rows,draws=100,seed=7)
        self.assertEqual(ci['winner_hit'],[1.0,1.0])

    def test_ineligible_status_is_counted_not_scored(self):
        race={'race_id':'r1','date':'2025-01-05','horse_numbers':['1','2','3'],
              'baseline':{'marginal_probabilities':[[.5],[.3],[.2]],
                           'target':['1','2','3']}}
        rows,excluded=audit.evaluate([race],{'r1':('2025-01-05','turf','requires_review')},
                                     {},{},temperature=.7)
        self.assertEqual(rows,[])
        self.assertEqual(excluded[0]['reason'],'requires_review')

    def test_two_day_lag_excludes_border_day(self):
        race={'race_id':'r1','date':'2025-01-05','horse_numbers':['1','2','3'],
              'baseline':{'marginal_probabilities':[[.5],[.3],[.2]],
                           'target':['1','2','3']}}
        roster={'r1':('2025-01-05','turf','validated_result')}
        per={'r1':{'1':('rider1',1),'2':('rider2',2),'3':('rider3',3)}}
        # Jan 3 is the cutoff (Jan 5 minus 2 days), and is excluded.
        day={'past': [('turf','horse1','rider1',1,3),
                      ('turf','horse2','rider2',2,3),
                      ('turf','horse3','rider3',3,3)]}
        included,_=audit.evaluate([race],roster,per,{'2025-01-02':day},.7)
        excluded,_=audit.evaluate([race],roster,per,{'2025-01-03':day},.7)
        self.assertEqual(included[0]['jockey_residual_covered'],3)
        self.assertEqual(excluded[0]['jockey_residual_covered'],0)

    def test_softmax_and_PL_rank_top3_agree(self):
        # The v50 ticket engine's Plackett-Luce argmax is the top 3 p1 in order.
        from itertools import permutations
        rng=random.Random(101)
        for n in range(3,11):
            p=[rng.random() for _ in range(n)]
            p=[v/sum(p) for v in p]
            pick=tuple(sorted(range(n),key=lambda i:-p[i])[:3])
            exact=max(permutations(range(n),3),
                      key=lambda t:p[t[0]]*p[t[1]]/(1-p[t[0]])*p[t[2]]/(1-p[t[0]]-p[t[1]]))
            self.assertEqual(pick,exact)


if __name__ == '__main__':
    unittest.main()
