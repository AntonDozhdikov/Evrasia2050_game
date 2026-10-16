/* Подготовка новой партии. Экономические итоги вычисляются только проверенным игровым движком. */
(function(){
'use strict';
const Core=window.EurasiaParty,D=window.EURASIA_DATA,M=window.EurasiaModel,G=window.EURASIA_GUIDE,W=window.EURASIA_WILDCARDS;
if(!Core||!D||!M||!G||!W)return;
const $=id=>document.getElementById(id),KEY='evrasia2050:party-draft:v1',SLOTS_KEY='evrasia2050:party-slots:v1',ACTIVE_KEY='evrasia2050:active-slot:v1';
const escape=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let party=Core.make(),lastCountry='RUS',flash='',activeSlot=null;
function readSlots(){
 try{
  const value=JSON.parse(localStorage.getItem(SLOTS_KEY)||'[]');
  if(!Array.isArray(value))return [];
  return value.filter(x=>x&&typeof x.id==='string'&&typeof x.name==='string'&&x.party&&typeof x.party==='object').slice(0,20);
 }catch(_){return [];}
}
function saveSlots(items){localStorage.setItem(SLOTS_KEY,JSON.stringify(items));}
function updateSlotPicker(){
 const select=$('partySlots');
 if(!select)return;
 const items=readSlots();
 select.innerHTML='<option value="">Текущая партия (без имени)</option>'+items.map(x=>'<option value="'+escape(x.id)+'">'+escape(x.name)+'</option>').join('');
 select.value=activeSlot&&items.some(x=>x.id===activeSlot)?activeSlot:'';
 $('partySlotCount').textContent=items.length+' из 20 сохранений';
}
function setActiveSlot(id){
 activeSlot=id||null;
 if(activeSlot)localStorage.setItem(ACTIVE_KEY,activeSlot);
 else localStorage.removeItem(ACTIVE_KEY);
}
function store(notify=true){
 try{
  const json=JSON.stringify(party);
  localStorage.setItem(KEY,json);
  if(activeSlot){
   const slots=readSlots(),slot=slots.find(x=>x.id===activeSlot);
   if(slot){slot.party=Core.clone(party);saveSlots(slots);}
   else setActiveSlot(null);
  }
  if(notify&&typeof window.dispatchEvent==='function'&&typeof Event==='function')window.dispatchEvent(new Event('eurasia:party-edited'));
  return true;
 }catch(_){return false;}
}
function verifyWild(p){
 if(!p.scenario.startsWith('W'))return;
 if(!Number.isInteger(p.wildcardSeed)||p.wildcardSeed<1||p.wildcardSeed>4294967295)
  throw Error('В сохранении «Дикой карты» отсутствует номер жеребьёвки. Восстановить состав кризисов невозможно.');
 W.generate(p.wildcardSeed);
 const selected=W.getSets().find(x=>x.id===p.scenario);
 if(!selected)throw Error('Дикая карта не найдена');
 if(p.wildcardEvents&&JSON.stringify(p.wildcardEvents)!==JSON.stringify(selected.crisis_ids))
  throw Error('Состав кризисов не совпадает с номером жеребьёвки');
}
function restore(){
 try{
  const data=localStorage.getItem(KEY),id=localStorage.getItem(ACTIVE_KEY);
  if(data){const p=JSON.parse(data);Core.validate(p);verifyWild(p);party=Core.clone(p);}
  if(id&&readSlots().some(x=>x.id===id))activeSlot=id;
 }catch(e){party=Core.make();activeSlot=null;flash='Не удалось восстановить сохранение: '+e.message+'. Проверьте ранее скачанный файл партии.';}
}
function saveNamedSlot(){
 if(!savePendingIfAny())return;
 const items=readSlots(),current=items.find(x=>x.id===activeSlot);
 let name=prompt('Название сохраняемой партии',current?current.name:'Партия '+(items.length+1));
 if(name===null)return;
 name=name.trim().replace(/\s+/g,' ').slice(0,64);
 if(!name){line('Введите название партии.',false);return;}
 if(!current&&items.length>=20){line('Достигнут предел в 20 сохранений. Удалите ненужную партию.',false);return;}
 if(items.some(x=>x.name===name&&x.id!==activeSlot)){line('Сохранение с таким названием уже существует.',false);return;}
 try{
  if(current){current.name=name;current.party=Core.clone(party);}
  else{const id='save-'+Date.now()+'-'+Math.floor(Math.random()*1e9);items.push({id,name,party:Core.clone(party)});setActiveSlot(id);}
  saveSlots(items);store(false);updateSlotPicker();
  line('Партия «'+name+'» сохранена.');
 }catch(e){line('Не удалось сохранить партию: '+e.message,false);}
}
function loadNamedSlot(){
 const id=$('partySlots').value,item=readSlots().find(x=>x.id===id);
 if(!item){line('Выберите именованное сохранение.',false);return;}
 if((Object.keys(party.years).length||hasPendingDecisions())&&!confirm('Открыть «'+item.name+'»? Текущая партия будет заменена.'))return;
 try{
  Core.validate(item.party);verifyWild(item.party);
  party=Core.clone(item.party);setActiveSlot(id);lastCountry=party.controlled[0];
  if(!store())throw Error('Не удалось записать партию в браузер');
  render();line('Загружена партия «'+item.name+'».');
 }catch(e){line('Загрузка отклонена: '+e.message,false);}
}
function deleteNamedSlot(){
 const id=$('partySlots').value,item=readSlots().find(x=>x.id===id);
 if(!item){line('Выберите сохранение для удаления.',false);return;}
 if(!confirm('Удалить сохранение «'+item.name+'»? Текущая партия останется открытой.'))return;
 try{
  saveSlots(readSlots().filter(x=>x.id!==id));
  if(activeSlot===id)setActiveSlot(null);
  updateSlotPicker();line('Именованное сохранение удалено.');
 }catch(e){line('Удаление невозможно: '+e.message,false);}
}
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
 updateSlotPicker();
 $('partyNext').disabled=party.year===2050;
 const wild=party.scenario.startsWith('W'),supported=!wild&&D.manifest.seeds.includes(party.seed);
 $('partyContext').innerHTML=wild?
  '<strong>«Дикая карта» '+escape(party.scenario)+':</strong> четыре кризиса. Номер жеребьёвки: <b>'+escape(party.wildcardSeed||'не сохранён')+'</b>; номер экономического расчёта: <b>'+escape(party.seed)+'</b>. Доступны переговорная и нейтральная стратегии.':
  '<strong>'+escape(G.scenarioTitles[party.scenario]||party.scenario)+'.</strong> '+(supported?
   'Начальные решения взяты из выбранной стратегии. MAPPO использует сохранённые последовательности действий, а переговорная стратегия пересчитывается по состоянию модели.':
   'Начальный уровень решений — средний. Для этого номера расчёта доступны переговорная и нейтральная стратегии.');
 $('partyNotComputed').textContent='Вы задаёте решения только для выбранных лет. В остальные годы государства действуют по выбранным стратегиям. Расчёт всегда охватывает 2025–2050 годы.';
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
  const values=decisionsForYear(),saved=party.years[party.year]||{};
  if(party.controlled.every(c=>saved[c]&&values[c]&&saved[c].every((v,i)=>v===values[c][i]))){
   line('Решения '+party.year+' года уже сохранены.');
   return true;
  }
  for(const c of party.controlled)party=Core.plan(party,party.year,c,values[c]);
  const stored=store();render();
  line('Решения '+party.year+' года сохранены для '+party.controlled.length+' государств.'+(stored?'':' Скачайте файл партии: сохранение в браузере недоступно.'),stored);
  return stored;
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
 party=Core.goto(party,year);store(false);render();window.dispatchEvent(new Event('eurasia:year-navigated'));
}
function changeScenario(){
 if((Object.keys(party.years).length||hasPendingDecisions())&&!confirm('Новые условия начнут отдельную партию. Все решения текущей партии будут заменены. Продолжить?')){
  $('partyScenario').value=party.scenario;$('partyPolicy').value=party.policy;$('partySeed').value=party.seed;
  return;
 }
 const scenario=$('partyScenario').value,requestedPolicy=$('partyPolicy').value,seed=Number($('partySeed').value);
 try{
  const restricted=scenario.startsWith('W')||!D.manifest.seeds.includes(seed);
  const policy=restricted&&requestedPolicy.startsWith('MAPPO')?'BARGAIN':requestedPolicy;
  let q=Core.setScenario(party,scenario,policy,seed);
  if(scenario.startsWith('W')){q.wildcardSeed=W.getSeed();q.wildcardEvents=W.getSets().find(x=>x.id===scenario).crisis_ids.slice();}
  party=q;setActiveSlot(null);store();render();
  line('Условия партии изменены.'+(policy!==requestedPolicy?' Для этих условий выбрана переговорная стратегия: архивная MAPPO недоступна.':''));
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
  out.wildcardSeed=party.wildcardSeed;
  W.generate(party.wildcardSeed);
  out.wildcardEvents=W.getSets().find(x=>x.id===party.scenario)?.crisis_ids||[];
 }
 download(out,'evrazia2050_party_'+party.scenario+'_'+party.year+'.json');
 line('Файл решений готов к сохранению.');
}
let lastImport=Promise.resolve(false),importSerial=0;
async function importParty(file){
 const request=++importSerial;
 if(!file)return false;
 try{
  if(file.size>1048576)throw Error('Файл превышает допустимый объем 1 МБ');
  const text=await file.text();
  // If the user selects another file before reading finishes, only the latest import may modify the party.
  if(request!==importSerial)return false;
  const p=JSON.parse(text);Core.validate(p);
  verifyWild(p);
  const next=Core.clone(p);
  party=next;setActiveSlot(null);
  if(!store())throw Error('Не удалось сохранить загруженную партию в браузере');
  render();
  const n=Object.keys(party.years).length;
  line('Партия загружена: '+n+' '+(n%10===1&&n%100!==11?'игровой год':n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?'игровых года':'игровых лет')+'.');
  return true;
 }catch(e){
  if(request===importSerial)line('Загрузка отклонена: '+e.message,false);
  return false;
 }finally{
  if(request===importSerial)$('partyFile').value='';
 }
}
$('partyScenario').addEventListener('change',changeScenario);
$('partyPolicy').addEventListener('change',changeScenario);
$('partySeed').addEventListener('change',changeScenario);
$('partyYear').addEventListener('change',showYear);
$('partySave').addEventListener('click',saveYear);
$('partyNext').addEventListener('click',()=>{if(saveYear()&&party.year<2050){party=Core.goto(party,party.year+1);store(false);render();window.dispatchEvent(new Event('eurasia:year-navigated'));}});
$('partyExport').addEventListener('click',exportParty);
$('partyImport').addEventListener('click',()=>$('partyFile').click());
$('partyFile').addEventListener('change',e=>{lastImport=importParty(e.target.files[0]);});
$('partySlotSave').addEventListener('click',saveNamedSlot);
$('partySlotLoad').addEventListener('click',loadNamedSlot);
$('partySlotDelete').addEventListener('click',deleteNamedSlot);
$('partyNew').addEventListener('click',()=>{if((!Object.keys(party.years).length&&!hasPendingDecisions())||confirm('Начать новую партию? Все решения текущей партии будут заменены.')){let selected=party.controlled.slice();party=Core.control(Core.make(),selected);setActiveSlot(null);lastCountry=selected[0];store();render();line('Новая партия создана.');}});
const quick=$('uxQuickStart');
if(quick)quick.addEventListener('click',()=>{
 if((Object.keys(party.years).length||hasPendingDecisions())&&!confirm('Быстрый старт создаст новую партию. Скачайте сохраненные решения, если они вам нужны. Продолжить?'))return;
 party=Core.control(Core.make({scenario:'S01',policy:'BARGAIN',seed:163}),['RUS']);
 setActiveSlot(null);lastCountry='RUS';store();render();
 line('Россия выбрана. Определите решения на 2025 год — и начните игру.');
 $('partyActions').scrollIntoView({behavior:'smooth',block:'center'});
});
window.addEventListener('eurasia:texts-updated',render);
window.EurasiaPartyUI={saveCurrentYear:saveYear,getCurrent:()=>Core.clone(party),getActiveSlot:()=>activeSlot,get importFinished(){return lastImport;}};
restore();render();if(flash)line(flash,false);
})();