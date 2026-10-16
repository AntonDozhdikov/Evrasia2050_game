/* Перед ходом: кризисы текущего года и история завершенных решений без подсказки будущего. */
(function(root){
 'use strict';
 const $=id=>document.getElementById(id);
 const E=root.EurasiaEngine,B=root.EURASIA_ENGINE_BOOTSTRAP,D=root.EURASIA_DATA,
       G=root.EURASIA_GUIDE,W=root.EURASIA_WILDCARDS,M=root.EurasiaModel,U=root.EurasiaUnits;
 if(!E||!B||!D||!G||!W||!M||!U||!root.EurasiaPartyUI)return;
 const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=(x,n=2)=>U.format(x,n);
 let lastSignature='',lastHTML='';
 function scenarioOf(p){
  if(p.scenario.startsWith('S')){
   const s=D.scenarios.find(x=>x.scenario_id===p.scenario);
   if(!s)throw Error('Неизвестный сценарий '+p.scenario);
   return s;
  }
  if(!Number.isInteger(p.wildcardSeed)||p.wildcardSeed<1)throw Error('Не задан номер жеребьёвки кризисов');
  W.generate(p.wildcardSeed);
  const s=W.getSets().find(x=>x.id===p.scenario);
  if(!s||p.wildcardEvents&&JSON.stringify(p.wildcardEvents)!==JSON.stringify(s.crisis_ids))
   throw Error('Состав «Дикой карты» не совпадает с сохранением');
  return {scenario_id:s.id,crisis_ids:s.crisis_ids};
 }
 const actionText=(i,level)=>level+' — '+G.actionDescriptions[i].levels[level];
 function render(){
  const panel=$('partyTurnIntelligence');
  if(!panel)return;
  const p=root.EurasiaPartyUI.getCurrent();
  const signature=JSON.stringify([p.scenario,p.policy,p.seed,p.year,p.years,p.controlled,p.wildcardSeed,p.wildcardEvents]);
  if(signature===lastSignature){panel.innerHTML=lastHTML;return;}
  try{
   const scenario=scenarioOf(p),year=p.year;
   const planned=E.announcedCrises(scenario,G.crisisCatalog,year);
   const pending=planned.filter(e=>e.started===year),continuing=planned.filter(e=>e.started<year);
   const events=planned.length?
    planned.map(e=>'<li><strong>'+safe(e.name)+'</strong> · '+safe(e.type)+
     ' · '+(e.started===year?'начинается в '+year:'продолжается с '+e.started)+
     ' · '+(e.affected?.length?safe(e.affected.join(', ')):'все государства')+'</li>').join(''):
    '<li>По сценарию на этот год кризисных событий нет.</li>';
   let content='<div class="turn-intel-head"><div><span class="section-kicker">ИНФОРМАЦИЯ ПЕРЕД ХОДОМ</span>'+
    '<h3>Обстановка к '+year+' году</h3></div><span class="turn-intel-year">'+year+'</span></div>';
   content+='<div class="turn-crisis">'+
    '<strong>Кризисы, предусмотренные сценарием на '+year+' год</strong>'+
    '<ul>'+events+'</ul><p>События известны из выбранного сценария. Их количественное воздействие зависит от решений стран и будет рассчитано после хода. Новых событий: '+
    pending.length+'; продолжающихся: '+continuing.length+'.</p></div>';
   if(year===2025)content+='<p class="turn-intel-empty">Первый ход. Истории игровых решений пока нет. Исходные экономические и институциональные условия взяты из состояния 2024 года.</p>';
   else{
    const overrides=Object.fromEntries(Object.entries(p.years).map(([y,rows])=>
     [y,Object.fromEntries(Object.entries(rows).filter(([c])=>p.controlled.includes(c)))]));
    const run=E.run({bootstrap:B,cat:G.crisisCatalog,scenario,seed:p.seed,db:D,
                   policy:p.policy,adaptive:root.EurasiaAdaptive,overrides,untilYear:year-1});
    const prev=run.history[run.history.length-1];
    const automated=run.history.filter(row=>!p.controlled.some(c=>p.years[row.year]?.[c])).length;
    const known=prev.active_crises?.length?prev.active_crises.map(e=>safe(e.name)).join('; '):'не было';
    content+='<p class="turn-intel-caption"><strong>Итоги '+prev.year+' года:</strong> кризисы — '+
      known+'; средний рост ВВП восьми стран — '+num(prev.mean_growth_pct,2)+' %; '+
      'моделируемая исходящая торговля восьми стран — '+num(U.countryTrade(prev.trade_usd_total),2)+' млрд долл.; '+
      'новые проекты — '+num(prev.new_projects,0)+'.</p>';
    if(automated)content+='<p class="turn-intel-note">За '+automated+
      ' предыдущих лет решения стран, которыми вы управляете, рассчитаны выбранной стратегией (вы пропустили эти годы). '+
      'Это модельное продолжение, а не зафиксированные действия человека.</p>';
    content+='<details class="turn-history" open><summary>Что сделали государства в '+prev.year+
      ' году · решения всех восьми стран</summary><div class="turn-history-scroll"><table><thead><tr>'+
      '<th>Государство / источник</th>'+G.actionDescriptions.map(a=>'<th>'+safe(a.name)+'</th>').join('')+
      '<th>Рост ВВП</th><th>Торговля, млрд долл.</th></tr></thead><tbody>'+
      prev.actions.map((a,i)=>{
       const code=D.countries[i],manual=!!(p.controlled.includes(code)&&p.years[prev.year]?.[code]);
       const row=prev.country_stats[i];
       return '<tr'+(p.controlled.includes(code)?' class="turn-controlled"':'')+'><th>'+safe(M.countryNames[code])+
        '<small>'+(manual?'Ваше решение':'Решение стратегии')+'</small></th>'+
        a.map((lv,k)=>'<td title="'+safe(actionText(k,lv))+'">'+safe(actionText(k,lv))+'</td>').join('')+
        '<td>'+num(row.growth,2)+' %</td><td>'+num(U.countryTrade(row.trade_usd),2)+'</td></tr>';
      }).join('')+'</tbody></table></div>'+
      '<p>Показаны только решения уже завершённого года. Действия автоматических стран в '+year+' году ещё не известны.</p></details>';
    content+='<div class="turn-controlled-summary"><strong>Ваши государства после '+prev.year+' года</strong><div class="turn-controlled-grid">'+
     p.controlled.map(code=>{
      const i=D.countries.indexOf(code),x=prev.country_stats[i];
      return '<div><b>'+safe(M.countryNames[code])+'</b><span>Рост ВВП: '+num(x.growth,2)+' %</span>'+
       '<span>Капитал: '+num(x.budget,3)+' усл. ед.</span>'+
       '<span>Торговля: '+num(U.countryTrade(x.trade_usd),2)+' млрд долл.</span></div>';
     }).join('')+'</div></div>';
   }
   panel.innerHTML=content;lastSignature=signature;lastHTML=content;
  }catch(e){panel.innerHTML='<p role="alert">Не удалось показать обстановку перед ходом: '+safe(e.message)+'</p>';}
 }
 root.addEventListener('eurasia:party-rendered',render);
 render();
 root.EurasiaTurnIntelligence={render};
})(window);
