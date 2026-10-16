/* Дополнительные сценарии «Дикие карты» — все ранее неиспользованные события. */
(function(){
'use strict';
const G=window.EURASIA_GUIDE,D=window.EURASIA_DATA;
if(!G||!D)return;
const escape=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const used=new Set(D.scenarios.flatMap(s=>s.crisis_ids.map(Number)));
const unused=Object.values(G.crisisCatalog).filter(c=>!used.has(Number(c.id))).sort((a,b)=>Number(a.id)-Number(b.id));
const subtitles=["Неожиданные препятствия","Смена условий","Цепочка потрясений","Сложные переговоры","Международная напряженность","Вызовы для экономики","Проверка сотрудничества","Разрывы и возможности","Непредвиденные перемены","Решения под давлением"];
const size=4,count=10;
let seed=(Date.now()>>>0)||1,sets=[];
if(unused.length!==40)throw Error("Исследовательский каталог должен содержать 40 событий, оставшихся за пределами двадцати сценариев");
function random(n){return function(){let t=n+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
function shuffle(xs,r){let a=[...xs];for(let i=a.length-1;i>0;i--){let j=Math.floor(r()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
function generate(number){
 seed=(Number(number)>>>0)||1;
 const remaining=shuffle(unused,random(seed));const pack=[];
 for(let i=0;i<count;i++){
  const events=[],types=new Set();
  for(let j=0;j<size;j++){
   let k=remaining.findIndex(c=>!types.has(c.type));
   if(k<0)k=0;
   const item=remaining.splice(k,1)[0];
   if(!item)throw Error("Недостаточно событий для распределения");
   types.add(item.type);events.push(item);
  }
  pack.push({id:"W"+String(i+1).padStart(2,"0"),name:"Дикая карта № "+(i+1),subtitle:subtitles[i],events});
 }
 const ids=pack.flatMap(s=>s.events.map(e=>Number(e.id)));
 if(remaining.length||ids.length!==40||new Set(ids).size!==40||ids.some(id=>used.has(id)))throw Error("Нарушено распределение всех событий");
 sets=pack;updatePicker();return pack;
}
function updatePicker(){
 const select=document.getElementById("wildcardPicker"),summary=document.getElementById("wildcardSummary");
 if(!select||!summary)return;
 const old=select.value;
 select.innerHTML='<option value="">Выберите дополнительный сценарий</option>'+sets.map(s=>'<option value="'+s.id+'">'+escape(s.name+" — "+s.subtitle)+'</option>').join('');
 select.value=sets.some(x=>x.id===old)?old:'';
 const selected=sets.find(x=>x.id===select.value);
 summary.textContent=selected?selected.name+": "+selected.events.map((e,i)=>(2026+3*i)+" — "+e.name).join("; ")+". Итоги рассчитываются в новой игровой партии для переговорной и нейтральной стратегий.":
 "Десять дополнительных сценариев охватывают все сорок ранее неиспользованных кризисов. В каждом по четыре события.";
}
function exportSelection(){
 const payload={title:"Евразия 2050 — Дикие карты",purpose:"Игровые условия для будущего расчетного движка",base:"V4.7",seed,
 events_total:40,scenarios:sets.map(s=>({id:s.id,name:s.name,subtitle:s.subtitle,events:s.events.map((e,i)=>({
 id:Number(e.id),name:e.name,type:e.type,intensity:e.intensity,duration:e.duration,
 affected:e.affected,scheduled_start:2026+3*i
 }))}))};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json;charset=utf-8"}));
 const a=document.createElement("a");a.href=url;a.download="evrazia2050_dikie_karty_"+seed+".json";
 document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function render(box){
 const cards=sets.map((s,k)=>'<article class="guide-card wild-card"><span class="guide-code">ДОПОЛНИТЕЛЬНЫЙ СЦЕНАРИЙ '+(k+1)+'</span><h3>'+escape(s.name+" — "+s.subtitle)+'</h3>'+
 '<p>Четыре события, случайно выбранных из оставшейся части каталога. Последствия рассчитываются в новой игровой партии для переговорной и нейтральной стратегий.</p>'+
 '<ol class="wild-events">'+s.events.map((c,i)=>'<li><span class="wild-year">'+(2026+3*i)+'</span><div><b>'+escape(c.name)+'</b><small>'+escape(G.crisisTypes[c.type]||c.type)+' · интенсивность '+Number(c.intensity).toLocaleString("ru-RU")+' · продолжительность '+c.duration+' '+(c.duration===1?"год":"года")+'</small><p>'+escape(c.note||"")+'</p></div></li>').join('')+'</ol></article>').join('');
 box.innerHTML='<p class="reference-intro"><b>Все 100 кризисов распределены:</b> 60 входят в двадцать исходных сценариев, оставшиеся 40 — в десять дополнительных. Один кризис входит ровно в один сценарий. Номер жеребьевки позволяет воспроизвести тот же состав событий.</p>'+
 '<div class="wild-toolbar"><button type="button" class="small-guide-action" id="wildRegen">Новая жеребьевка</button><label>Номер жеребьевки <input id="wildSeed" type="number" min="1" max="4294967295" step="1" value="'+seed+'"></label><button type="button" class="small-guide-action" id="wildApply">Восстановить жеребьевку</button><button type="button" class="small-guide-action" id="wildSave">Скачать условия</button></div>'+
 '<p class="wild-warning"><b>Расчет последствий:</b> откройте «Вашу партию» и выберите «Дикую карту». Текущий движок рассчитывает её для переговорной и нейтральной стратегий; архивные траектории MAPPO доступны только для исходных 20 сценариев.</p>'+
 '<div class="guide-grid">'+cards+'</div>';
 box.querySelector("#wildRegen").addEventListener("click",()=>{generate((Date.now()+Math.floor(Math.random()*1000000))>>>0);render(box);});
 box.querySelector("#wildApply").addEventListener("click",()=>{
 const v=Number(box.querySelector("#wildSeed").value);
 if(Number.isInteger(v)&&v>0&&v<=4294967295){generate(v);render(box);}
 else{box.querySelector("#wildSeed").setCustomValidity("Введите целое число от 1 до 4294967295");box.querySelector("#wildSeed").reportValidity();box.querySelector("#wildSeed").setCustomValidity("");}
 });
 box.querySelector("#wildSave").addEventListener("click",exportSelection);
 updatePicker();
}
generate(seed);
const select=document.getElementById("wildcardPicker");
if(select)select.addEventListener("change",updatePicker);
updatePicker();
window.EURASIA_WILDCARDS={render,generate,getSets:()=>sets.map(s=>({id:s.id,crisis_ids:s.events.map(e=>Number(e.id))})),getAvailableIds:()=>unused.map(e=>Number(e.id)),getSeed:()=>seed};
})();