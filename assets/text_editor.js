/* Редактор игровых текстов. Вносит только текстовые правки, не изменяет расчеты V4.7. */
(function(){
'use strict';
const G=window.EURASIA_GUIDE,D=window.EURASIA_DATA,M=window.EurasiaModel;
if(!G||!D||!M)return;
const $=id=>document.getElementById(id),KEY='evrasia2050:editorial:v1';
const PAGE={
 intro:{label:'Вступление: смысл игры',selector:'.intro > div > p'},
 start:{label:'С чего начать',selector:'.intro-note > span'},
 method:{label:'Объяснение игры',selector:'.method-heading > p'},
 limits:{label:'О результатах',selector:'.method-limit > p'},
 actionHelp:{label:'Как читать решения',selector:'.actions-panel .panel-lead'},
 tradeHelp:{label:'Как читать торговлю',selector:'.network-panel .panel-lead'},
 scenarioHelp:{label:'Пояснение к справочнику',selector:'#reference .reference-heading > p'}
};
const copy=x=>JSON.parse(JSON.stringify(x));
const base={
 titles:copy(G.scenarioTitles),scenarios:copy(G.scenarioDescriptions),
 crises:Object.fromEntries(Object.entries(G.crisisCatalog).map(([id,c])=>[id,{name:c.name,note:c.note}])),
 policies:copy(G.policyDescriptions),actions:copy(G.actionDescriptions),
 page:Object.fromEntries(Object.entries(PAGE).map(([id,d])=>[id,document.querySelector(d.selector)?.textContent||'']))
};
let changes={version:1,scenario:{},crisis:{},policy:{},action:{},page:{}};
const rules={scenario:['title','short','details'],crisis:['name','note'],policy:['short','details'],action:['name','detail','level0','level1','level2'],page:['text']};
const textMax=6000;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function entries(kind){
 if(kind==='scenario')return D.scenarios.map(s=>[s.scenario_id,(G.scenarioTitles[s.scenario_id]||s.name)]);
 if(kind==='crisis')return Object.entries(G.crisisCatalog).sort((a,b)=>Number(a[0])-Number(b[0])).map(([id,c])=>[id,id+' · '+c.name]);
 if(kind==='policy')return Object.keys(G.policyDescriptions).map(id=>[id,M.policyNames[id]]);
 if(kind==='action')return G.actionDescriptions.map((a,i)=>[String(i),a.name]);
 return Object.entries(PAGE).map(([id,d])=>[id,d.label]);
}
function validate(data){
 if(!data||data.version!==1||typeof data!=='object')throw Error('Неизвестный формат исправлений');
 let size=JSON.stringify(data).length;if(size>700000)throw Error('Файл исправлений слишком велик');
 for(const kind of Object.keys(rules)){
  const part=data[kind];if(!part||typeof part!=='object'||Array.isArray(part))throw Error('Неверный раздел текстов');
  const ids=new Set(entries(kind).map(([id])=>id));
  for(const [id,fields] of Object.entries(part)){
   if(!ids.has(id)||!fields||typeof fields!=='object'||Array.isArray(fields))throw Error('Неизвестное описание '+kind+' '+id);
   for(const [field,value] of Object.entries(fields)){
    if(!rules[kind].includes(field)||typeof value!=='string'||value.length>textMax)throw Error('Неверное поле '+kind+' '+id+' '+field);
   }
  }
 }
 return true;
}
function baseFields(kind,id){
 if(kind==='scenario')return {title:base.titles[id]||D.scenarios.find(s=>s.scenario_id===id)?.name||'',...base.scenarios[id]};
 if(kind==='crisis')return {...base.crises[id]};
 if(kind==='policy')return {...base.policies[id]};
 if(kind==='action'){
  const a=base.actions[Number(id)];return {name:a.name,detail:a.detail,level0:a.levels[0],level1:a.levels[1],level2:a.levels[2]};
 }
 return {text:base.page[id]};
}
function apply(){
 Object.assign(G.scenarioTitles,copy(base.titles));
 Object.entries(base.scenarios).forEach(([id,content])=>Object.assign(G.scenarioDescriptions[id],content));
 Object.entries(base.crises).forEach(([id,text])=>{G.crisisCatalog[id].name=text.name;G.crisisCatalog[id].note=text.note;});
 Object.entries(base.policies).forEach(([id,text])=>Object.assign(G.policyDescriptions[id],text));
 base.actions.forEach((item,i)=>Object.assign(G.actionDescriptions[i],copy(item)));
 Object.entries(base.page).forEach(([id,text])=>{const node=document.querySelector(PAGE[id].selector);if(node)node.textContent=text;});
 for(const [kind,items] of Object.entries(changes)){
  if(kind==='version')continue;
  for(const [id,values] of Object.entries(items)){
   if(kind==='scenario'){
    const {title,...rest}=values;
    if(title!==undefined)G.scenarioTitles[id]=title;
    Object.assign(G.scenarioDescriptions[id],rest);
   }else if(kind==='crisis')Object.assign(G.crisisCatalog[id],values);
   else if(kind==='policy')Object.assign(G.policyDescriptions[id],values);
   else if(kind==='action'){
    const a=G.actionDescriptions[Number(id)];
    if(values.name!==undefined)a.name=values.name;
    if(values.detail!==undefined)a.detail=values.detail;
    for(let n=0;n<3;n++)if(values['level'+n]!==undefined)a.levels[n]=values['level'+n];
   }else if(kind==='page'){
    const node=document.querySelector(PAGE[id].selector);if(node&&values.text!==undefined)node.textContent=values.text;
   }
  }
 }
 // Rebuild only visible option labels. No model values or country decisions change.
 for(const option of document.querySelectorAll('#scenario option')){
  const info=D.scenarios.find(s=>s.scenario_id===option.value);
  if(info)option.textContent=info.scenario_id+' · '+(G.scenarioTitles[info.scenario_id]||info.name);
 }
 for(const option of document.querySelectorAll('#actionType option')){
  const k=Number(option.value);if(G.actionDescriptions[k])option.textContent=G.actionDescriptions[k].name;
 }
 window.dispatchEvent(new CustomEvent('eurasia:texts-updated'));
}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(changes));return true;}catch(e){return false;}}
function showMessage(text,success=true){const node=$('textEditorMessage');node.textContent=text;node.classList.toggle('party-error',!success);}
function kindSelected(){return $('textKind').value;}
function itemSelected(){return $('textItem').value;}
function makeItemOptions(){
 const kind=kindSelected(),list=entries(kind);
 const before=$('textItem').value;
 $('textItem').innerHTML=list.map(([id,title])=>'<option value="'+escape(id)+'">'+escape(title)+'</option>').join('');
 if(list.some(([id])=>id===before))$('textItem').value=before;
 renderFields();
}
const titles={title:'Название сценария',short:'Краткое описание',details:'Подробное описание',name:'Название',note:'Описание и причины',detail:'Пояснение',level0:'Уровень 0',level1:'Уровень 1',level2:'Уровень 2',text:'Текст'};
function renderFields(){
 const kind=kindSelected(),id=itemSelected();
 if(!id)return;
 const fields={...baseFields(kind,id),...(changes[kind]?.[id]||{})};
 const html=rules[kind].map(key=>'<label class="text-edit-field"><span>'+escape(titles[key])+'</span><textarea data-edit-key="'+key+'" rows="'+(key==='details'||key==='note'||key==='text'?5:2)+'" maxlength="'+textMax+'"></textarea></label>').join('');
 $('textFields').innerHTML=html;
 $('textFields').querySelectorAll('textarea').forEach(field=>field.value=fields[field.dataset.editKey]||'');
 $('textEditorCurrent').textContent=Object.keys(changes[kind]?.[id]||{}).length?'Есть локальные изменения':'Исходная редакция';
}
function save(){
 const kind=kindSelected(),id=itemSelected(),values={};
 for(const field of $('textFields').querySelectorAll('textarea')){
  const v=field.value.trim();
  if(!v){showMessage('Заполните все поля редактируемого описания.',false);return;}
  values[field.dataset.editKey]=v;
 }
 changes[kind][id]=values;const ok=persist();apply();renderFields();
 showMessage(ok?'Изменения сохранены в этом браузере.':'Правка применена. Браузер не разрешил локальное сохранение: скачайте файл изменений.',ok);
}
function resetEntry(){
 const kind=kindSelected(),id=itemSelected();
 delete changes[kind][id];persist();apply();renderFields();showMessage('Восстановлена исходная редакция выбранного текста.');
}
function resetAll(){
 if(!confirm('Восстановить исходную редакцию всех текстов?'))return;
 changes={version:1,scenario:{},crisis:{},policy:{},action:{},page:{}};
 persist();apply();makeItemOptions();showMessage('Восстановлена исходная редакция всех текстов.');
}
function download(){
 const payload=JSON.stringify(changes,null,2);
 const url=URL.createObjectURL(new Blob([payload],{type:'application/json;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download='evrazia2050_teksty.json';document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);showMessage('Файл изменений сохранен.');
}
async function importFile(file){
 if(!file)return;
 try{
  if(file.size>800000)throw Error('Файл слишком велик');
  const obj=JSON.parse(await file.text());
  validate(obj);changes=copy(obj);persist();apply();makeItemOptions();
  showMessage('Редакция из файла применена.');
 }catch(e){showMessage('Не удалось применить изменения: '+e.message,false);}
 $('textImportFile').value='';
}
$('textKind').addEventListener('change',makeItemOptions);
$('textItem').addEventListener('change',renderFields);
$('textApply').addEventListener('click',save);
$('textDownload').addEventListener('click',download);
$('textLoad').addEventListener('click',()=>$('textImportFile').click());
$('textImportFile').addEventListener('change',e=>importFile(e.target.files[0]));
$('textReset').addEventListener('click',resetEntry);
$('textResetAll').addEventListener('click',resetAll);
try{
 const raw=localStorage.getItem(KEY);if(raw){const saved=JSON.parse(raw);validate(saved);changes=copy(saved);}
}catch(e){changes={version:1,scenario:{},crisis:{},policy:{},action:{},page:{}};showMessage('Сохраненные правки повреждены: загружена исходная редакция.',false);}
apply();makeItemOptions();
})();