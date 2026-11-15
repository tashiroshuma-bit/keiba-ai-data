import test from 'node:test';
import assert from 'node:assert/strict';
import {predictV51} from './predict_v51_js.mjs';
const model={production_enabled:true,feature_count:31,feature_mean:Array(31).fill(0),feature_scale:Array(31).fill(1),
 calibration:{group_entropy_cutoff:.94,group_favorite_cutoff:.25,global_stage_temperatures:{'2':1,'3':1},winner_entropy_confidence_groups:{'high_entropy__close_field':{temp:1},'high_entropy__clear_favorite':{temp:1},'other_entropy__close_field':{temp:1},'other_entropy__clear_favorite':{temp:1}}},\n stage_coefficients:[Array.from({length:31},(_,i)=>i===0?1:0),Array(31).fill(0),Array(31).fill(0)]};
const snap={forecast_asof:'2025-01-01T00:00:00+09:00',races:[{race:'R1',race_off_at:'2025-01-02T12:00:00+09:00',
 horses:[1,2,3].map((n)=>({number:n,name:'horse'+n,feature_values:[n,...Array(30).fill(0)]}))}]};
test('predicts winner probabilities from 31-feature preoff snapshot',()=>{
 const p=predictV51(snap,model);assert.equal(p.races.length,1);
 assert.equal(p.races[0].winner_pick,3);\n assert.equal(p.races[0].ordered_top3.length,3);\n for(const k of ['p1','p2','p3'])assert.ok(Math.abs(p.races[0].runners.reduce((a,r)=>a+r[k],0)-1)<1e-12);\n assert.ok(Math.abs(p.races[0].joint_mass-1)<1e-12);
 assert.ok(Math.abs(p.races[0].winner_probabilities.reduce((a,r)=>a+r.probability,0)-1)<1e-12);
});
test('rejects postoff forecasts',()=>assert.throws(()=>predictV51({...snap,forecast_asof:'2025-01-03T00:00:00+09:00'},model),/before off/));
test('rejects invalid model',()=>assert.throws(()=>predictV51(snap,{...model,production_enabled:false}),/approved/));
