import test from 'node:test';
import assert from 'node:assert/strict';
import {predictV51} from './predict_v51_js.mjs';
const model={production_enabled:true,feature_count:31,feature_mean:Array(31).fill(0),feature_scale:Array(31).fill(1),
 stage_coefficients:[Array.from({length:31},(_,i)=>i===0?1:0),Array(31).fill(0),Array(31).fill(0)]};
const snap={forecast_asof:'2025-01-01T00:00:00+09:00',races:[{race:'R1',race_off_at:'2025-01-02T12:00:00+09:00',
 horses:[1,2,3].map((n)=>({number:n,name:'horse'+n,feature_values:[n,...Array(30).fill(0)]}))}]};
test('predicts winner probabilities from 31-feature preoff snapshot',()=>{
 const p=predictV51(snap,model);assert.equal(p.races.length,1);
 assert.equal(p.races[0].winner_pick,3);
 assert.ok(Math.abs(p.races[0].winner_probabilities.reduce((a,r)=>a+r.probability,0)-1)<1e-12);
});
test('rejects postoff forecasts',()=>assert.throws(()=>predictV51({...snap,forecast_asof:'2025-01-03T00:00:00+09:00'},model),/before off/));
test('rejects invalid model',()=>assert.throws(()=>predictV51(snap,{...model,production_enabled:false}),/approved/));
