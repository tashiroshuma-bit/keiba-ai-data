// Produce a real prediction from an observed, pre-off snapshot using approved V51 winner-stage coefficients.
// The source snapshot must contain 31 observed features, not target-race results.
// CLI: node research/predict_v51_js.mjs snapshot.json standard_v51_model.json output.json
import fs from 'node:fs';
import {softmax} from './shared_forecast_engine.mjs';
export function predictV51(snapshot,model){
  if(model.production_enabled!==true || model.feature_count!==31 || !Array.isArray(model.stage_coefficients)||model.stage_coefficients.length!==3)throw Error('approved V51 model required');
  const date=snapshot.forecast_asof;
  if(!date || !Array.isArray(snapshot.races)||!snapshot.races.length)throw Error('valid preoff snapshot required');
  const outputs=[];
  for(const race of snapshot.races){
    if(!(Date.parse(date)<Date.parse(race.race_off_at)))throw Error('forecast not before off');
    const runners=[...race.horses].sort((a,b)=>a.number-b.number);
    if(runners.length<3 || new Set(runners.map(x=>x.number)).size!==runners.length)throw Error('invalid field');
    const z=model.stage_coefficients.map(coef=>runners.map(r=>{
      if(!Array.isArray(r.feature_values)||r.feature_values.length!==31)throw Error('31 features required');
      if(r.latest_history_date && !(r.latest_history_date<race.race_off_at.slice(0,10)))throw Error('future history leakage');
      return r.feature_values.reduce((a,v,i)=>{
        if(!Number.isFinite(v)||!(model.feature_scale[i]>0))throw Error('invalid feature');
        return a+(v-model.feature_mean[i])/model.feature_scale[i]*coef[i];
      },0);
    }));
    // V51 full calibration and joint podium inference are performed by official Python entrypoint.
    // This JS runner deliberately outputs winner-stage UNCALIBRATED research probabilities only.
    const p=softmax(z[0]);
    outputs.push({race:race.race,race_off_at:race.race_off_at,
      winner_probabilities:runners.map((r,i)=>({number:r.number,name:r.name,probability:p[i]})),
      winner_pick:runners[p.indexOf(Math.max(...p))].number});
  }
  return {schema:'jra-v51-js-uncalibrated-winner-research-v1',status:'RESEARCH_NOT_OFFICIAL',forecast_asof:date,races:outputs};
}
if(process.argv[1] && import.meta.url===new URL('file://'+process.argv[1]).href){
 const [input,modelPath,out]=process.argv.slice(2);
 if(!input||!modelPath||!out)throw Error('Usage: node research/predict_v51_js.mjs snapshot.json standard_v51_model.json output.json');
 const answer=predictV51(JSON.parse(fs.readFileSync(input)),JSON.parse(fs.readFileSync(modelPath)));
 fs.writeFileSync(out,JSON.stringify(answer,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({races:answer.races.length,output:out,status:answer.status}));
}
