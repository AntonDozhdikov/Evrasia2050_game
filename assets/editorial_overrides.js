/* Применение сохраненной редакции только к отображаемым текстам. Архивные числа не изменяются. */
(function(){
'use strict';
const G=window.EURASIA_GUIDE,D=window.EURASIA_DATA,M=window.EurasiaModel;
if(!G||!D||!M)return;
const selectors={intro:'.intro > div > p',start:'.hero-caption',method:'.method-heading > p',limits:'.method-limit > p',
 actionHelp:'.actions-panel .panel-lead',tradeHelp:'.network-panel .panel-lead',scenarioHelp:'#reference .reference-heading > p'};
const keys={scenario:['title','short','details'],crisis:['name','note'],policy:['short','details'],action:['name','detail','level0','level1','level2'],page:['text']};
let state;try{state=JSON.parse(localStorage.getItem('evrasia2050:editorial:v1')||'null');}catch(_){return;}
if(!state||state.version!==1||JSON.stringify(state).length>700000)return;
for(const [kind,values] of Object.entries(state)){
 if(!keys[kind]||!values||typeof values!=='object'||Array.isArray(values))continue;
 for(const [id,props] of Object.entries(values)){
  if(!props||typeof props!=='object'||Array.isArray(props))continue;
  for(const [field,text] of Object.entries(props)){
   if(!keys[kind].includes(field)||typeof text!=='string'||text.length>6000)continue;
   if(kind==='scenario'){
    if(!D.scenarios.some(s=>s.scenario_id===id))continue;
    if(field==='title')G.scenarioTitles[id]=text;
    else if(G.scenarioDescriptions[id])G.scenarioDescriptions[id][field]=text;
   }else if(kind==='crisis'){
    if(G.crisisCatalog[id])G.crisisCatalog[id][field]=text;
   }else if(kind==='policy'){
    if(G.policyDescriptions[id])G.policyDescriptions[id][field]=text;
   }else if(kind==='action'){
    const i=Number(id);if(!Number.isInteger(i)||i<0||i>=G.actionDescriptions.length)continue;
    if(field==='name'||field==='detail')G.actionDescriptions[i][field]=text;
    else if(/^level[012]$/.test(field))G.actionDescriptions[i].levels[Number(field.slice(-1))]=text;
   }else if(kind==='page'){
    const selector=selectors[id];const node=selector?document.querySelector(selector):null;
    if(node&&field==='text')node.textContent=text;
   }
  }
 }
}
})();