(() => {
'use strict';
const D=window.EURASIA_DATA, M=window.EurasiaModel;
if(!D||!M){document.body.textContent='Не загружены научные данные V4.7. Проверьте assets/data.js';return;}
const $=id=>document.getElementById(id);
let state={scenario:'S01',policy:'MAPPO_GREEDY',compare:'BARGAIN',seed:163,year:2025,country:'RUS',metric:'mean_growth_pct'};
let timer=null;
const fmt=(v,n=1)=>v==null?'—':Number(v).toLocaleString('ru-RU',{maximumFractionDigits:n,minimumFractionDigits:n});
const signed=(x,n=1)=> x==null?'—':(x>0?'+':'')+fmt(x,n);
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const escNumber=(v)=>v==null?'—':fmt(v,1);
const current=()=>M.at(D,state.scenario,state.policy,state.seed,state.year);
const compare=()=>M.at(D,state.scenario,state.compare,state.seed,state.year);
function selectSetup(){
 $('scenario').innerHTML=D.scenarios.map(s=>`<option value="${safe(s.scenario_id)}">${safe(s.scenario_id+' · '+(window.EURASIA_GUIDE?.scenarioTitles?.[s.scenario_id]||s.name))}</option>`).join('');
 for(const id of ['policy','compare'])$(id).innerHTML=Object.entries(M.policyNames).map(([v,k])=>`<option value="${v}">${safe(k)}</option>`).join('');
 $('seed').innerHTML=D.manifest.seeds.map(v=>`<option value="${v}">${v}</option>`).join('');
 for(const id of ['scenario','policy','compare','seed','metric']){if(!$(id))continue;$(id).value=state[id];$(id).addEventListener('change',e=>{state[id]=id==='seed'?Number(e.target.value):e.target.value;pause();render();});}
 $('year').addEventListener('input',e=>{state.year=Number(e.target.value);render();});
 $('back').onclick=()=>{pause();state.year=Math.max(2025,state.year-1);render();};
 $('next').onclick=()=>{pause();state.year=Math.min(2050,state.year+1);render();};
 $('play').onclick=()=>timer?pause():play();
 $('exportJson').onclick=downloadJSON;
 $('exportCsv').onclick=downloadCSV;
}
function play(){if(state.year===2050)state.year=2025;$('play').textContent='Ⅱ Пауза';timer=setInterval(()=>{if(state.year===2050){pause();return;}state.year++;render();},650);}
function pause(){if(timer){clearInterval(timer);timer=null;}$('play').textContent='▶ Воспроизвести';}
function updateStat(id,deltaId,v,other,suffix='',digits=1){
 $(id).textContent=fmt(v,digits)+suffix;
 let diff=Number(v)-Number(other);
 $(deltaId).innerHTML=`<span class="${diff>0?'pos':diff<0?'neg':'neutral'}">${signed(diff,digits)}${suffix}</span> к ${safe(M.policyNames[state.compare])}`;
}
function renderStats(){let x=current().values,y=compare().values;
 updateStat('growth','growth-delta',x.mean_growth_pct,y.mean_growth_pct,'%',2);
 updateStat('projects','projects-delta',x.new_projects,y.new_projects,'',0);
 updateStat('trade','trade-delta',x.trade_usd_total/1e9,y.trade_usd_total/1e9,'',1);
 $('crisis').textContent=fmt(x.crises_active,0);$('crisis-delta').textContent=x.crises_active?'Синтетические воздействия':'Активных воздействий нет';
}
function renderChart(){
 const a=M.series(D,state.scenario,state.policy,state.seed,state.metric),b=M.series(D,state.scenario,state.compare,state.seed,state.metric);
 const vals=[...a,...b].map(p=>p.value).filter(Number.isFinite);let low=Math.min(...vals),high=Math.max(...vals);if(high===low){low-=1;high+=1;}
 const margin=(high-low)*.13;low-=margin;high+=margin;
 const w=820,h=290,p={l:58,r:16,t:21,b:42};const X=i=>p.l+i*(w-p.l-p.r)/25;const Y=v=>p.t+(high-v)/(high-low)*(h-p.t-p.b);
 const makeLine=(s,color)=>`<polyline points="${s.map((d,i)=>`${X(i).toFixed(2)},${Y(d.value).toFixed(2)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
 const ix=state.year-2025; const hl=`<line x1="${X(ix)}" y1="${p.t}" x2="${X(ix)}" y2="${h-p.b}" stroke="#9aaabe" stroke-width="1.5" stroke-dasharray="5 5"/>`;
 const grids=Array.from({length:5},(_,i)=>{let v=low+i*(high-low)/4,yy=Y(v);return `<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="#e3e9f0"/><text x="${p.l-12}" y="${yy+4}" font-size="12" fill="#718095" text-anchor="end">${fmt(state.metric==='trade_usd_total'?v/1e9:v,1)}</text>`;}).join('');
 const labels=[2025,2030,2035,2040,2045,2050].map(v=>`<text x="${X(v-2025)}" y="${h-13}" text-anchor="middle" fill="#718095" font-size="12">${v}</text>`).join('');
 $('chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Динамика ${safe(state.metric)}"><g>${grids}${labels}${hl}${makeLine(b,'#d44f5d')}${makeLine(a,'#2362c6')}</g><circle cx="${X(ix)}" cy="${Y(a[ix].value)}" r="6" fill="#2362c6" stroke="#fff" stroke-width="2"><title>${safe(M.policyNames[state.policy])}: ${fmt(a[ix].value,3)}</title></circle><circle cx="${X(ix)}" cy="${Y(b[ix].value)}" r="5" fill="#d44f5d" stroke="#fff" stroke-width="2"><title>${safe(M.policyNames[state.compare])}: ${fmt(b[ix].value,3)}</title></circle></svg>`;
 $('legendPrimary').textContent=M.policyNames[state.policy];$('legendCompare').textContent=M.policyNames[state.compare]; $('metricExplanation').textContent=metricExplanations[state.metric]+' Синяя линия — выбранная стратегия, красная — сравниваемая. Это условные результаты модели.';
}
const positions={RUS:[255,75],BLR:[110,122],KAZ:[312,186],KGZ:[205,260],UZB:[295,293],TJK:[385,283],TKM:[380,218],ARM:[87,246]};
const actionLevels=[
 ['Диверсифицировать торговлю','Сохранить торговые условия','Углублять региональную торговлю'],
 ['Накапливать резервы','Умеренные инвестиции','Предлагать совместные проекты'],
 ['Сохранять автономию','Вести переговоры','Выдвигать институциональные инициативы'],
 ['Минимальная защита от кризисов','Умеренная защита','Усиленная защита'],
 ['Ориентация на внешние рынки','Работа с действующими партнерами','Развитие регионального партнерства'],
 ['Сохранять ограничения','Сохранять действующие условия','Развивать согласованную трудовую мобильность']
];
const metricExplanations={
 mean_growth_pct:'Средний модельный темп роста ВВП восьми стран за год, в процентах.',
 new_projects:'Количество новых совместных проектов, согласованных странами за год. Запуск проекта не означает немедленного дохода.',
 projects_matured:'Сколько ранее начатых проектов достигли стадии отдачи за год. В модели она появляется с задержкой.',
 trade_usd_total:'Сумма моделируемых экспортных потоков между странами, показанная в млрд долларов; это не исторические данные 2025–2050 годов.',
 capital_budget_total:'Суммарный доступный капитал восьми государств в условных единицах расчетной модели.',
 mean_reward:'Внутренняя оценка действий алгоритмом. Это не прибыль и не общественное благосостояние; использовать ее как единственную меру успеха нельзя.',
 network_strength:'Условный индекс межгосударственной связности внутри модели. Он отличается от исторической схемы торговли за 2024 год.'
};
const policyExplanations={
 MAPPO_GREEDY:'ИИ выбирает наиболее вероятное действие обученной политики для каждого государства. Это не означает, что действие обязательно самое выгодное.',
 MAPPO:'ИИ выбирает действия с учетом их вероятностей; при сходных условиях решения могут различаться между расчетами.',
 BARGAIN:'Все страны действуют по заранее установленным правилам переговоров, инвестиций и сотрудничества. Это контрольный вариант для сравнения.',
 NEUTRAL:'Государства сохраняют преимущественно нейтральные решения и не выдвигают новые крупные инициативы. Это контрольная стратегия.'
};
const scenarioQuestions={
 S01:'Как отличаются решения стран при изменении условий сырьевых рынков?',
 S02:'Какие стратегии сохраняют ресурсы и позволяют продолжать сотрудничество при финансовых ограничениях?',
 S03:'Как меняются торговля и совместные проекты при перестройке торговых связей?',
 S04:'Что происходит с проектами, когда меняются инвестиционные условия?',
 S05:'Как страны ведут переговоры и заключают соглашения при разных стратегиях?',
 S06:'Какие различия возникают в координации и числе соглашений?',
 S07:'Как распределяются результаты совместных решений между участниками?',
 S08:'Как меняются число и отдача совместных инвестиционных проектов?',
 S09:'Как сочетаются экономические решения и выбор политики трудовой мобильности?',
 S10:'Как стратегии реагируют на сценарий, связанный с водными ресурсами?',
 S11:'Как ведут себя страны в условиях развития транспортных коридоров?',
 S12:'Чем различаются решения при сценарии энергетической интеграции?',
 S13:'Как стратегии ведут себя при изменении мировой торговли?',
 S14:'Какие решения принимают государства при внешних финансовых ограничениях?',
 S15:'Как страны реагируют на условия технологических изменений?',
 S16:'Что происходит при появлении новых рыночных возможностей?',
 S17:'Как стратегии проходят несколько последовательных кризисных воздействий?',
 S18:'Что происходит, когда несколько неблагоприятных воздействий накладываются друг на друга?',
 S19:'Какие решения сохраняются при длительном периоде адаптации?',
 S20:'Как в условиях стрессового сценария меняются действия государств и их сотрудничество?'
};
function availableFlows(){return D.trade2024.filter(([a,b,v,observed])=>a!==b&&Boolean(observed)&&v!=null&&Number.isFinite(Number(v))&&v>0);}
function tradeAmount(usd){if(usd>=1e9)return fmt(usd/1e9,2)+' млрд $';if(usd>=1e6)return fmt(usd/1e6,1)+' млн $';return fmt(usd/1e3,0)+' тыс. $';}
function renderNetwork(){
 const flows=availableFlows();const pairs=new Map();
 flows.forEach(([from,to,usd])=>{const ids=[from,to].sort();let key=ids.join('|');if(!pairs.has(key))pairs.set(key,{key,a:ids[0],b:ids[1],total:0,flows:[]});const e=pairs.get(key);e.total+=usd;e.flows.push({from,to,usd});});
 const totals=[...pairs.values()],maxValue=Math.max(1,...totals.map(e=>e.total));
 const lines=totals.map(e=>{
  const [ax,ay]=positions[e.a],[bx,by]=positions[e.b];const highlighted=e.a===state.country||e.b===state.country;
  const width=(1.5+6.5*Math.sqrt(e.total/maxValue)).toFixed(2);
  const info=e.flows.map(f=>`${M.countryNames[f.from]} → ${M.countryNames[f.to]}: ${tradeAmount(f.usd)}`).join('\n');
  return `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}" stroke="${highlighted?'#2362c6':'#739bbd'}" stroke-width="${width}" stroke-opacity="${highlighted?'.86':'.33'}" stroke-linecap="round"><title>${safe(info)}</title></line>`;
 }).join('');
 const nodes=D.countries.map(c=>{const [x,y]=positions[c],is=c===state.country;
  return `<g class="network-node" tabindex="0" role="button" aria-label="Выбрать ${safe(M.countryNames[c])}" data-country="${c}"><circle cx="${x}" cy="${y}" r="${is?25:22}" fill="${is?'#2362c6':'#fff'}" stroke="${is?'#2362c6':'#93afcb'}" stroke-width="2"/><text x="${x}" y="${y+4}" fill="${is?'#fff':'#304963'}" font-size="12" font-weight="700" text-anchor="middle">${c}</text><title>${safe(M.countryNames[c])}</title></g>`;
 }).join('');
 $('network').innerHTML=lines+nodes;
 $('network').querySelectorAll('[data-country]').forEach(n=>{const choose=()=>{state.country=n.dataset.country;renderNetwork();renderCountry();};n.addEventListener('click',choose);n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});});
 $('tradeOverview').textContent=`Торговые связи за 2024 год · ${flows.length} направлений экспорта.`;
 const outgoing=flows.filter(f=>f[0]===state.country),incoming=flows.filter(f=>f[1]===state.country);
 const related=[...outgoing.map(f=>({from:f[0],to:f[1],usd:f[2]})),...incoming.map(f=>({from:f[0],to:f[1],usd:f[2]}))].sort((a,b)=>b.usd-a.usd);
 const rows=related.slice(0,7).map(f=>`<li><span>${safe(M.countryNames[f.from])} <b aria-label="экспортирует в">→</b> ${safe(M.countryNames[f.to])}</span><strong>${tradeAmount(f.usd)}</strong></li>`).join('');
 $('tradePartners').innerHTML=`<div class="trade-heading"><strong>${safe(M.countryNames[state.country])}: торговые партнеры</strong><small>Экспорт из страны: ${outgoing.length}/7 · экспорт в страну: ${incoming.length}/7</small></div>${related.length?`<ul>${rows}</ul>`:'<p>Сведения об экспорте по этому направлению отсутствуют.</p>'}`;
}
function renderCountry(){
 const snapshot=current(),actions=snapshot.actions;
 $('actionPeriod').textContent=`${state.year} · ${M.policyNames[state.policy]}`;
 $('actions').innerHTML=D.countries.map(c=>`<button class="agent-row ${state.country===c?'chosen':''}" data-code="${c}" aria-label="Решения: ${safe(M.countryNames[c])}"><span>${safe(M.countryNames[c])}<small>${c}</small></span><span class="mini-actions">${actions[c].map((v,i)=>`<i title="${safe(M.actionNames[i])}: ${safe((window.EURASIA_GUIDE?.actionDescriptions?.[i]?.levels?.[v]||actionLevels[i][v]))}" class="level level-${v}"></i>`).join('')}</span><span class="chevron">›</span></button>`).join('');
 $('actions').querySelectorAll('[data-code]').forEach(el=>el.addEventListener('click',()=>{state.country=el.dataset.code;renderCountry();renderNetwork();}));
 const h=M.historic(D,state.country),a=actions[state.country];
 const historic=(k,suffix='')=>{const m=h?.[k];return (!m||!m.observed||m.value==null)?'нет сведений':fmt(m.value,k==='population_total'?0:2)+suffix;};
 $('countryDetail').innerHTML=`<div class="country-title"><b>${safe(M.countryNames[state.country])}</b><small>Решения ${state.year} года</small></div><p class="decision-intro">Выбранная стратегия дала этой стране следующие решения:</p><div class="decision-list">${a.map((v,i)=>`<div class="decision-item"><span>${safe(M.actionNames[i])}</span><strong>${safe((window.EURASIA_GUIDE?.actionDescriptions?.[i]?.levels?.[v]||actionLevels[i][v]))}</strong></div>`).join('')}</div><div class="historical-context"><strong>Для справки: наблюдения 2024 года</strong><div class="country-kpis"><span>Рост ВВП <b>${historic('gdp_growth_pct','%')}</b></span><span>Инвестиции / ВВП <b>${historic('investment_share_gdp','%')}</b></span></div></div>`;
}
function renderScenario(){
 const s=D.scenarios.find(e=>e.scenario_id===state.scenario),x=current().values;
 $('scenarioDescription').innerHTML=`<div class="scenario-chip">${safe(s.group)}</div><h3>${safe(window.EURASIA_GUIDE?.scenarioTitles?.[s.scenario_id]||s.name)}</h3><p>${safe(window.EURASIA_GUIDE?.scenarioDescriptions?.[s.scenario_id]?.short||scenarioQuestions[s.scenario_id]||'Как различаются результаты выбранных стратегий?')}</p><p class="scenario-context">Три кризисных события: 2026, 2030 и 2034 годы. Подробности — в разделе «Кризисы».</p>`;
 const items=[['Действующие соглашения',x.agreements],['Проекты, достигшие отдачи за год',x.projects_matured],['Чистая отдача проектов, условные единицы',x.project_benefit_current-x.project_cash_out],['Индекс связей, условный',x.network_strength],['Доступный капитал, условные единицы',x.capital_budget_total],['Оценка политики внутри модели',x.mean_reward]];
 $('reportMetrics').innerHTML=items.map(([k,v])=>`<div><span>${safe(k)}</span><strong>${fmt(v,2)}</strong></div>`).join('');
}
function render(){ $('policyExplanation').textContent=policyExplanations[state.policy]; $('selectedYear').textContent=state.year;$('year').value=state.year;renderStats();renderChart();renderNetwork();renderCountry();renderScenario();}
function download(name,text,mime){let url=URL.createObjectURL(new Blob([text],{type:mime}));let a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);}
function downloadJSON(){download(`eurasia_${state.scenario}_${state.policy}_${state.seed}_${state.year}.json`,JSON.stringify({manifest:D.manifest,snapshot:current(),origin:'V4.7 archived trajectory, not newly calculated'},null,2),'application/json;charset=utf-8');}
function downloadCSV(){download(`eurasia_${state.scenario}_${state.policy}_${state.seed}_2025-2050.csv`,'\ufeff'+M.exportCsv(D,state.scenario,state.policy,state.seed),'text/csv;charset=utf-8');}
window.addEventListener('eurasia:texts-updated',()=>{renderCountry();renderScenario();});
selectSetup();render();
})();
