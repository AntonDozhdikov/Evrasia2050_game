/* Real frozen MAPPO V4.7 Actor: state-conditioned forward pass in the browser.
   Original checkpoint: research/frozen/EURASIA_STAGE3_HANDOFF_V47.zip.
   Only the actor and gated offsets are used; the V4.7 economy is not modified.
   Some non-target historical features are held at 2024 values because the compact
   JS engine does not evolve all Python environment features. This is an explicitly
   documented observation adapter, NOT numerical equivalence with PyTorch runtime.
*/
(function(root,factory){
 const v=factory(typeof module==='object'&&module.exports?require('./policy_v47.js'):root.EURASIA_ACTOR_V47);
 if(typeof module==='object'&&module.exports)module.exports=v;
 else root.EurasiaAdaptive=v;
})(typeof self!=='undefined'?self:this,function(P){
'use strict';
if(!P||P.schema!=='EURASIA_FROZEN_MAPPO_V47_PORT_1')throw Error('MAPPO V4.7 checkpoint not loaded');
const C=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM'],HEADS=6;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const sum=a=>a.reduce((v,x)=>v+x,0);
function observe(state){
 if(!state||state.z?.length!==8||state.graph?.length!==8||!Number.isInteger(state.year))throw Error('Invalid V4.7 game state for adaptive policy');
 const o=[];
 for(let i=0;i<8;i++){
  const z=P.initial_z[i].slice();
  for(let k=0;k<8;k++)z[P.target_indices[k]]=state.z[i][k];
  if(state.year>2024){
   const g=5,p=14,pc=7;
   z[g]=state.gdpZ[i];z[p]=state.popZ[i];
   const gdp=Math.expm1(clamp(z[g]*P.feature_std[g]+P.feature_mean[g],0,34));
   const pop=Math.expm1(clamp(z[p]*P.feature_std[p]+P.feature_mean[p],0,34));
   z[pc]=(Math.log1p(Math.max(0,gdp/Math.max(pop,1)))-P.feature_mean[pc])/P.feature_std[pc];
  }
  const mask=state.year===2024?P.initial_mask[i]:P.initial_mask[i].map(()=>1);
  const graph=state.graph[i].slice(),incoming=state.graph.map(row=>row[i]);
  const sourceEstimate=P.source[i].filter(x=>x===3).length/8;
  const trade=sum(state.trade[i]);
  const extras=[sum(graph),Math.max(...graph),sourceEstimate,state.energy[i],
   state.year/2050,(Math.log1p(Math.max(P.population[i],1))-12)/8];
  const recent=[state.lastProjects?.[i]||0,state.lastAgreements?.[i]||0,
   state.lastCrisis?.[i]||0,Math.log1p(trade/Math.max(state.tradeInitial,1))];
  const row=[...z,...mask,...P.initial_instit[i],...graph,...incoming,
   ...P.migration[i],...P.migration_mask[i],...extras,...recent];
  if(row.length!==P.obs_dim||row.some(v=>!Number.isFinite(v)))throw Error('Invalid MAPPO observation: country '+C[i]+' dimension '+row.length);
  o.push(row);
 }
 return o;
}
function affine(W,B,input){
 const out=Array(W.shape[0]),cols=W.shape[1],w=W.values,b=B.values;
 if(input.length!==cols)throw Error('MAPPO weight dimension mismatch');
 for(let i=0;i<out.length;i++){
  let n=b[i],off=i*cols;
  for(let j=0;j<cols;j++)n+=w[off+j]*input[j];
  out[i]=n;
 }
 return out;
}
function logitsFromObs(obs){
 const weights=P.actor,emb=weights['embed.weight'].values,offsets=P.gates.values;
 return obs.map((row,i)=>{
  const embed=emb.slice(i*12,(i+1)*12);
  const x=[...row,...embed];
  const one=affine(weights['body.0.weight'],weights['body.0.bias'],x).map(Math.tanh);
  const two=affine(weights['body.2.weight'],weights['body.2.bias'],one).map(Math.tanh);
  const out=affine(weights['head.weight'],weights['head.bias'],two);
  const crisis=clamp(row[row.length-2]*5,0,1);
  const shortage=clamp((.60-row[row.length-7])*2,0,1);
  const elapsed=clamp((row[row.length-6]*2050-2025)/20,0,1);
  const gated=Array.from({length:HEADS},(_,h)=>
    Array.from({length:3},(_,level)=>{
      const k=(i*HEADS+h)*3+level;
      return out[h*3+level]+offsets[k]+
       crisis*offsets[8*HEADS*3+k]+
       shortage*offsets[2*8*HEADS*3+k]+
       elapsed*offsets[3*8*HEADS*3+k];
    })
  );
  return gated;
 });
}
function logits(state){return logitsFromObs(observe(state));}
function softmax(values){
 const max=Math.max(...values),raw=values.map(x=>Math.exp(x-max)),total=sum(raw);
 return raw.map(x=>x/total);
}
function random(seed,year,country,head){
 // Separate counter-based stream, independent of policy execution order.
 let n=((seed>>>0)^Math.imul(year,2654435761)^Math.imul(country+1,2246822519)^Math.imul(head+1,3266489917))>>>0;
 n^=n>>>16;n=Math.imul(n,0x7feb352d);n^=n>>>15;n=Math.imul(n,0x846ca68b);n^=n>>>16;
 return (n>>>0)/4294967296;
}
function actions(state,policy,seed,year){
 if(!['ADAPTIVE_MAPPO_GREEDY','ADAPTIVE_MAPPO'].includes(policy))throw Error('Unknown adaptive policy '+policy);
 const rows=logits(state);
 return rows.map((country,i)=>country.map((values,h)=>{
  if(policy==='ADAPTIVE_MAPPO_GREEDY')return values.indexOf(Math.max(...values));
  const p=softmax(values),r=random(seed,year,i,h);
  return r<p[0]?0:r<p[0]+p[1]?1:2;
 }));
}
return {observe,logits,logitsFromObs,softmax,actions,checkpoint:P.provenance,observationAdapter:'JS_V47_2024_NON_TARGET_FROZEN'};
});
