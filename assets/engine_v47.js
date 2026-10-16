
(function(root,factory){const result=factory();if(typeof module==='object'&&module.exports)module.exports=result;else root.EurasiaEngine=result;})(typeof self!=='undefined'?self:this,function(){
'use strict';
const C=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM'],N=8;
const L=[[ -18,25],[-5,70],[0,70],[0,140],[0,140],[0,45],[-5,8],[0,65]];
const vectors={economic:[-.9,.18,-.55,-.25],financial:[-.8,.35,-.35,-.5],geopolitical:[-.55,.3,-.7,-.35],technological:[.35,-.06,.25,.28],demographic:[-.3,.12,-.18,-.1],environmental:[-.45,.16,-.32,-.35],pandemic:[-.8,.2,-.62,-.6],elite:[-.25,.12,-.27,-.19]};
const clamp=(x,a,b)=>Math.max(a,Math.min(x,b)),sum=a=>a.reduce((v,x)=>v+x,0),avg=a=>sum(a)/a.length;
const copy=a=>JSON.parse(JSON.stringify(a)),matrix=()=>Array.from({length:N},()=>Array(N).fill(0));
function generator(seed){
 let x=seed>>>0,spare=null;
 const uniform=()=>{x=(x+0x6D2B79F5)>>>0;let t=x;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};
 return ()=>{if(spare!==null){const a=spare;spare=null;return a;}const r=Math.sqrt(-2*Math.log(Math.max(uniform(),1e-12))),t=uniform()*Math.PI*2;spare=r*Math.sin(t);return r*Math.cos(t);};
}
function init(bootstrap,scenario,cat,seed=163,zeroNoise=false){
 if(!bootstrap||!scenario)throw Error('Не найдено начальное состояние или сценарий');
 const state={year:2024,seed,scenario,cat,countries:C,gauss:generator(seed),zeroNoise,
  z:copy(bootstrap.targetZ),means:bootstrap.mean,std:bootstrap.std,gdpZ:bootstrap.gdpZ.slice(),popZ:bootstrap.popZ.slice(),
  gdpMean:bootstrap.gdpZMean,gdpStd:bootstrap.gdpZStd,popMean:bootstrap.popZMean,popStd:bootstrap.popZStd,
  energy:bootstrap.energy.slice(),instit:bootstrap.instit,trade:copy(bootstrap.trade),tradeInitial:bootstrap.tradeInitial,
  register:{},pending:[],active:[],events:[],returns:Array(N).fill(0),history:[],
  lastProjects:Array(N).fill(0),lastAgreements:Array(N).fill(0),lastCrisis:Array(N).fill(0)};
 state.graph=state.trade.map(row=>row.map(v=>v/Math.max(1e-8,sum(row))));
 return state;
}
function crisis(state){
 const year=state.year,ids=state.scenario.crisis_ids;
 ids.forEach((id,k)=>{
  const start=2026+(state.scenario.scenario_id[0]==='W'?3:4)*k;
  if(year>=start&&(state.scenario.scenario_id[0]==='W'?year===start:(year-start)%12===0)){
   const ev=state.cat[String(id)];if(!ev)throw Error('Нет кризиса '+id);
   state.events.push({...ev,expires:Math.min(2050,year+ev.duration-1)});
  }
 });
 state.events=state.events.filter(e=>e.expires>=year);
 const sh=Array.from({length:N},()=>[0,0,0,0]);
 for(const e of state.events){
  const v=(vectors[e.type]||vectors.economic).map(x=>x*e.intensity*.65);
  const destinations=(e.affected||[]).map(c=>C.indexOf(c)).filter(i=>i>=0);
  const mask=C.map((_,i)=>destinations.length?+(destinations.includes(i)):1);
  for(let i=0;i<N;i++){
   const weight=clamp(mask[i]+.45*sum(state.graph[i].map((p,j)=>p*mask[j])),0,1.3);
   for(let k=0;k<4;k++)sh[i][k]+=weight*v[k];
  }
 }
 return sh.map(row=>row.map(v=>clamp(v,-2,2)));
}
function step(s,actions){
 if(actions.length!==N||actions.some(row=>row.length!==6||row.some(x=>!Number.isInteger(x)||x<0||x>2)))throw Error('Ожидается 8 стран и 6 решений каждой');
 s.year++;const year=s.year;
 const trade=actions.map(a=>a[0]-1),inv=actions.map(a=>a[1]-1),coord=actions.map(a=>a[2]-1),protect=actions.map(a=>a[3]-1),focus=actions.map(a=>a[4]-1),mob=actions.map(a=>a[5]-1);
 const before=copy(s.graph),prev=copy(s.z),oldEnergy=s.energy.slice();
 for(const pair of Object.keys(s.register))if(s.register[pair]<year)delete s.register[pair];
 const proposal=matrix(),agreement=matrix(),newTreaties=[],offers=[];
 for(let i=0;i<N;i++)for(let j=i+1;j<N;j++){
  const key=i+'-'+j,member=s.instit[i][0]*s.instit[j][0]>0;
  const compatible=(actions[i][4]>=1&&actions[j][4]>=1)||member;
  if(compatible&&actions[i][2]>=1&&actions[j][2]>=1&&(actions[i][2]===2||actions[j][2]===2)){
   if(s.register[key]===undefined)newTreaties.push([i,j]);
   agreement[i][j]=agreement[j][i]=1;s.register[key]=year+6;
  }
  const investing=actions[i][1]>=1&&actions[j][1]>=1&&(actions[i][1]===2||actions[j][1]===2);
  if(investing&&actions[i][2]>=1&&actions[j][2]>=1&&(s.register[key]!==undefined||member)){
   const offer=(.18+.12*(actions[i][1]===2&&actions[j][1]===2?1:0))*Math.min(s.energy[i],s.energy[j]);
   if(offer>=.01){proposal[i][j]=proposal[j][i]=offer;offers.push([i,j]);}
  }
 }
 const mAgreement=matrix();
 for(let i=0;i<N;i++)for(let j=i+1;j<N;j++){
  const legal=s.instit[i][2]*s.instit[j][2]>0||(coord[i]>0&&coord[j]>0);
  if(mob[i]>0&&mob[j]>0&&legal)mAgreement[i][j]=mAgreement[j][i]=1;
 }
 const rowMob=mAgreement.map(row=>sum(row)/7);
 const offered=proposal.map(sum),allocation=offered.map((x,i)=>Math.min(1,s.energy[i]/(x+.01)));
 for(let i=0;i<N;i++)for(let j=0;j<N;j++)proposal[i][j]*=Math.min(allocation[i],allocation[j]);
 let duplicate=0;
 for(const [i,j] of offers)if([...s.pending,...s.active].some(p=>p.i===i&&p.j===j)){proposal[i][j]=proposal[j][i]=0;duplicate++;}
 const rowProj=proposal.map(sum),treatyCost=Array(N).fill(0);
 newTreaties.forEach(([i,j])=>{treatyCost[i]+=.012;treatyCost[j]+=.012;});
 for(let i=0;i<N;i++)for(let j=i+1;j<N;j++)if(proposal[i][j]>0)s.pending.push({i,j,amount:proposal[i][j],maturity:year+2,expiry:year+8});
 const matured=s.pending.filter(p=>p.maturity<=year);
 s.active.push(...matured);s.pending=s.pending.filter(p=>p.maturity>year);s.active=s.active.filter(p=>p.expiry>=year);
 const benefit=Array(N).fill(0);
 for(const p of s.active){benefit[p.i]+=.34*p.amount;benefit[p.j]+=.34*p.amount;}
 s.energy=s.energy.map((e,i)=>clamp(e-rowProj[i]-.014*(actions[i][1]===2?1:0)-treatyCost[i]-.03*Math.max(protect[i],0),.025,1.5));
 for(let i=0;i<N;i++){
  for(let j=0;j<N;j++){
   let w=s.graph[i][j]*(1+.02*trade[i]);
   if(focus[i]===1)w*=.985+.12*before[i][j];
   if(focus[i]===-1)w*=.97;
   if(coord[i]>0&&agreement[i][j])w*=1.02;
   if(proposal[i][j]>0)w+=proposal[i][j]*.006;
   if(i===j)w=0;
   s.graph[i][j]=Math.max(w,0);
   s.trade[i][j]=clamp(s.trade[i][j]*clamp(s.graph[i][j]/Math.max(before[i][j],1e-8),.65,1.35),0,1e15);
  }
  const total=sum(s.trade[i]);s.graph[i]=total>0?s.trade[i].map(x=>x/total):before[i].slice();
 }
 const diversity=s.graph.map(row=>1-sum(row.map(x=>x*x))),concentration=diversity.map(x=>1-x);
 const shock=crisis(s);
 for(let i=0;i<N;i++){
  const factor=clamp(1+.035*shock[i][2],.90,1.06);
  for(let j=0;j<N;j++)s.trade[i][j]*=factor;
  const total=sum(s.trade[i]);s.graph[i]=total>0?s.trade[i].map(x=>x/total):s.graph[i].slice();
 }
 const values=Array.from({length:N},()=>Array(8).fill(0));
 for(let k=0;k<8;k++)for(let i=0;i<N;i++){
  const sh=shock[i],effGrowth=sh[0]*(1-.19*protect[i]);let e;
  if(k===0)e=effGrowth*2.4+.35*trade[i]*diversity[i]+.26*rowProj[i]+.48*benefit[i]-.30*Math.max(inv[i],0)-.16*Math.max(protect[i],0);
  else if(k===1)e=sh[1]*2.3+.16*Math.max(inv[i],0)-.14*Math.max(protect[i],0);
  else if(k===2)e=.6*inv[i]+.2*rowProj[i]+sh[2]*1.1;
  else if(k===3)e=sh[2]*2+.8*trade[i]*(.2+diversity[i])+.2*focus[i];
  else if(k===4)e=sh[2]*1.7+.6*trade[i];
  else if(k===5)e=sh[3]*1.5-.2*rowProj[i]+.2*Math.max(inv[i],0)-.22*rowMob[i]+.08*Math.max(mob[i],0);
  else if(k===6)e=sh[3]*.10;
  else e=sh[3]*1.3+.18*rowMob[i];
  let z=prev[i][k]+clamp(e/Math.max(s.std[k],.01),-3.5,3.5)+(s.zeroNoise?0:.015*s.gauss());
  let raw=clamp(z*s.std[k]+s.means[k],L[k][0],L[k][1]);
  s.z[i][k]=(raw-s.means[k])/s.std[k];values[i][k]=raw;
 }
 for(let i=0;i<N;i++){
  const gdp=Math.expm1(clamp(s.gdpZ[i]*s.gdpStd+s.gdpMean,0,34));
  const pop=Math.expm1(clamp(s.popZ[i]*s.popStd+s.popMean,0,34));
  s.gdpZ[i]=(Math.log1p(Math.max(1e4,gdp*(1+values[i][0]/100)))-s.gdpMean)/s.gdpStd;
  s.popZ[i]=(Math.log1p(Math.max(1e4,pop*(1+values[i][6]/100)))-s.popMean)/s.popStd;
 }
 const totalTrade=sum(s.trade.map(sum)),level=Math.log1p(totalTrade/Math.max(s.tradeInitial,1));
 const rewards=Array.from({length:N},(_,i)=>{
  const exposure=Math.abs(shock[i][0])*(.3+concentration[i]);
  return clamp(.13*clamp(values[i][0],-15,20)+.18*diversity[i]+.19*(benefit[i]-rowProj[i])+.06*level
  -.11*treatyCost[i]-.11*Math.max(protect[i],0)-.016*Math.max(coord[i],0)
  -.18*exposure*(1-.36*Math.max(protect[i],0))-.12*concentration[i]*Math.max(trade[i],0)
  -.06*(oldEnergy[i]<.15?1:0)-.04*Math.max(mob[i],0),-5,5);
 });
 rewards.forEach((v,i)=>s.returns[i]+=v);
 const projects=offers.filter(([i,j])=>proposal[i][j]>0).length;
 const activeAgreements=Array.from({length:N},(_,i)=>Array.from({length:N-i-1},(_,k)=>agreement[i][i+k+1])).flat().filter(Boolean).length;
 // Observation-only data for the frozen MAPPO actor. These never feed into
 // economic state updates or V4.7 rewards.
 s.lastProjects=proposal.map(row=>row.filter(amount=>amount>0).length/7);
 s.lastAgreements=Array(N).fill(0);
 for(const pair of Object.keys(s.register)){
  const [i,j]=pair.split('-').map(Number);
  if(Number.isInteger(i)&&Number.isInteger(j)){s.lastAgreements[i]+=1/7;s.lastAgreements[j]+=1/7;}
 }
 s.lastCrisis=shock.map(row=>clamp(Math.abs(row[0]),0,2));
 const out={year,actions:copy(actions),mean_growth_pct:avg(values.map(v=>v[0])),
  inflation_pct:avg(values.map(v=>v[1])),investment_pct:avg(values.map(v=>v[2])),export_pct:avg(values.map(v=>v[3])),
  import_pct:avg(values.map(v=>v[4])),unemployment_pct:avg(values.map(v=>v[5])),
  population_growth_pct:avg(values.map(v=>v[6])),remittances_pct:avg(values.map(v=>v[7])),
  new_projects:projects,projects_matured:matured.length,projects_operating:s.active.length,
  agreements:activeAgreements,new_agreements:newTreaties.length,mobility_agreements:mAgreement.flat().filter(Boolean).length/2,
  trade_usd_total:totalTrade,network_strength:totalTrade/Math.max(s.tradeInitial,1),
  capital_budget_total:sum(s.energy),project_cash_out:sum(rowProj)/2,project_benefit_current:sum(benefit),
  trade_concentration:avg(concentration),mean_reward:avg(rewards),crises_active:s.events.length,
  rejected_duplicate_pairs:duplicate,growth_pct:values.map(v=>v[0]),
  country_stats:C.map((c,i)=>({country:c,growth:values[i][0],budget:s.energy[i],reward:rewards[i],trade_usd:sum(s.trade[i])}))};
 s.history.push(out);
 return out;
}
function choose(s,policy,db,scenario,seed,year){
 const a=Array.from({length:N},()=>Array(6).fill(1));
 if(policy==='NEUTRAL')return a;
 if(policy==='BARGAIN'){
  const lead=(s.year-2024)%N;
  a[lead][1]=a[lead][2]=a[lead][4]=2;
  for(let j=0;j<N;j++)if(s.graph[lead][j]>.05){a[j][1]=1;a[j][2]=1;a[j][4]=2;}
  return a;
 }
 const run=db.runs[[scenario,policy,seed].join('|')];
 if(!run)throw Error('Нет сохраненной последовательности ИИ для выбранного сценария');
 return copy(run.actions[year-2025]);
}
function run(options){
 const {bootstrap,cat,scenario,seed,policy,db}=options;
 const s=init(bootstrap,scenario,cat,seed,options.zeroNoise);
 for(let year=2025;year<=2050;year++){
  const a=policy.startsWith('ADAPTIVE_MAPPO')
   ? (options.adaptive?options.adaptive.actions(s,policy,seed,year):(()=>{throw Error('Не подключен адаптивный актор MAPPO V4.7');})())
   : choose(s,policy,db,options.actionScenario||scenario.scenario_id,seed,year);
  const changed=options.overrides&&options.overrides[year];
  if(changed)for(const [country,actions] of Object.entries(changed)){
   const i=C.indexOf(country);if(i<0)throw Error('Неизвестное государство');
   a[i]=actions.slice();
  }
  step(s,a);
 }
 return {history:s.history,returns:s.returns,policy,scenario:scenario.scenario_id,seed};
}
function summary(run){
 const h=run.history,last=h[h.length-1],total=k=>sum(h.map(x=>x[k]||0)),average=k=>avg(h.map(x=>x[k]||0));
 return {growth:average('mean_growth_pct'),inflation:average('inflation_pct'),investments:average('investment_pct'),
  exports:average('export_pct'),imports:average('import_pct'),unemployment:average('unemployment_pct'),
  population:average('population_growth_pct'),remittances:average('remittances_pct'),
  projects:total('new_projects'),matured:total('projects_matured'),agreements:total('new_agreements'),
  mobility:total('mobility_agreements'),expenses:total('project_cash_out'),benefits:total('project_benefit_current'),
  net:total('project_benefit_current')-total('project_cash_out'),
  trade:last.trade_usd_total,budget:last.capital_budget_total,
  reward:average('mean_reward'),network:last.network_strength,concentration:average('trade_concentration'),
  crises:total('crises_active')};
}
return {init,step,choose,run,summary};
});
