/* «Дикие карты»: четыре воспроизводимых набора из неиспользованных кризисных событий V4.7. */
(function(){
'use strict';
const G=window.EURASIA_GUIDE,D=window.EURASIA_DATA;
if(!G||!D)return;
const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const used=new Set(D.scenarios.flatMap(s=>s.crisis_ids));
const available=Object.values(G.crisisCatalog).filter(c=>!used.has(Number(c.id))).sort((a,b)=>Number(a.id)-Number(b.id));
const titles=['Неожиданный поворот','Цепочка событий','Новые ограничения','Сложная развилка'];
const names=['Дикая карта I','Дикая карта II','Дикая карта III','Дикая карта IV'];
let seed=(Date.now()>>>0)||1,sets=[],container=null;
function random(n){return function(){let t=n+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
function shuffle(list,rng){let a=[...list];for(let i=a.length-1;i>0;i--){let j=Math.floor(rng()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
function generate(newSeed){
 seed=Number(newSeed)>>>0||1;
 const rng=random(seed),options=shuffle(available,rng),selected=[],others=[];
 // Within each card prefer three different types; no event repeats between cards.
 for(let k=0;k<4;k++){
  const row=[],types=new Set();
  for(let j=0;j<3;j++){
   let ix=options.findIndex(e=>!types.has(e.type));
   if(ix<0)ix=0;
   const ev=options.splice(ix,1)[0];if(!ev)throw Error('Недостаточно событий для четырех подборок');
   types.add(ev.type);row.push(ev);selected.push(ev.id);
  }
  others.push({id:'W'+String(k+1).padStart(2,'0'),name:names[k],subtitle:titles[k],events:row});
 }
 if(new Set(selected).size!==12||selected.some(x=>used.has(Number(x))))throw Error('Нарушена уникальность неиспользованных событий');
 sets=others;return sets;
}
function save(){
 const payload={description:'Четыре сценария «Дикие карты» для будущего игрового движка «Евразия 2050»',status:'предварительные условия; новые расчеты V4.7 для них пока отсутствуют',base_research:'V4.7',seed,source_unused_events:available.length,
  scenarios:sets.map(s=>({id:s.id,name:s.name,events:s.events.map((c,i)=>({id:Number(c.id),name:c.name,type:c.type,intensity:c.intensity,duration:c.duration,affected:c.affected,start_year:2026+i*4}))}))};
 const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='evrazia2050_dikie_karty_'+seed+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function render(node){
 container=node;if(!sets.length)generate(seed);
 const cards=sets.map((s,i)=>'<article class="guide-card wild-card"><span class="guide-code">ДОПОЛНИТЕЛЬНЫЙ СЦЕНАРИЙ '+(i+1)+'</span><h3>'+esc(s.name)+' — '+esc(s.subtitle)+'</h3>'+
 '<p>Три случайных кризиса из неиспользованной части каталога. Условия подготовлены для будущего игрового расчета; экономические результаты еще не получены.</p>'+
 '<ol class="wild-events">'+s.events.map((e,j)=>'<li><span class="wild-year">'+(2026+j*4)+'</span><div><b>'+esc(e.name)+'</b><small>'+esc(G.crisisTypes[e.type]||e.type)+' · интенсивность '+Number(e.intensity).toLocaleString('ru-RU')+' · длительность '+e.duration+' '+(e.duration===1?'год':'года')+'</small><p>'+esc(e.note||'Предполагаемое внешнее воздействие в рамках сценарной модели.')+'</p></div></li>').join('')+'</ol></article>').join('');
 node.innerHTML='<p class="reference-intro"><strong>'+available.length+' событий из 100</strong> ранее не использовались в исходных двадцати сценариях. Четыре дополнительных набора формируются случайно: по три события без повторов между наборами.</p>'+
 '<div class="wild-toolbar"><button class="small-guide-action" id="wildRegen">Перемешать события заново</button><label>Номер жеребьевки <input id="wildSeed" type="number" min="1" max="4294967295" step="1" value="'+seed+'"></label><button class="small-guide-action" id="wildApply">Повторить по номеру</button><button class="small-guide-action" id="wildSave">Сохранить условия</button></div>'+
 '<p class="wild-warning"><strong>Пока без расчета последствий.</strong> Для этих сочетаний нет сохраненных траекторий V4.7. Их нельзя сопоставлять с графиками двадцати рассчитанных сценариев. Расчет будет доступен после переноса игрового движка.</p><div class="guide-grid">'+cards+'</div>';
 node.querySelector('#wildRegen').addEventListener('click',()=>{generate((Date.now()+Math.floor(Math.random()*1000000))>>>0);render(node);});
 node.querySelector('#wildApply').addEventListener('click',()=>{const n=Number(node.querySelector('#wildSeed').value);if(Number.isInteger(n)&&n>0&&n<=4294967295){generate(n);render(node);}else{node.querySelector('#wildSeed').setCustomValidity('Введите целое число от 1 до 4294967295');node.querySelector('#wildSeed').reportValidity();node.querySelector('#wildSeed').setCustomValidity('');}});
 node.querySelector('#wildSave').addEventListener('click',save);
}
generate(seed);
window.EURASIA_WILDCARDS={render,generate,getSets:()=>sets.map(s=>({id:s.id,crisis_ids:s.events.map(x=>Number(x.id))})),getAvailableIds:()=>available.map(x=>Number(x.id)),getSeed:()=>seed};
})();