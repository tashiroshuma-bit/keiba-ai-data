// Exact three-stage conditional Plackett-Luce enumeration with V51 temperature calibration.
import {softmax} from './shared_forecast_engine.mjs';
function tempered(z,t){if(!(t>0))throw Error('invalid temperature');return softmax(z.map(v=>v/t))}
export function v51Joint(z,cal){
 const n=z[0].length;
 if(z.length!==3||n<3||z.some(a=>a.length!==n))throw Error('invalid stage logits');
 const raw=softmax(z[0]), entropy=-raw.reduce((s,p)=>s+p*Math.log(Math.max(1e-15,p)),0)/Math.log(n);
 const cls=(entropy>=cal.group_entropy_cutoff?'high_entropy':'other_entropy')+'__'+(Math.max(...raw)<cal.group_favorite_cutoff?'close_field':'clear_favorite');
 const t1=cal.winner_entropy_confidence_groups[cls]?.temp,t2=cal.global_stage_temperatures['2'],t3=cal.global_stage_temperatures['3'];
 const p1=tempered(z[0],t1),p2=Array(n).fill(0),p3=Array(n).fill(0),sets=new Map();
 let top={probability:-1,indices:null},mass=0;
 for(let i=0;i<n;i++){
  const rem2=Array.from({length:n},(_,k)=>k).filter(k=>k!==i),q2=tempered(rem2.map(k=>z[1][k]),t2);
  for(let jx=0;jx<rem2.length;jx++){
   const j=rem2[jx],pair=p1[i]*q2[jx];p2[j]+=pair;
   const rem3=rem2.filter(k=>k!==j),q3=tempered(rem3.map(k=>z[2][k]),t3);
   for(let kx=0;kx<rem3.length;kx++){
    const k=rem3[kx],probability=pair*q3[kx];mass+=probability;p3[k]+=probability;
    const key=[i,j,k].sort((a,b)=>a-b).join(',');
    sets.set(key,(sets.get(key)||0)+probability);
    if(probability>top.probability+1e-16)top={probability,indices:[i,j,k]};
   }
  }
 }
 let best=null,bestP=-1;
 for(const [key,p] of sets){if(p>bestP+1e-16||(Math.abs(p-bestP)<=1e-16&&(best===null||key.split(',').map(Number).some((v,i)=>v<best[i]&&key.split(',').map(Number).slice(0,i).every((x,j)=>x===best[j]))))){best=key.split(',').map(Number);bestP=p}}
 if(Math.abs(mass-1)>1e-8)throw Error('joint mass mismatch');
 return {p1,p2,p3,pTop3:p1.map((v,i)=>v+p2[i]+p3[i]),orderedPick:top.indices,orderedProbability:top.probability,
  unorderedPick:best,unorderedProbability:bestP,entropy,stratum:cls,jointMass:mass};
}
