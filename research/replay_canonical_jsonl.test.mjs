import test from 'node:test';
import assert from 'node:assert/strict';
import {pairedReplay} from './replay_canonical_jsonl.mjs';
const base={coefficients:[1],mean:[0],scale:[1]};
const improved={coefficients:[-1],mean:[0],scale:[1]};
const rows=[{raceId:'R1',raceDate:'2025-11-15',asOfDate:'2025-11-14',officialWinnerNumber:3,runners:[
 {number:1,features:[1],latestHistoryDate:'2025-11-01'},
 {number:2,features:[0]},{number:3,features:[-1]}]}];
test('same-race paired evaluation uses independent winner label',()=>{
 const r=pairedReplay(rows,{baseline:base,corrected:improved});
 assert.equal(r.races,1);assert.equal(r.baseline.top1Hits,0);assert.equal(r.corrected.top1Hits,1);
 assert.ok(r.delta.logloss<0);assert.ok(r.delta.brier<0);
});
test('reject label injection and duplicate races',()=>{
 assert.throws(()=>pairedReplay([{...rows[0],runners:[{...rows[0].runners[0],finishOrder:1},...rows[0].runners.slice(1)]}],{baseline:base,corrected:improved}),/target result/);
 assert.throws(()=>pairedReplay([...rows,...rows],{baseline:base,corrected:improved}),/duplicate race/);
});
