#!/usr/bin/env node
'use strict';
/* Верификация смешанного сравнения: архивные записи + реальные расчёты адаптивной MAPPO. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const D=JSON.parse(read('assets/data.js').split('window.EURASIA_DATA=',2)[1].trim().replace(/;\s*$/,''));
const G={crisisCatalog:Object.fromEntries(JSON.parse(read('research/results/crises_future_100.json')).map(x=>[String(x.id),x]))};
const sandbox={window:{}};vm.runInNewContext(read('assets/engine_bootstrap.js'),sandbox);
global.window={
 EURASIA_ENGINE_BOOTSTRAP:sandbox.window.EURASIA_ENGINE_BOOTSTRAP,
 EURASIA_GUIDE:G,
 EurasiaEngine:require('../assets/engine_v47.js'),
 EurasiaAdaptive:require('../assets/adaptive_v47.js')
};
const M=require('../assets/model.js');
assert.equal(M.archivePolicies.length,4);
assert.equal(M.adaptivePolicies.length,2);
assert.equal(Object.values(M.policyNames).length,6);
const scenarios=['S01','S05','S10','S17','S20'],seeds=[163,272,381];
let tested=0;
for(const sc of scenarios)for(const seed of seeds)for(const policy of M.adaptivePolicies){
 const run=M.getRun(D,sc,policy,seed);
 assert.equal(run.origin,'adaptive_js_v47');
 assert.equal(run.years.length,26);
 assert.equal(run.actions.length,26);
 assert.strictEqual(M.getRun(D,sc,policy,seed),run,'Repeated rendering should cache identical 26-year series');
 for(let y=2025;y<=2050;y++){
  const j=y-2025,view=M.at(D,sc,policy,seed,y),rows=run.years[j];
  assert.equal(rows.length,D.fields.length);
  assert.ok(rows.every(Number.isFinite),'Non-finite archive-adapter output '+sc+' '+policy+' '+y);
  assert.equal(view.values.projects,view.values.new_projects,'Project field alias must match original Python definition');
  assert.equal(Object.keys(view.actions).length,8);
  for(const a of Object.values(view.actions))assert.ok(a.length===6&&a.every(v=>[0,1,2].includes(v)));
 }
 for(const metric of ['mean_growth_pct','new_projects','trade_usd_total','mean_reward']){
  const points=M.series(D,sc,policy,seed,metric);
  assert.equal(points.length,26);
  assert.ok(points.every(row=>Number.isFinite(row.value)));
 }
 tested++;
}
const original=M.getRun(D,'S01','MAPPO_GREEDY',163);
assert.equal(original,D.runs['S01|MAPPO_GREEDY|163'],'Archive trajectory must remain bitwise unchanged');
assert.ok(M.policyDetails.ADAPTIVE_MAPPO_GREEDY.includes('пересчитывает'));
console.log('PASS ADAPTIVE ARCHIVE: '+tested+' 26-year live actor trajectories, all 15 fields, project alias, six strategies and immutable source archive.');
