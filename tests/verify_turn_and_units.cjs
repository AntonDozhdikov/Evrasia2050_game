#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const U=require('../assets/metric_units.js'),E=require('../assets/engine_v47.js'),A=require('../assets/adaptive_v47.js');
const data=JSON.parse(fs.readFileSync('assets/data.js','utf8').split('window.EURASIA_DATA=',2)[1].trim().replace(/;\s*$/,''));
const scenarios=JSON.parse(fs.readFileSync('research/results/scenarios_20.json','utf8'));
const cat=Object.fromEntries(JSON.parse(fs.readFileSync('research/results/crises_future_100.json','utf8')).map(e=>[String(e.id),e]));
const bootstrap={};
const vm=require('node:vm');const sandbox={window:{}};vm.runInNewContext(fs.readFileSync('assets/engine_bootstrap.js','utf8'),sandbox);
Object.assign(bootstrap,sandbox.window.EURASIA_ENGINE_BOOTSTRAP);
assert.equal(U.fromSummary('trade',174268226220.07),174.26822622007);
assert.ok(Math.abs(U.delta('trade',0,174268226220.07)+174.26822622007)<1e-9);
assert.equal(U.units.trade,'млрд долл.');
assert.equal(U.fromSummary('growth',5.6),5.6);
assert.equal(U.fromSummary('net',1.1),1.1);
assert.ok(U.signed(-174.26822622007,2).includes('174,27'),'The large fake billion-dollar delta must disappear');
for(const scenario of scenarios){
 const s=E.run({bootstrap,cat,scenario,seed:163,db:data,policy:'ADAPTIVE_MAPPO_GREEDY',adaptive:A,untilYear:2027});
 assert.equal(s.history.length,3);
 assert.equal(s.history.at(-1).year,2027);
 for(const row of s.history){
  assert.ok(Array.isArray(row.active_crises));
  for(const event of row.active_crises)assert.ok(event.started<=row.year && event.expires>=row.year);
  const planned=E.announcedCrises(scenario,cat,row.year);
  assert.equal(row.active_crises.length,planned.length);
  assert.deepEqual(row.active_crises.map(e=>e.id),planned.map(e=>e.id));
 }
}
const first=scenarios[0];
const early=E.run({bootstrap,cat,scenario:first,seed:163,db:data,policy:'ADAPTIVE_MAPPO_GREEDY',adaptive:A,untilYear:2026});
const full=E.run({bootstrap,cat,scenario:first,seed:163,db:data,policy:'ADAPTIVE_MAPPO_GREEDY',adaptive:A});
assert.equal(early.history.length,2);
assert.deepEqual(early.history,full.history.slice(0,2),'No future look-ahead in previous-year snapshot');
const override={2025:{RUS:[2,2,2,2,2,2]}};
const changed=E.run({bootstrap,cat,scenario:first,seed:163,db:data,policy:'ADAPTIVE_MAPPO_GREEDY',adaptive:A,overrides:override,untilYear:2026});
assert.notDeepEqual(changed.history[0].actions[0],early.history[0].actions[0]);
assert.ok(changed.history[1].country_stats.every(x=>Number.isFinite(x.trade_usd)));
console.log('PASS TURN AND UNITS: numeric units, 20 crisis plans, history cutoff, country values and no altered V4.7 economics.');
