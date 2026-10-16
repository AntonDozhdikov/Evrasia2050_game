
/* Расчет новой партии и сопоставление пяти вариантов при одинаковых условиях. */
(function(){
'use strict';
const Engine=window.EurasiaEngine,Core=window.EurasiaParty,B=window.EURASIA_ENGINE_BOOTSTRAP,D=window.EURASIA_DATA,G=window.EURASIA_GUIDE,W=window.EURASIA_WILDCARDS,M=window.EurasiaModel;
if(!Engine||!Core||!B||!D||!G||!W||!M)return;
const $=id=>document.getElementById(id);
const fmt=(v,n=2)=>Number.isFinite(v)?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:n,minimumFractionDigits:0}):'—';
const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const METRICS=[
 ['growth','Среднегодовой рост ВВП','%',1,'mean_growth_pct'],
 ['inflation','Среднегодовая инфляция','%',0,'inflation_pct'],
 ['investments','Инвестиции к ВВП','%',0,'investment_pct'],
 ['exports','Экспорт к ВВП','%',0,'export_pct'],
 ['imports','Импорт к ВВП','%',0,'import_pct'],
 ['unemployment','Безработица','%',-1,'unemployment_pct'],
 ['population','Годовое изменение населения','%',0,'population_growth_pct'],
 ['remittances','Денежные переводы к ВВП','%',0,'remittances_pct'],
 ['projects','Новые совместные проекты','',0,'new_projects'],
 ['matured','Проекты, достигшие отдачи','',0,'projects_matured'],
 ['agreements','Новые соглашения','',0,'new_agreements'],
 ['mobility','Соглашения о трудовой мобильности','',0,'mobility_agreements'],
 ['expenses','Инвестиционные расходы','усл. ед.',0,'project_cash_out'],
 ['benefits','Проектные поступления','усл. ед.',0,'project_benefit_current'],
 ['net','Чистая проектная отдача','усл. ед.',1,'net_annual'],
 ['trade','Торговый оборот в 2050 году','млрд долл.',1,'trade_usd_total'],
 ['budget','Остаток общего капитала в 2050 году','усл. ед.',1,'capital_budget_total'],
 ['network','Изменение торговой сети','индекс',0,'network_strength'],
 ['concentration','Сосредоточенность торговых потоков','индекс',0,'trade_concentration'],
 ['reward','Внутренняя оценка решений','усл. ед.',1,'mean_reward'],
 ['crises','Сумма годовых кризисных воздействий','',0,'crises_active']
];
const keys=['PLAYER','MAPPO_GREEDY','MAPPO','BARGAIN','NEUTRAL'];
const NAMES={PLAYER:'Игрок',MAPPO_GREEDY:'ИИ: наиболее вероятные решения',MAPPO:'ИИ: вероятностные решения',BARGAIN:'Переговоры по правилам',NEUTRAL:'Без новых инициатив'};
const colors={PLAYER:'#1b6cbb',MAPPO_GREEDY:'#7b4bb6',MAPPO:'#3d9389',BARGAIN:'#da8350',NEUTRAL:'#71819b'};
let computation=null;
function normalize(value,key){
 return key==='trade' ? value/1e9:value;
}
function metricAnnual(row,k){
 if(k==='net_annual')return (row.project_benefit_current||0)-(row.project_cash_out||0);
 if(k==='trade_usd_total')return row.trade_usd_total/1e9;
 return Number(row[k]||0);
}
function valueOf(summary,key){
 return normalize(summary[key],key);
}
function pct(a,b){
 if(!Number.isFinite(a)||!Number.isFinite(b))return '';
 const v=a-b,sign=v>0?'+':'';
 return (sign+fmt(v,3));
}
function getScenario(party){
 if(party.scenario.startsWith('S')){
  const s=D.scenarios.find(x=>x.scenario_id===party.scenario);if(!s)throw Error('Не найден сценарий '+party.scenario);return s;
 }
 if(party.wildcardSeed)W.generate(party.wildcardSeed);
 const selection=W.getSets().find(x=>x.id===party.scenario);
 if(!selection)throw Error('Не найдена выбранная Дикая карта');
 if(party.wildcardEvents&&JSON.stringify(party.wildcardEvents)!==JSON.stringify(selection.crisis_ids))throw Error('Состав кризисов изменился. Загрузите сохраненную партию.');
 return {scenario_id:party.scenario,crisis_ids:selection.crisis_ids};
}
function extract(){
 const raw=localStorage.getItem('evrasia2050:party-draft:v1');
 if(!raw)throw Error('Сначала сохраните решения года в разделе «Новая игровая партия».');
 const p=JSON.parse(raw);Core.validate(p);
 if(!Object.keys(p.years).length)throw Error('Сохраните решения хотя бы одного года.');
 return p;
}
function calculate(){
 const status=$('partyResultsStatus');
 status.textContent='Идет расчет 2025–2050 годов…';
 try{
  const p=extract(),scenario=getScenario(p);
  const isWild=scenario.scenario_id[0]==='W',standardSeed=D.manifest.seeds.includes(p.seed);
  const available=(isWild||!standardSeed)?['BARGAIN','NEUTRAL']:keys.slice(1);
  if(!available.includes(p.policy))throw Error('Для новой партии выберите «Переговоры по правилам» или «Без новых инициатив». Два режима обученной стратегии требуют исходного сценария и сохраненного номера расчета.');
  const settings={bootstrap:B,cat:G.crisisCatalog,scenario,seed:p.seed,db:D};
  const runs={};
  runs.PLAYER=Engine.run({...settings,policy:p.policy,overrides:p.years});
  for(const policy of available)runs[policy]=Engine.run({...settings,policy});
  const summaries=Object.fromEntries(Object.entries(runs).map(([k,v])=>[k,Engine.summary(v)]));
  computation={party:p,scenario,runs,summaries,available:['PLAYER',...available]};
  $('partyResultsContent').hidden=false;
  $('partyResultMetric').innerHTML=METRICS.map(([id,label])=>'<option value="'+id+'">'+safe(label)+'</option>').join('');
  $('partyResultMetric').value='growth';
  renderAll();
  status.textContent='Расчет завершен: 26 лет, '+p.controlled.length+' '+(p.controlled.length===1?'управляемое государство':'управляемых государств')+', '+available.length+' стратегии для сравнения.'+
   (available.length<4?' Для этого сценария доступны переговорная и нейтральная стратегии.':'');
  $('partyResults').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){status.textContent='Не удалось рассчитать партию: '+e.message; $('partyResultsContent').hidden=true;}
}
function renderAll(){
 const c=computation,head=c.available,player=c.summaries.PLAYER;
 const performance=METRICS.filter(m=>m[3]).map(([id,label,unit,dir])=>{
  const scores=c.available.slice(1).map(k=>({name:NAMES[k],value:c.summaries[k][id]}));
  const rivals=scores.filter(x=>Number.isFinite(x.value));if(!rivals.length)return null;
  const best=rivals.reduce((a,b)=>dir*b.value>dir*a.value?b:a);
  return {label,unit,better:dir*player[id]>dir*best.value+1e-8,against:best.name,delta:player[id]-best.value};
 }).filter(Boolean);
 const better=performance.filter(x=>x.better).length;
 $('partyResultKpis').innerHTML=[
 ['Преимущество по показателям',better+' из '+performance.length],
 ['Рост ВВП за год',fmt(player.growth)+'%'],
 ['Чистая отдача проектов',fmt(player.net)+' усл. ед.'],
 ['Торговый оборот к 2050 году',fmt(player.trade/1e9,1)+' млрд долл.']
 ].map(([title,value])=>'<div class="player-kpi"><span>'+safe(title)+'</span><strong>'+safe(value)+'</strong></div>').join('');
 $('partyResultHead').innerHTML='<tr><th>Показатель</th>'+head.map(k=>'<th>'+safe(NAMES[k])+'</th>').join('')+'</tr>';
 $('partyResultRows').innerHTML=METRICS.map(([key,label,unit,dir])=>{
  const values=head.map(k=>{let v=c.summaries[k][key];if(key==='trade')v/=1e9;return v;});
  const ranked=dir?values.reduce((best,v,i)=>dir*v>dir*values[best]?i:best,0):-1;
  return '<tr><th>'+safe(label)+'</th>'+values.map((v,i)=>'<td class="'+(i===0?'player-cell ':'')+(ranked===i?'metric-winner':'')+'">'+fmt(v,key==='trade'?2:3)+(unit?' <small>'+safe(unit)+'</small>':'')+'</td>').join('')+'</tr>';
 }).join('');
 const countries=D.countries;
 $('partyCountryHead').innerHTML='<tr><th>Государство</th>'+head.map(k=>'<th>'+safe(NAMES[k])+'</th>').join('')+'</tr>';
 $('partyCountryRows').innerHTML=countries.map((country,i)=>'<tr><th>'+safe(M.countryNames[country])+(c.party.controlled.includes(country)?' <small>игрок</small>':'')+'</th>'+head.map((k,j)=>'<td class="'+(j===0?'player-cell':'')+'">'+fmt(c.runs[k].returns[i],3)+'</td>').join('')+'</tr>').join('');
 renderChart();
}
function renderChart(){
 const c=computation,metric=METRICS.find(m=>m[0]===$('partyResultMetric').value)||METRICS[0];
 const series=c.available.map(key=>({key,values:c.runs[key].history.map(row=>metricAnnual(row,metric[4]))}));
 const vals=series.flatMap(s=>s.values),min=Math.min(...vals),max=Math.max(...vals),spread=Math.max(1e-7,max-min);
 const low=min-spread*.11,high=max+spread*.11;
 const W=900,H=330,ox=62,oy=20,iw=W-ox-22,ih=H-oy-43;
 const X=k=>ox+k*iw/25,Y=v=>oy+(high-v)/(high-low)*ih;
 const lines=series.map(s=>'<polyline points="'+s.values.map((v,i)=>X(i).toFixed(2)+','+Y(v).toFixed(2)).join(' ')+'" fill="none" stroke="'+colors[s.key]+'" stroke-width="'+(s.key==='PLAYER'?4:2)+'" stroke-linecap="round"/>').join('');
 const grid=Array.from({length:5},(_,i)=>{const v=low+(high-low)*i/4,y=Y(v);return '<line x1="'+ox+'" y1="'+y+'" x2="'+(W-22)+'" y2="'+y+'" stroke="#e4eaf2"/><text x="'+(ox-8)+'" y="'+(y+4)+'" text-anchor="end" fill="#72869c" font-size="11">'+fmt(v,2)+'</text>';}).join('');
 const years=[2025,2030,2035,2040,2045,2050].map(y=>'<text x="'+X(y-2025)+'" y="'+(H-14)+'" text-anchor="middle" fill="#72869c" font-size="12">'+y+'</text>').join('');
 const legend=series.map(s=>'<span><i style="background:'+colors[s.key]+'"></i>'+safe(NAMES[s.key])+'</span>').join('');
 $('partyResultChart').innerHTML='<div class="player-chart-title">'+safe(metric[1])+'</div><svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Годовые значения показателя"><g>'+grid+years+lines+'</g></svg><div class="player-chart-legend">'+legend+'</div>';
}
function exportJSON(){
 if(!computation)return;
 const data={party:computation.party,scenario:computation.scenario,metrics:METRICS.map(m=>m.slice(0,4)),
  outcomes:computation.runs,summary:computation.summaries,provenance:{base:'V4.7',source:'2024 Stage1',engine:'JS conditional port of EurasiaEnv',reproducible:true,
  policy_mode:'MAPPO archive actions replayed; NEUTRAL and BARGAIN computed from scenario',
  random_stream:'browser seeded random stream rather than NumPy PCG64'}};
 const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download='evrazia2050_itogi_'+data.party.scenario+'_'+data.party.seed+'.json';
 document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('partyCalculate').addEventListener('click',calculate);
$('partyResultMetric').addEventListener('change',()=>{if(computation)renderChart();});
$('partyDownloadResults').addEventListener('click',exportJSON);
})();
