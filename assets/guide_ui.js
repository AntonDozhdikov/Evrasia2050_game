/* Eurasia 2050: explanation and visualisation layer. Original V4.7 numeric data are read-only. */
(function(){
'use strict';
var D=window.EURASIA_DATA,M=window.EurasiaModel,G=window.EURASIA_GUIDE;
if(!D||!M||!G)return;
var $=function(id){return document.getElementById(id);};
var escape=function(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
var fmt=function(x,n){return Number(x).toLocaleString('ru-RU',{maximumFractionDigits:n==null?2:n,minimumFractionDigits:0});};
var selectedTab='scenarios',crisisFilter='scenario',lastReferenceKey='';
var pos={RUS:[255,70],BLR:[112,122],KAZ:[311,184],KGZ:[202,258],UZB:[292,293],TJK:[384,283],TKM:[381,218],ARM:[85,247]};
function view(){
var a=document.querySelector('.agent-row.chosen');
return {scenario:$('scenario').value,policy:$('policy').value,seed:Number($('seed').value),year:Number($('selectedYear').textContent)||2025,country:a?a.dataset.code:'RUS',action:Number($('actionType').value)||0};
}
function scenario(id){return D.scenarios.find(function(x){return x.scenario_id===id;});}
function item(id){return G.crisisCatalog[String(id)];}
function due(id,year){
var s=scenario(id),out=[];if(!s)return out;
s.crisis_ids.forEach(function(eventId,i){var c=item(eventId);if(!c)return;for(var start=2026+4*i;start<=2050;start+=12){var end=Math.min(start+c.duration-1,2050);if(year>=start&&year<=end)out.push(Object.assign({start:start,end:end},c));}});
return out;
}
function launches(sid,eventId){
var s=scenario(sid),i=s?s.crisis_ids.indexOf(eventId):-1,years=[];if(i<0)return years;
for(var y=2026+i*4;y<=2050;y+=12)years.push(y);return years;
}
function showTab(tab){
if(!['scenarios','crises','strategies','actions','wildcards'].includes(tab))return;
selectedTab=tab;lastReferenceKey='';
document.querySelectorAll('[data-guide-detail]').forEach(function(el){el.open=el.dataset.guideDetail===tab;});
renderReference(view());
}
function renderSummaries(v){
var q=G.scenarioDescriptions[v.scenario],p=G.policyDescriptions[v.policy];
$('scenarioShort').textContent=q?q.short:'Сравните способы действий стран и их экономические последствия.';
$('policyExplanation').textContent=p?p.short:'';
}
function renderCrisis(v){
var list=due(v.scenario,v.year),node=$('crisisCurrent'),archive=M.at(D,v.scenario,v.policy,v.seed,v.year);
$('crisisNotice').classList.toggle('is-active',list.length>0);
if(!list.length){node.innerHTML='<strong>В '+v.year+' году кризисных событий по выбранному сценарию нет.</strong><p>Выберите другой год или откройте справочник, чтобы посмотреть последовательность событий.</p>';return;}
var html='<strong>В '+v.year+' году: '+list.length+' '+(list.length===1?'активное событие':'активных события')+'</strong>';
list.forEach(function(c){html+='<div class="current-crisis"><b>'+escape(c.name)+'</b><span>'+escape(G.crisisTypes[c.type]||c.type)+' · интенсивность '+fmt(c.intensity)+' · действует '+c.start+'–'+c.end+'</span><p>'+escape(c.note||'Синтетическое воздействие на экономику восьми стран.')+'</p></div>';});
var n=Number(archive.values.crises_active);if(n!==list.length)html+='<p class="footnote">В исходной траектории число активных воздействий: '+n+'. Календарь отображен по правилам V4.7.</p>';
node.innerHTML=html;
}
function renderMap(v){
var snapshot=M.at(D,v.scenario,v.policy,v.seed,v.year),actions=snapshot.actions,previous=v.year>2025?M.at(D,v.scenario,v.policy,v.seed,v.year-1).actions:null,desc=G.actionDescriptions[v.action],colors=['#dce6f0','#87b4df','#255eaf'];
if(!desc)return;
var counts=[0,1,2].map(function(l){return D.countries.filter(function(c){return actions[c][v.action]===l;}).length;});
var markup='<div class="decision-map-heading"><strong>'+escape(desc.name)+'</strong><small>'+counts[0]+' низкий · '+counts[1]+' средний · '+counts[2]+' высокий</small></div><svg viewBox="0 0 480 350" role="img" aria-label="Решения восьми государств">';
D.countries.forEach(function(c){
var xy=pos[c],level=actions[c][v.action],focused=v.country===c,fullname=M.countryNames[c],act=desc.levels[level],changed=previous&&previous[c][v.action]!==level;
markup+='<g data-decision-country="'+c+'" role="button" tabindex="0" aria-label="'+escape(fullname+': '+act)+'"><circle cx="'+xy[0]+'" cy="'+xy[1]+'" r="'+(focused?31:26)+'" fill="'+colors[level]+'" stroke="'+(focused?'#cd4954':'#fff')+'" stroke-width="'+(focused?4:2)+'"'+(changed?' stroke-dasharray="5 3"':'')+'/><text x="'+xy[0]+'" y="'+(xy[1]-2)+'" fill="'+(level===2?'white':'#213b55')+'" text-anchor="middle" font-size="12" font-weight="700">'+c+'</text><text x="'+xy[0]+'" y="'+(xy[1]+13)+'" fill="'+(level===2?'white':'#213b55')+'" text-anchor="middle" font-size="11">'+level+'/2</text><title>'+escape(fullname+': '+act)+'</title></g>';
});
var changedCountries=previous?D.countries.filter(function(c){return previous[c][v.action]!==actions[c][v.action];}):[];
var diffLine=v.year>2025?'По сравнению с '+(v.year-1)+' годом изменили этот тип решения: '+(changedCountries.length?changedCountries.map(function(c){return M.countryNames[c];}).join(', '):'ни одна страна')+'.':'Показаны решения первого года.';
markup+='</svg><p class="decision-map-caption"><strong>'+escape(diffLine)+'</strong> Нажмите на государство, чтобы увидеть все шесть решений. Пунктирный контур обозначает изменение уровня относительно предыдущего года. Расположение условное.</p>';
$('decisionMap').innerHTML=markup;
$('decisionMap').querySelectorAll('[data-decision-country]').forEach(function(node){
function choose(){var country=node.dataset.decisionCountry,button=document.querySelector('.agent-row[data-code="'+country+'"]');if(button){button.click();renderMap(view());}}
node.addEventListener('click',choose);
node.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});
});
}
function crisisImpact(c){
var v=G.shockVectors[c.type]||G.shockVectors.economic;
return G.channelNames.map(function(name,i){var n=v[i]*c.intensity*.65;return '<span>'+escape(name)+': <strong>'+(n>0?'+':'')+fmt(n,3)+'</strong></span>';}).join('');
}
function crisisContext(c){
var region=(c.affected||[]).filter(function(k){return D.countries.includes(k);});
var target=region.length?'В модели прямые адресаты: '+region.map(function(k){return M.countryNames[k];}).join(', ')+'. Дальнейшее распространение зависит от торговой сети.':'Внешнее событие: по правилам модели воздействие распространяется на все восемь стран.';
return (c.note?c.note+'. ':'')+target;
}
function renderReference(v){
var detail=$('guide-panel-'+selectedTab);
if(!detail||!detail.open)return;
var box=$('guide-'+selectedTab),html='';
var key=selectedTab+'|'+(selectedTab==='scenarios'?v.scenario:selectedTab==='strategies'?v.policy:selectedTab==='crises'?(v.scenario+'|'+v.year+'|'+crisisFilter):'fixed');
if(key===lastReferenceKey)return;lastReferenceKey=key;
if(selectedTab==='wildcards'){window.EURASIA_WILDCARDS.render(box);return;}
if(selectedTab==='scenarios'){
html='<p class="reference-intro">Каждый сценарий задает собственную последовательность трех кризисных событий. Выберите сценарий, чтобы сопоставить действия стран и результаты разных стратегий.</p><div class="guide-grid">';
D.scenarios.forEach(function(s){
var t=G.scenarioDescriptions[s.scenario_id],chosen=s.scenario_id===v.scenario;
html+='<article class="guide-card '+(chosen?'selected-guide':'')+'"><span class="guide-code">'+escape(s.scenario_id)+' · '+escape(s.group)+'</span><h3>'+escape(G.scenarioTitles[s.scenario_id]||s.name)+'</h3><p><strong>'+escape(t.short)+'</strong></p><p>'+escape(t.details)+'</p><p class="guide-list"><b>Предусмотренные события:</b> '+s.crisis_ids.map(function(id,i){return escape(item(id).name)+' — с '+(2026+4*i)+' г.';}).join('; ')+'</p><button type="button" class="small-guide-action" data-choose-scenario="'+s.scenario_id+'">'+(chosen?'Выбран':'Выбрать сценарий')+'</button></article>';
});
html+='</div>';
}else if(selectedTab==='strategies'){
html='<p class="reference-intro">Здесь сравниваются два способа работы обученной многоагентной стратегии и два варианта поведения по заранее заданным правилам. Для сравнения используются одинаковые условия.</p><div class="guide-grid">';
Object.keys(G.policyDescriptions).forEach(function(id){var t=G.policyDescriptions[id];html+='<article class="guide-card '+(v.policy===id?'selected-guide':'')+'"><span class="guide-code">'+(id.startsWith('MAPPO')?'ОБУЧЕННАЯ МОДЕЛЬ':'ПРАВИЛА ДЛЯ СРАВНЕНИЯ')+'</span><h3>'+escape(M.policyNames[id])+'</h3><p><strong>'+escape(t.short)+'</strong></p><p>'+escape(t.details)+'</p><button type="button" class="small-guide-action" data-choose-policy="'+id+'">'+(id===v.policy?'Выбрана':'Выбрать стратегию')+'</button></article>';});
html+='</div>';
}else if(selectedTab==='actions'){
html='<p class="reference-intro">Каждая страна выбирает шесть действий; у каждого три уровня. Показаны значения обученной или контрольной стратегии, а не фактические решения правительств.</p><div class="guide-grid">';
G.actionDescriptions.forEach(function(t,i){html+='<article class="guide-card"><span class="guide-code">НАПРАВЛЕНИЕ '+(i+1)+' ИЗ 6</span><h3>'+escape(t.name)+'</h3><p>'+escape(t.detail)+'</p><ol class="action-levels">'+t.levels.map(function(z,level){return '<li><b>Уровень '+level+':</b> '+escape(z)+'</li>';}).join('')+'</ol><button type="button" class="small-guide-action" data-action-index="'+i+'">Посмотреть на карте стран</button></article>';});
html+='</div>';
}else{
var s=scenario(v.scenario),all=Object.values(G.crisisCatalog),active=due(v.scenario,v.year),selected=crisisFilter==='all'?all:crisisFilter==='active'?active:all.filter(function(c){return s.crisis_ids.includes(c.id);});
html='<p class="reference-intro">Каталог содержит 100 гипотетических событий. Интенсивность — условный коэффициент, а не вероятность. Воздействия рассчитаны по четырем каналам; численные коэффициенты не равны процентам изменения ВВП.</p><label class="guide-filter">Показать <select id="crisisFilter"><option value="scenario">События выбранного сценария</option><option value="active">Кризисы выбранного года</option><option value="all">Все 100 событий</option></select></label><div class="guide-grid">';
selected.forEach(function(c){
var act=active.some(function(e){return e.id===c.id;}),starts=launches(v.scenario,c.id);
html+='<article class="guide-card '+(act?'selected-guide':'')+'"><span class="guide-code">СОБЫТИЕ '+c.id+' · '+escape(G.crisisTypes[c.type]||c.type)+'</span><h3>'+escape(c.name)+'</h3><p>'+escape(crisisContext(c))+'</p><div class="crisis-params"><span>Интенсивность: <strong>'+fmt(c.intensity)+'</strong></span><span>Длительность: <strong>'+c.duration+' '+(c.duration===1?'год':'года')+'</strong></span><span>Появление в сценарии: <strong>'+(starts.length?starts.join(', '):'не входит')+'</strong></span></div><div class="impact-grid">'+crisisImpact(c)+'</div><p class="guide-caveat">Канальные коэффициенты до распространения по торговой сети, не фактические экономические потери.</p></article>';
});
html+=selected.length?'':'<p class="reference-intro">В этом году кризисных событий нет.</p>';html+='</div>';
}
box.innerHTML=html;
if($('crisisFilter')){$('crisisFilter').value=crisisFilter;$('crisisFilter').addEventListener('change',function(e){crisisFilter=e.target.value;renderReference(view());});}
box.querySelectorAll('[data-choose-scenario]').forEach(function(n){n.addEventListener('click',function(){var x=$('scenario');x.value=n.dataset.chooseScenario;x.dispatchEvent(new Event('change',{bubbles:true}));window.scrollTo({top:0,behavior:'smooth'});});});
box.querySelectorAll('[data-choose-policy]').forEach(function(n){n.addEventListener('click',function(){var x=$('policy');x.value=n.dataset.choosePolicy;x.dispatchEvent(new Event('change',{bubbles:true}));window.scrollTo({top:0,behavior:'smooth'});});});
box.querySelectorAll('[data-action-index]').forEach(function(n){n.addEventListener('click',function(){var x=$('actionType');x.value=n.dataset.actionIndex;renderMap(view());$('decisionMap').scrollIntoView({behavior:'smooth',block:'center'});});});
}
function refresh(){var v=view();renderSummaries(v);renderCrisis(v);renderMap(v);renderReference(v);}
$('actionType').addEventListener('change',refresh);
['scenario','policy','seed','year'].forEach(function(id){$(id).addEventListener('change',refresh);});
var yearObserver=new MutationObserver(function(){refresh();});yearObserver.observe($('selectedYear'),{subtree:true,childList:true,characterData:true});
var countryObserver=new MutationObserver(function(){renderMap(view());});countryObserver.observe($('actions'),{subtree:true,childList:true,attributes:false});
document.querySelectorAll('[data-guide-detail]').forEach(function(n){n.addEventListener('toggle',function(){
 if(n.open){selectedTab=n.dataset.guideDetail;lastReferenceKey='';document.querySelectorAll('[data-guide-detail]').forEach(function(other){if(other!==n)other.open=false;});renderReference(view());}
});});
document.querySelectorAll('[data-open-guide]').forEach(function(n){n.addEventListener('click',function(e){e.preventDefault();showTab(n.dataset.openGuide);$('reference').scrollIntoView({behavior:'smooth',block:'start'});});});
window.addEventListener('eurasia:texts-updated',function(){lastReferenceKey='';refresh();});
refresh();
})();