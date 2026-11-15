// One race-normalized inference engine shared by historical replay and future forecasts.
// No outcomes are accepted as model inputs.
export function softmax(values) {
  if (!Array.isArray(values) || values.length < 3 || values.some(v => !Number.isFinite(v))) throw Error("invalid logits");
  const top=Math.max(...values), weights=values.map(v=>Math.exp(v-top));
  const total=weights.reduce((a,b)=>a+b,0);
  return weights.map(v=>v/total);
}
export function forecastRace({raceId,asOfDate,raceDate,runners,model}) {
  if (!(asOfDate<raceDate)) throw Error("forecast must precede race date");
  if (!Array.isArray(runners)||runners.length<3) throw Error("full field required");
  if (new Set(runners.map(r=>r.number)).size!==runners.length) throw Error("duplicate runner");
  if (!Array.isArray(model.coefficients)||!Array.isArray(model.mean)||!Array.isArray(model.scale)) throw Error("model missing");
  const n=model.coefficients.length;
  if(n===0||model.mean.length!==n||model.scale.length!==n) throw Error("model dimension mismatch");
  const logits=runners.map(r=>{
    if (!Array.isArray(r.features)||r.features.length!==n) throw Error("feature count mismatch");
    if(r.features.some(x=>!Number.isFinite(x))) throw Error("invalid feature");
    if(r.latestHistoryDate && !(r.latestHistoryDate<raceDate)) throw Error("future historical leakage");
    return r.features.reduce((acc,x,i)=>{
      if (!(model.scale[i]>0)) throw Error("invalid scale");
      return acc+((x-model.mean[i])/model.scale[i])*model.coefficients[i];
    },0);
  });
  const probabilities=softmax(logits);
  return {raceId,asOfDate,raceDate,predictions:runners.map((r,i)=>({number:r.number,p1:probabilities[i]})),winnerNumber:runners[probabilities.indexOf(Math.max(...probabilities))].number};
}
export function evaluateRace(forecast,officialResult) {
  if(forecast.raceId!==officialResult.raceId)throw Error("race mismatch");
  if(!(forecast.raceDate<=officialResult.resultDate))throw Error("result date precedes race");
  const trueWinner=officialResult.winnerNumber;
  const p=forecast.predictions.find(r=>r.number===trueWinner)?.p1;
  if(!(p>0))throw Error("winner missing");
  return {raceId:forecast.raceId,hit:Number(forecast.winnerNumber===trueWinner),
    logloss:-Math.log(p),brier:forecast.predictions.reduce((a,r)=>a+(r.p1-Number(r.number===trueWinner))**2,0)};
}
export function summarize(rows) {
  if(!rows.length)throw Error("empty evaluation");
  return {races:rows.length,top1Hits:rows.reduce((a,r)=>a+r.hit,0),
    top1Accuracy:rows.reduce((a,r)=>a+r.hit,0)/rows.length,
    logloss:rows.reduce((a,r)=>a+r.logloss,0)/rows.length,
    brier:rows.reduce((a,r)=>a+r.brier,0)/rows.length};
}
