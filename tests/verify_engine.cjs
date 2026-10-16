#!/usr/bin/env node
'use strict';
/* Паритет расчетов при подавленном шуме проверяется по эталонному Python V4.7. */
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const env={window:{},module:{exports:{}},exports:{}};
vm.runInNewContext(read('assets/engine_bootstrap.js'),env,{filename:'engine_bootstrap.js'});
vm.runInNewContext(read('assets/engine_v47.js'),env,{filename:'engine_v47.js'});
const B=env.window.EURASIA_ENGINE_BOOTSTRAP,E=env.module.exports;
assert.ok(B&&E&&E.run);
const scenarios=JSON.parse(read('research/results/scenarios_20.json'));
const cat=Object.fromEntries(JSON.parse(read('research/results/crises_future_100.json')).map(e=>[String(e.id),e]));
const db={runs:{}};
const source=JSON.parse(read('assets/data.js').split('window.EURASIA_DATA=',2)[1].trim().replace(/;\s*$/,''));
const actualDb=source;
assert.equal(Object.keys(source.runs).length,240);
const tests=[
 {sc:'S01',strategy:'NEUTRAL',first:[6.633741556,213547937456.646,5.781826858,0],last:[2.655333869,198304349255.303,5.781826858,0]},
 {sc:'S01',strategy:'BARGAIN',first:[6.643319373,222428076742.199,4.266154627,7],last:[2.429879803,408870871014.748,0.2348521765,0]},
 {sc:'S02',strategy:'NEUTRAL',first:[6.633741556,213547937456.646,5.781826858,0],last:[2.319907749,199620800737.74,5.781826858,0]},
 {sc:'S02',strategy:'BARGAIN',first:[6.643319373,222428076742.199,4.266154627,7],last:[2.06648830,411605322327.041,0.2348521765,0]}
];
for(const tc of tests){
 const r=E.run({bootstrap:B,cat,scenario:scenarios.find(s=>s.scenario_id===tc.sc),seed:163,policy:tc.strategy,db:actualDb,zeroNoise:true});
 assert.equal(r.history.length,26);
 for(const [row,expect] of [[r.history[0],tc.first],[r.history[25],tc.last]]){
  const values=[row.mean_growth_pct,row.trade_usd_total,row.capital_budget_total,row.new_projects];
  values.forEach((value,i)=>assert.ok(Math.abs(value-expect[i])<([1e-5,3,1e-6,0][i]+1e-12),tc.sc+' '+tc.strategy+' '+i+': '+value+'/'+expect[i]));
 }
}
const first=scenarios[0],baseline=E.run({bootstrap:B,cat,scenario:first,seed:163,policy:'BARGAIN',db:actualDb});
const alternative=E.run({bootstrap:B,cat,scenario:first,seed:163,policy:'BARGAIN',db:actualDb,overrides:{2025:{RUS:[0,0,0,2,0,0]}}});
assert.notEqual(E.summary(baseline).net,E.summary(alternative).net);
for(const scenario of scenarios)for(const seed of source.manifest.seeds)for(const strategy of source.manifest.policies){
 const result=E.run({bootstrap:B,cat,scenario,seed,policy:strategy,db:actualDb});
 assert.equal(result.history.length,26);
 assert.ok(Object.values(E.summary(result)).every(Number.isFinite),scenario.scenario_id+':'+strategy+':'+seed);
}
console.log('Проверка: 240 сочетаний основных сценариев, стратегия игрока, макроэкономика и паритет Python для 4 контрольных траекторий.');
