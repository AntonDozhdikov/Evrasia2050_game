#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const game=read('play_the_game.html'),landing=read('index.html'),editor=read('editor.html'),guide=read('assets/guide_ui.js');
assert.ok(landing.includes('window.location.replace(destination.href)'), 'Старая стартовая страница не перенаправляет');
assert.ok(landing.includes("new URL('./play_the_game'"), 'Старый адрес не ведет на /play_the_game');
assert.ok(game.includes('rel="canonical" href="https://antondozhdikov.github.io/Evrasia2050_game/play_the_game"'), 'Неверный основной адрес игры');
assert.ok(game.includes('href="./play_the_game"'), 'Логотип не ведет на новый адрес');
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
assert.ok(read('assets/editorial_overrides.js').includes("start:'.hero-caption'"),'Редактор не связан с новой шапкой игры');
assert.ok(editor.includes('Одна партия — 26 лет решений.'),'В редакторе остался прежний текст первого экрана');
for(const p of ['assets/app.js','assets/model.js','assets/guide_ui.js','assets/party_core.js','assets/party_ui.js','assets/editorial_ru.js','assets/editorial_overrides.js','assets/text_editor.js'])
 assert.ok(read(p).length>100,'Пустой или отсутствующий файл '+p);
assert.ok(!read('assets/app.js').includes('Линии показывают только известные данные, без заполнения пропусков.'));
console.log('Страница игры: обзор → партия → результаты → закрытый справочник. Редактор — отдельная страница.');
