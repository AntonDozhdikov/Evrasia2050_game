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
 $('scenario').innerHTML=D.scenarios.map(s=>`<option value="${safe(s.scenario_id)}">${safe(s.scenario_id+' · '+s.name)}</option>`).join('');
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
 $(deltaId).innerHTML=`<span class="${diff>0?'pos':diff<0?'neg':'neutral'}">${signed(diff,digits)}${suffix}</span> к ${safe(state.compare)}`;
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
 $('legendPrimary').textContent=M.policyNames[state.policy];$('legendCompare').textContent=M.policyNames[state.compare];
}
const positions={RUS:[255,75],BLR:[110,122],KAZ:[312,186],KGZ:[205,260],UZB:[295,293],TJK:[385,283],TKM:[380,218],ARM:[87,246]};
function renderNetwork(){
 let edges=[];for(let r of D.trade2024){const [a,b,v,observed]=r;if(!observed||!v||a===b)continue;const key=[a,b].sort().join('–');let e=edges.find(x=>x.key===key);if(!e){e={key,a,b,total:0};edges.push(e);}e.total+=v;}
 edges.sort((a,b)=>a.total-b.total);
 let lines=edges.map(e=>{let [ax,ay]=positions[e.a],[bx,by]=positions[e.b];return `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}" stroke="#94afcf" stroke-width="${Math.min(8,1+Math.log10(1+e.total)/2.5).toFixed(1)}" stroke-opacity="0.21"/>`}).join('');
 const nodes=D.countries.map(c=>{let [x,y]=positions[c],is=c===state.country;return `<g class="network-node" tabindex="0" role="button" aria-label="${safe(M.countryNames[c])}" data-country="${c}"><circle cx="${x}" cy="${y}" r="${is?24:21}" fill="${is?'#2362c6':'#fff'}" stroke="${is?'#2362c6':'#a7bbd3'}" stroke-width="2"/><text x="${x}" y="${y+4}" fill="${is?'#fff':'#304963'}" font-size="12" font-weight="700" text-anchor="middle">${c}</text></g>`}).join('');
 $('network').innerHTML=lines+nodes;
 $('network').querySelectorAll('[data-country]').forEach(n=>{n.addEventListener('click',()=>{state.country=n.dataset.country;renderNetwork();renderCountry();});n.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();state.country=n.dataset.country;renderNetwork();renderCountry();}});});
}
function renderCountry(){
 const snapshot=current(),actions=snapshot.actions;
 $('actionPeriod').textContent=`${state.year} · ${state.policy}`;
 $('actions').innerHTML=D.countries.map(c=>`<button class="agent-row ${state.country===c?'chosen':''}" data-code="${c}"><span>${safe(M.countryNames[c])}<small>${c}</small></span><span class="mini-actions">${actions[c].map((v,i)=>`<i title="${safe(M.actionNames[i])}: ${v}" class="level level-${v}"></i>`).join('')}</span><span class="chevron">›</span></button>`).join('');
 $('actions').querySelectorAll('[data-code]').forEach(el=>el.addEventListener('click',()=>{state.country=el.dataset.code;renderCountry();renderNetwork();}));
 const h=M.historic(D,state.country),a=actions[state.country];
 const historic=(k,suffix='')=>{let m=h?.[k];if(!m||m.value==null)return 'нет наблюдения';return fmt(m.value,k==='population_total'?0:2)+suffix+(m.observed?'':' · без подтверждения наблюдения');};
 $('countryDetail').innerHTML=`<div class="country-title"><b>${safe(M.countryNames[state.country])}</b><small>Данные 2024 · решения ${state.year}</small></div><div class="country-kpis"><span>Рост ВВП <strong>${historic('gdp_growth_pct','%')}</strong></span><span>Инвестиции / ВВП <strong>${historic('investment_share_gdp','%')}</strong></span></div><div class="action-chips">${a.map((v,i)=>`<span>${safe(M.actionNames[i])} <b>${v}/2</b></span>`).join('')}</div>`;
}
function renderScenario(){
 const s=D.scenarios.find(e=>e.scenario_id===state.scenario),x=current().values,other=compare().values;
 $('scenarioDescription').innerHTML=`<div class="scenario-chip">${safe(s.group)}</div><h3>${safe(s.name)}</h3><p>${safe(s.description)}</p><div class="scenario-crisis">Каталожные кризисы: <b>${s.crisis_ids.map(safe).join(', ')}</b><small>Их календарная активность определяется архивной траекторией.</small></div>`;
 let items=[['Соглашения за год',x.agreements],['Созревших проектов',x.projects_matured],['Чистая проектная отдача за год', x.project_benefit_current-x.project_cash_out],['Сетевой показатель',x.network_strength],['Бюджет стран',x.capital_budget_total],['Награда среды',x.mean_reward]];
 $('reportMetrics').innerHTML=items.map(([k,v])=>`<div><span>${safe(k)}</span><strong>${fmt(v,2)}</strong></div>`).join('');
}
function render(){ $('selectedYear').textContent=state.year;$('year').value=state.year;renderStats();renderChart();renderNetwork();renderCountry();renderScenario();}
function download(name,text,mime){let url=URL.createObjectURL(new Blob([text],{type:mime}));let a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);}
function downloadJSON(){download(`eurasia_${state.scenario}_${state.policy}_${state.seed}_${state.year}.json`,JSON.stringify({manifest:D.manifest,snapshot:current(),origin:'V4.7 archived trajectory, not newly calculated'},null,2),'application/json;charset=utf-8');}
function downloadCSV(){download(`eurasia_${state.scenario}_${state.policy}_${state.seed}_2025-2050.csv`,'\ufeff'+M.exportCsv(D,state.scenario,state.policy,state.seed),'text/csv;charset=utf-8');}
selectSetup();render();
})();
