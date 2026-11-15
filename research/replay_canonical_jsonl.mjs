// Offline replay adapter for canonical point-in-time race snapshots.
// Input: JSONL, each row {raceId,raceDate,asOfDate,officialWinnerNumber,runners:[{number,features,latestHistoryDate}]}
// Models: JSON {baseline:{coefficients,mean,scale},corrected:{...}}.
// Explicitly refuses retrospective results as forecast inputs.
import fs from 'node:fs';
import {forecastRace,evaluateRace,summarize} from './shared_forecast_engine.mjs';
function parseLines(path){return fs.readFileSync(path,'utf8').split(/\r?\n/).filter(Boolean).map((s,i)=>{try{return JSON.parse(s)}catch(e){throw Error('bad JSONL line '+(i+1)+': '+e.message)}})}
export function pairedReplay(rows,models){
  if(!models.baseline||!models.corrected)throw Error('two model coefficients required');
  const paired=[];const ids=new Set();
  for(const row of rows){
    if(ids.has(row.raceId))throw Error('duplicate race');ids.add(row.raceId);
    if(!Array.isArray(row.runners)||row.runners.some(r=>'finishOrder' in r||'targetResult' in r||'officialWinnerNumber' in r))
      throw Error('target result mixed into feature rows');
    const outcomes={raceId:row.raceId,resultDate:row.raceDate,winnerNumber:row.officialWinnerNumber};
    const shared={raceId:row.raceId,raceDate:row.raceDate,asOfDate:row.asOfDate,runners:row.runners};
    const a=evaluateRace(forecastRace({...shared,model:models.baseline}),outcomes);
    const b=evaluateRace(forecastRace({...shared,model:models.corrected}),outcomes);
    paired.push({raceId:row.raceId,baseline:a,corrected:b});
  }
  const baseline=summarize(paired.map(p=>p.baseline));
  const corrected=summarize(paired.map(p=>p.corrected));
  return {races:paired.length,baseline,corrected,delta:{
    top1Accuracy:corrected.top1Accuracy-baseline.top1Accuracy,
    logloss:corrected.logloss-baseline.logloss,
    brier:corrected.brier-baseline.brier},paired};
}
if(process.argv[1] && import.meta.url===new URL('file://'+process.argv[1]).href){
  const [rowsPath,modelsPath,outputPath]=process.argv.slice(2);
  if(!rowsPath||!modelsPath||!outputPath)throw Error('Usage: node research/replay_canonical_jsonl.mjs snapshots.jsonl models.json results.json');
  const result=pairedReplay(parseLines(rowsPath),JSON.parse(fs.readFileSync(modelsPath,'utf8')));
  fs.writeFileSync(outputPath,JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({races:result.races,baseline:result.baseline,corrected:result.corrected,delta:result.delta}));
}
