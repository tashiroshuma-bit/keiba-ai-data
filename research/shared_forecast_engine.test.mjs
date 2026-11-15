import test from 'node:test';
import assert from 'node:assert/strict';
import {forecastRace,evaluateRace,summarize} from './shared_forecast_engine.mjs';
const input={raceId:'202505010101',asOfDate:'2025-04-30',raceDate:'2025-05-01',
  runners:[{number:1,features:[1],latestHistoryDate:'2025-04-20'},
           {number:2,features:[0]},{number:3,features:[-1]}],
  model:{coefficients:[1],mean:[0],scale:[1]}};
test('shared prediction and retrospective scoring',()=>{
 const p=forecastRace(input);
 assert.equal(p.winnerNumber,1);
 assert.ok(Math.abs(p.predictions.reduce((a,r)=>a+r.p1,0)-1)<1e-12);
 const m=summarize([evaluateRace(p,{raceId:input.raceId,resultDate:'2025-05-01',winnerNumber:1})]);
 assert.equal(m.top1Accuracy,1);assert.ok(m.logloss>0);assert.ok(m.brier>0);
});
test('reject same-day history and target result leakage',()=>{
 assert.throws(()=>forecastRace({...input,runners:input.runners.map((r,i)=>i===0?{...r,latestHistoryDate:'2025-05-01'}:r)}),/leakage/);
 assert.throws(()=>forecastRace({...input,asOfDate:'2025-05-01'}),/precede/);
});
test('reject wrong race label',()=>{
 assert.throws(()=>evaluateRace(forecastRace(input),{raceId:'other',resultDate:'2025-05-01',winnerNumber:1}),/mismatch/);
});
