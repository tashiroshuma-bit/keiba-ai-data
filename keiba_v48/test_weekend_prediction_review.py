import importlib.util
import itertools
import unittest
import sys
import json
import hashlib
from pathlib import Path

spec=importlib.util.spec_from_file_location('weekend',Path(__file__).resolve().parents[1]/'scripts/weekend_prediction_review.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WeekendReviewTest(unittest.TestCase):
    def test_revision_evidence_and_new_probabilities(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from revise_research_shadow import build_revision
        base=json.dumps({'races':[{'race':'東京1R','models':{'A':{'horses':[
            {'no':1,'p1':.4},{'no':2,'p1':.3},{'no':3,'p1':.2},{'no':4,'p1':.1}]}}}]}).encode()
        request={'race':'東京1R','parent_prediction_sha256':hashlib.sha256(base).hexdigest(),
            'parent_variant':'base','variant':'base','frozen_at':'2026-11-01T09:00:00+09:00',
            'scheduled_start':'2026-11-01T10:00:00+09:00',
            'nonstarter_evidence':[{'no':1,'source_url':'https://example.com/test-fixture','observed_at':'2026-11-01T08:59:00+09:00'}]}
        result=build_revision(base,request)['races'][0]['models']['A']
        self.assertAlmostEqual(result['horses'][0]['p1'],.5)
        self.assertEqual(len(result['wide_all_pairs']),3)
        self.assertIsNone(result['wide_selection'])
        for p in ('p1','p2','p3'):self.assertAlmostEqual(sum(h[p] for h in result['horses']),1)
        request['frozen_at']='2026-11-01T10:01:00+09:00'
        with self.assertRaises(ValueError):build_revision(base,request)

    def test_scratch_recomputes_placing_and_joint_mass(self):
        w=m.normalized({1:.4,2:.3,3:.2,4:.1},nonstarters=[1])
        self.assertNotIn(1,w)
        self.assertAlmostEqual(w[2],.5)
        marginal,triples=m.rank_distribution(w)
        self.assertAlmostEqual(sum(triples.values()),1)
        for k in range(3):self.assertAlmostEqual(sum(p[k] for p in marginal.values()),1)
        for p in marginal.values():self.assertAlmostEqual(sum(p),1)

    def test_wide_union_is_not_sum(self):
        _,triples=m.rank_distribution({1:1,2:1,3:1,4:1})
        a=m.wide_union(triples,[(1,2)])
        b=m.wide_union(triples,[(1,3)])
        both=m.wide_union(triples,[(1,2),(1,3)])
        self.assertAlmostEqual(a,.5)
        self.assertAlmostEqual(a+b,1)
        self.assertAlmostEqual(both,.75)
        self.assertAlmostEqual(m.wide_union(triples,itertools.combinations(range(1,5),2)),1)

    def test_third_tie_does_not_make_tied_pair_wide_winner(self):
        result={'top3':[[1,9],[2,11],[3,10],[3,14]],'payouts':{
            'trio':{'9-10-11':18620,'9-11-14':1920},'trifecta':{'9-11-10':146590,'9-11-14':22070}}}
        self.assertEqual(m.evaluate({9:.5,11:.3,14:.15,10:.05},result)['ordered_hit'],1)
        self.assertEqual(m.evaluate({9:.5,14:.3,10:.15,11:.05},result)['unordered_hit'],0)
        paid=m.settle([{'numbers':[10,14]},{'numbers':[9,14]},{'numbers':[5,9]}],{'9-14':580},[5])
        self.assertEqual(paid['hypothetical_payout_yen'],580)
        self.assertEqual(paid['hypothetical_refund_yen'],100)
        self.assertEqual(paid['hit_tickets'],1)

    def test_silent_branch_change_rejected(self):
        parent={'prediction_sha256':'abc','variant':'market20'}
        with self.assertRaises(ValueError):m.validate_revision(parent,{'parent_prediction_sha256':'abc','variant':'base'})
        with self.assertRaises(ValueError):m.validate_revision(parent,{'parent_prediction_sha256':'xyz','variant':'market20'})
        m.validate_revision(parent,{'parent_prediction_sha256':'abc','variant':'base','variant_switch_reason':'Explicit comparison'})

    def test_invalid_weights(self):
        for w in ({1:float('nan')},{1:-1},{1:0}):
            with self.assertRaises(ValueError):m.normalized(w)


if __name__=='__main__':unittest.main()
