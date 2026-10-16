#!/usr/bin/env node
'use strict';
/* Проверка полноты сценариев и качества русских описаний. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const original=JSON.parse(read('research/results/scenarios_20.json'));
const catalog=JSON.parse(read('research/results/crises_future_100.json'));
assert.equal(original.length,20);assert.equal(catalog.length,100);
const context={window:{},document:{getElementById:()=>null},Date,Math,Blob:class{},URL:{},setTimeout:()=>{}};
vm.createContext(context);
for(const file of ['assets/data.js','assets/guide.js','assets/editorial_ru.js','assets/wildcards.js']){
 vm.runInContext(read(file),context,{filename:file,timeout:12000});
}
const G=context.window.EURASIA_GUIDE,W=context.window.EURASIA_WILDCARDS;
assert.ok(G&&W);
assert.equal(Object.keys(G.crisisCatalog).length,100);
assert.equal(Object.keys(G.scenarioDescriptions).length,20);
for(const [id,c] of Object.entries(G.scenarioDescriptions)){
 const length=c.short.trim().split(/\s+/).length;
 assert.ok(length>=20&&length<=26,'Краткое описание '+id+': '+length+' слов');
}
for(const c of Object.values(G.crisisCatalog)){
 assert.ok(c.name.length>8&&c.note.length>20,'Описание события '+c.id);
 assert.ok(!/\b[A-Za-z][A-Za-z_-]{2,}\b/.test(c.name+' '+c.note),'Английская служебная запись '+c.id);
 assert.ok(!/(?:не.{0,50},\s*но\b|не только.{0,40}но и\b)/i.test(c.name+' '+c.note),'Шаблонный оборот '+c.id);
}
const originalIds=original.flatMap(s=>s.crisis_ids.map(Number));
assert.equal(originalIds.length,60);assert.equal(new Set(originalIds).size,60);
const initial=W.getSets();
assert.equal(initial.length,10);
const wildIds=initial.flatMap(x=>x.crisis_ids);
assert.ok(initial.every(s=>s.crisis_ids.length===4));
assert.equal(wildIds.length,40);assert.equal(new Set(wildIds).size,40);
assert.equal(new Set([...originalIds,...wildIds]).size,100);
const originalSet=new Set(originalIds);
assert.ok(wildIds.every(id=>!originalSet.has(id)));
W.generate(731205);const first=JSON.stringify(W.getSets());
W.generate(731205);assert.equal(JSON.stringify(W.getSets()),first);
W.generate(731206);assert.notEqual(JSON.stringify(W.getSets()),first);
const html=read('play_the_game.html');
for(const filename of ['assets/data.js','assets/guide.js','assets/editorial_ru.js','assets/wildcards.js','assets/app.js','assets/guide_ui.js'])
 assert.ok(html.includes('src="'+filename+'"'),'Не подключен '+filename);
assert.ok(html.includes('data-guide-detail="wildcards"'));
assert.ok(html.includes('src="assets/engine_v47.js"'));
assert.ok(html.includes('src="assets/party_results.js"'));
assert.ok(!html.includes('id="text-editor"'));
assert.ok(html.includes('id="partyCalculate"'));

console.log('Проверено: 20 исходных сценариев, 10 «Диких карт», 100 событий без повторов, русские описания и воспроизводимая жеребьевка.');
