#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const html=read('play_the_game.html'),editor=read('editor.html'),css=read('assets/ux_v2.css');
const party=read('assets/party_ui.js'),results=read('assets/party_results.js');
const sections=['class="intro"','id="party-planner"','id="results"','id="partyResults"','id="archive-results"','id="methods"','id="reference"'];
const positions=sections.map(x=>html.indexOf(x));
assert.ok(positions.every(x=>x>=0),'Пропущен основной раздел');
assert.ok(positions.every((x,i)=>i===0||x>positions[i-1]),'Неверный порядок игровых разделов');
const ids=['uxQuickStart','partyCountryTabs','partyActions','partySave','partyNext','partyCalculate','partyExport','partyImport','partyNew','partyResultKpis','partyStrengths','partySeriesChoices','partyResultChart','partyAllMetrics','partyCountryMetrics','archive-results','countries','decisionMap','partyResultRows','partyCountryRows','partySlots','partySlotSave','partySlotLoad','partySlotDelete','partyPreviewYear','partyYearPreviewContent','partyYearCrisis','partyYearCountries','partyResultProvenance','partyCountryDetails','partyCountryDetailChart','partyCountryDetailRows'];
for(const id of ids)assert.ok(html.includes('id="'+id+'"'),'Отсутствует '+id);
for(const p of ['assets/styles.css','assets/ux_v2.css','assets/party_ui.js','assets/party_results.js','assets/ux_v2.js'])assert.ok(html.includes('"'+p+'"'),'Не подключен '+p);
assert.ok(!html.includes('editor.html')&&!html.includes('id="text-editor"'),'Редактор появился на игровой странице');
assert.ok(editor.includes('id="text-editor"')&&editor.includes('assets/text_editor.js'),'Утерян отдельный редактор');
assert.ok(!html.includes('id="archive-results" open'),'Исследовательский архив открыт по умолчанию');
assert.ok(!html.includes('id="partyAllMetrics" open'),'Подробная таблица открыта по умолчанию');
assert.ok(!html.includes('id="partyCountryMetrics" open'),'Таблица стран открыта по умолчанию');
assert.ok(party.includes('data-party-tab')&&party.includes('data-party-card'),'Отсутствуют вкладки стран');
assert.ok(party.includes('party.controlled')&&party.includes('Core.plan'),'Нарушено сохранение решений');
assert.ok(results.includes("const METRICS=[")&&results.includes("function calculate()"),'Утрачен вычислительный итог');
assert.ok(results.includes('partySeriesChoices')&&results.includes('partyStrengths'),'Нет сравнительного графика');
assert.ok(results.includes('partyResultRows')&&results.includes('partyCountryRows'),'Нет полных таблиц');
assert.ok(results.includes('renderCountryDetail')&&results.includes('previewYear'),'Нет подробной экономики стран и обратной связи по годам');
assert.ok(party.includes('saveNamedSlot')&&party.includes('loadNamedSlot')&&party.includes('deleteNamedSlot'),'Отсутствуют именованные сохранения');
assert.ok(results.includes('wildcard_seed:computation.party.wildcardSeed'),'Экспорт теряет жеребьёвку кризисов');
assert.ok(!read('assets/wildcards.js').includes('следующий выпуск игрового движка'),'Устаревшие подсказки «Диких карт»');
assert.ok(css.includes('@media(max-width:490px)')&&css.includes('.intro')&&css.includes('.player-chart'),'Нет адаптивной верстки');
for(const file of ['assets/party_ui.js','assets/party_results.js','assets/ux_v2.js','assets/engine_v47.js']){
 new Function(read(file));
}
const tags=['section','main','details','div'];
const voidTags=new Set(['input','meta','link','img','hr','br','source']);
const stack=[],mismatch=[];
for(const m of html.matchAll(/<(\/?)([A-Za-z][\w-]*)\b[^>]*>/g)){
 const close=Boolean(m[1]),tag=m[2].toLowerCase();
 if(voidTags.has(tag)||m[0].endsWith('/>'))continue;
 if(close){if(stack.at(-1)===tag)stack.pop();else mismatch.push('Закрывающий '+tag+', ожидался '+stack.at(-1));}
 else stack.push(tag);
}
assert.equal(stack.length,0,'Незакрытые теги: '+stack.slice(-6).join(', '));
assert.deepEqual(mismatch,[],'Неверная вложенность HTML');
console.log('UX-приемка: старт, выбор государств, графики, подробные таблицы, отдельный редактор, адаптивный интерфейс. Все разделы сохранены.');
