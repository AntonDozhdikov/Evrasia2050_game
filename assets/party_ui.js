/* Подготовка новой партии. Экономические итоги вычисляются только проверенным игровым движком. */
(function(){
'use strict';
const Core=window.EurasiaParty,D=window.EURASIA_DATA,M=window.EurasiaModel,G=window.EURASIA_GUIDE,W=window.EURASIA_WILDCARDS;
if(!Core||!D||!M||!G||!W)return;
const $=id=>document.getElementById(id),KEY='evrasia2050:party-draft:v1';
const escape=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let party=Core.make(),lastCountry='RUS',flash='';
function store(){try{localStorage.setItem(KEY,JSON.stringify(party));if(typeof window.dispatchEvent==='function'&&typeof Event==='function')window.dispatchEvent(new Event('eurasia:party-edited'));return true;}catch(_){return false;}}
function restore(){try{let data=localStorage.getItem(KEY);if(data){let p=JSON.parse(data);Core.validate(p);party=Core.clone(p);if(party.wildcardSeed)W.generate(party.wildcardSeed);}}catch(_){party=Core.make();}}
function baseline(country,year){
 if(party.scenario.startsWith('W'))return Array(6).fill(1);
 try{return M.at(D,party.scenario,party.policy,party.seed,year).actions[country].slice();}
 catch(_){return Array(6).fill(1);}
}
function line(msg,ok=true){let node=$('partyMessage');node.textContent=msg;node.classList.toggle('party-error',!ok);flash=msg;}
function configureOptions(){
 const opts=D.scenarios.map(s=>'<option value="'+s.scenario_id+'">'+s.scenario_id+' · '+escape(G.scenarioTitles[s.scenario_id]||s.name)+'</option>')
 .concat(W.getSets().map(s=>'<option value="'+s.id+'">'+escape(s.id+' · Дикая карта № '+Number(s.id.slice(1)))+'</option>'));
 $('partyScenario').innerHTML=opts.join('');
 $('partyPolicy').innerHTML=Object.entries(M.policyNames).map(([id,title])=>'<option value="'+id+'">'+escape(title)+'</option>').join('');
 $('partyYear').innerHTML=Array.from({length:26},(_,i)=>'<option value="'+(i+2025)+'">'+(i+2025)+'</option>').join('');
}
function optionsLevel(i,selected){
 return G.actionDescriptions[i].levels.map((t,lv)=>'<option value="'+lv+'" '+(selected===lv?'selected':'')+'>'+lv+' — '+escape(t)+'</option>').join('');
}
function render(){
 configureOptions();
 $('partyScenario').value=party.scenario;
 $('partyPolicy').value=party.policy;
 $('partySeed').value=party.seed;
 $('partyYear').value=party.year;
 const countries=$('partyCountries');
 countries.innerHTML=Core.COUNTRIES.map(c=>'<label class="party-country '+(party.controlled.includes(c)?'chosen':'')+'"><input type="checkbox" value="'+c+'" '+(party.controlled.includes(c)?'checked':'')+'><span>'+escape(M.countryNames[c])+'</span></label>').join('');
 countries.querySelectorAll('input').forEach(input=>input.addEventListener('change',()=>onCountriesChange(input)));
 const current=party.years[party.year]||{};
 if(!party.controlled.includes(lastCountry))lastCountry=party.controlled[0];
 const tabs=$('partyCountryTabs');
 if(tabs){
  tabs.innerHTML=party.controlled.map(country=>'<button type="button" role="tab" class="party-tab '+(country===lastCountry?'active':'')+'" aria-selected="'+String(country===lastCountry)+'" data-party-tab="'+country+'">'+escape(M.countryNames[country])+(current[country]?' <span class="party-tab-check">✓</span>':'')+'</button>').join('');
  tabs.querySelectorAll('button[data-party-tab]').forEach(button=>button.addEventListener('click',()=>{
   lastCountry=button.dataset.partyTab;
   tabs.querySelectorAll('button[data-party-tab]').forEach(btn=>{const active=btn.dataset.partyTab===lastCountry;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));});
   $('partyActions').querySelectorAll('.party-country-card').forEach(card=>{card.hidden=card.dataset.partyCard!==lastCountry;});
  }));
 }
 const forms=party.controlled.map(country=>{
  const levels=current[country]||baseline(country,party.year);
  return '<article class="party-country-card" data-party-card="'+country+'" '+(country!==lastCountry?'hidden':'')+'><header><h3>'+escape(M.countryNames[country])+'</h3><span class="party-state">'+(current[country]?'Решения сохранены':'Новый ход')+'</span></header><div class="party-decisions">'+G.actionDescriptions.map((d,i)=>'<label><span>'+escape(d.name)+'</span><select data-party-country="'+country+'" data-party-action="'+i+'">'+optionsLevel(i,levels[i])+'</select></label>').join('')+'</div></article>';
 });
 $('partyActions').innerHTML=forms.join('');
 $('partyActions').querySelectorAll('select[data-party-country]').forEach(select=>select.addEventListener('change',()=>window.dispatchEvent(new Event('eurasia:party-edited'))));
 $('partyCount').textContent=Object.keys(party.years).length+' из 26 лет сохранено';
 $('partyNext').disabled=party.year===2050;
 const wild=party.scenario.startsWith('W'),supported=!wild&&D.manifest.seeds.includes(party.seed);
 $('partyContext').innerHTML=wild?
  '<strong>Дикая карта:</strong> четыре кризиса. Партия рассчитывается по выбранной стратегии.':
  '<strong>'+escape(G.scenarioTitles[party.scenario]||party.scenario)+'.</strong> '+(supported?
   'Начальные решения взяты из выбранной стратегии.':
   'Начальный уровень решений — средний.');
 $('partyNotComputed').textContent='Сохраните год, чтобы зафиксировать решения, затем рассчитайте итог до 2050 года.';
}
function onCountriesChange(input){
 const choices=Array.from($('partyCountries').querySelectorAll('input:checked')).map(x=>x.value);
 if(!choices.length){input.checked=true;line('В партии требуется хотя бы одна управляемая страна.',false);return;}
 if(!savePendingIfAny()){render();return;}
 party=Core.control(party,choices);if(!store())line('Хранилище браузера недоступно. Скачайте файл партии.',false);render();
}
function decisionsForYear(){
 const rows={};
 $('partyActions').querySelectorAll('select[data-party-country]').forEach(select=>{
  const c=select.dataset.partyCountry,k=Number(select.dataset.partyAction);
  if(!rows[c])rows[c]=Array(6).fill(1);
  rows[c][k]=Number(select.value);
 });
 return rows;
}
function saveYear(){
 try{
  const values=decisionsForYear();
  for(const c of party.controlled)party=Core.plan(party,party.year,c,values[c]);
  const stored=store();render();
  line('Решения '+party.year+' года сохранены для '+party.controlled.length+' государств.'+(stored?'':' Скачайте файл партии: сохранение в браузере недоступно.'),stored);
  return true;
 }catch(e){line(e.message,false);return false;}
}
function hasPendingDecisions(){
 const rows=decisionsForYear(),saved=party.years[party.year]||{};
 return party.controlled.some(country=>{
  const values=rows[country],previous=saved[country]||baseline(country,party.year);
  return values&&values.some((level,i)=>level!==previous[i]);
 });
}
function savePendingIfAny(){return !hasPendingDecisions()||saveYear();}
function showYear(e){
 const year=Number(e.target.value);
 if(!savePendingIfAny()){render();return;}
 party=Core.goto(party,year);store();render();
}
function changeScenario(){
 if((Object.keys(party.years).length||hasPendingDecisions())&&!confirm('Новые условия начнут отдельную партию. Все решения текущей партии будут заменены. Продолжить?')){
  $('partyScenario').value=party.scenario;$('partyPolicy').value=party.policy;$('partySeed').value=party.seed;
  return;
 }
 const scenario=$('partyScenario').value,policy=$('partyPolicy').value,seed=Number($('partySeed').value);
 try{
  let q=Core.setScenario(party,scenario,policy,seed);
  if(scenario.startsWith('W'))q.wildcardSeed=W.getSeed();
  party=q;store();render();line('Условия партии изменены.');
 }catch(e){line(e.message,false);render();}
}
function download(payload,name){
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportParty(){
 if(!savePendingIfAny())return;
 Core.validate(party);
 let out=Core.clone(party);
 if(party.scenario.startsWith('W')){
  out.wildcardSeed=W.getSeed();
  out.wildcardEvents=W.getSets().find(x=>x.id===party.scenario)?.crisis_ids||[];
 }
 download(out,'evrazia2050_party_'+party.scenario+'_'+party.year+'.json');
 line('Файл решений готов к сохранению.');
}
async function importParty(file){
 if(!file)return;
 try{
  if(file.size>1048576)throw Error('Файл превышает допустимый объем 1 МБ');
  const p=JSON.parse(await file.text());Core.validate(p);
  if(p.scenario.startsWith('W')&&p.wildcardSeed){
   W.generate(p.wildcardSeed);
   const found=W.getSets().find(x=>x.id===p.scenario);
   if(!found||p.wildcardEvents&&JSON.stringify(p.wildcardEvents)!==JSON.stringify(found.crisis_ids))throw Error('Состав кризисов не совпадает с сохраненной жеребьевкой');
  }
  party=Core.clone(p);store();render();line('Партия загружена: '+Object.keys(party.years).length+' игровых лет.');
 }catch(e){line('Загрузка отклонена: '+e.message,false);}
 $('partyFile').value='';
}
$('partyScenario').addEventListener('change',changeScenario);
$('partyPolicy').addEventListener('change',changeScenario);
$('partySeed').addEventListener('change',changeScenario);
$('partyYear').addEventListener('change',showYear);
$('partySave').addEventListener('click',saveYear);
$('partyNext').addEventListener('click',()=>{if(saveYear()&&party.year<2050){party=Core.goto(party,party.year+1);store();render();}});
$('partyExport').addEventListener('click',exportParty);
$('partyImport').addEventListener('click',()=>$('partyFile').click());
$('partyFile').addEventListener('change',e=>importParty(e.target.files[0]));
$('partyNew').addEventListener('click',()=>{if((!Object.keys(party.years).length&&!hasPendingDecisions())||confirm('Начать новую партию? Все решения текущей партии будут заменены.')){let selected=party.controlled.slice();party=Core.control(Core.make(),selected);lastCountry=selected[0];store();render();line('Новая партия создана.');}});
const quick=$('uxQuickStart');
if(quick)quick.addEventListener('click',()=>{
 if((Object.keys(party.years).length||hasPendingDecisions())&&!confirm('Быстрый старт создаст новую партию. Скачайте сохраненные решения, если они вам нужны. Продолжить?'))return;
 party=Core.control(Core.make({scenario:'S01',policy:'BARGAIN',seed:163}),['RUS']);
 lastCountry='RUS';store();render();
 line('Россия выбрана. Определите решения на 2025 год — и начните игру.');
 $('partyActions').scrollIntoView({behavior:'smooth',block:'center'});
});
window.addEventListener('eurasia:texts-updated',render);
window.EurasiaPartyUI={saveCurrentYear:saveYear};
restore();render();
})();