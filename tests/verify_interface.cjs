#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const game=read('index.html'),editor=read('editor.html'),guide=read('assets/guide_ui.js');
const parts=['class="game-facts"','id="party-planner"','id="results"','id="chart"','id="methods"','id="reference"'];
const positions=parts.map(x=>game.indexOf(x));
assert.ok(positions.every(x=>x>=0),'На главной отсутствуют разделы');
assert.ok(positions.every((x,i)=>i===0||x>positions[i-1]),'Нарушен порядок блоков');
assert.ok(!game.includes('id="text-editor"')&&!game.includes('text_editor.js')&&!game.includes('href="editor.html"'),'Редактор обнаружен на публичной странице');
assert.ok(game.includes('id="reference"')&&game.includes('class="reference-accordions"'));
for(const key of ['scenarios','crises','strategies','actions','wildcards']){
 assert.ok(game.includes('id="guide-panel-'+key+'"'));
 assert.ok(game.includes('data-guide-detail="'+key+'"'));
 assert.ok(game.includes('id="guide-'+key+'"'));
 assert.ok(!game.includes('id="guide-panel-'+key+'" open'),'Справочник открыт по умолчанию');
}
assert.ok(guide.includes("if(!detail||!detail.open)return"));
assert.ok(editor.includes('id="text-editor"')&&editor.includes('assets/text_editor.js'));
assert.ok(editor.includes('name="robots" content="noindex,nofollow"'));
assert.ok(game.includes('assets/editorial_overrides.js'));
for(const p of ['assets/app.js','assets/model.js','assets/guide_ui.js','assets/party_core.js','assets/party_ui.js','assets/editorial_ru.js','assets/editorial_overrides.js','assets/text_editor.js'])
 assert.ok(read(p).length>100,'Пустой или отсутствующий файл '+p);
assert.ok(!read('assets/app.js').includes('Линии показывают только известные данные, без заполнения пропусков.'));
console.log('Страница игры: обзор → партия → результаты → закрытый справочник. Редактор — отдельная страница.');
