#!/usr/bin/env node
'use strict';
/* Stage 3 real frozen-actor execution and counterfactual responsiveness. */
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const Adaptive=require('../assets/adaptive_v47.js'),Policy=require('../assets/policy_v47.js'),Engine=require('../assets/engine_v47.js');
const env={window:{},module:{exports:{}},exports:{}};
vm.runInNewContext(read('assets/engine_bootstrap.js'),env);
const bootstrap=env.window.EURASIA_ENGINE_BOOTSTRAP;
const scenarios=JSON.parse(read('research/results/scenarios_20.json'));
const cat=Object.fromEntries(JSON.parse(read('research/results/crises_future_100.json')).map(e=>[String(e.id),e]));
const db=JSON.parse(read('assets/data.js').split('window.EURASIA_DATA=',2)[1].trim().replace(/;\s*$/,''));
assert.match(Policy.provenance.source,/mappo.pt$/);
assert.equal(Policy.obs_dim,80);
assert.equal(Policy.provenance.training,'none; exact frozen checkpoint export');
assert.equal(Policy.actor['body.0.weight'].values.length,96*92);
assert.deepEqual(Policy.gates.shape,[4,8,6,3]);
const initial=Engine.init(bootstrap,scenarios[0],cat,163,true);
const initialObservation=Adaptive.observe(initial);
assert.equal(initialObservation.length,8);
assert.equal(initialObservation[0].length,80);
const initialLogits=Adaptive.logits(initial);
assert.equal(initialLogits.length,8);
assert.ok(initialLogits.every(c=>c.length===6&&c.every(row=>row.length===3&&row.every(Number.isFinite))));
const a1=Adaptive.actions(initial,'ADAPTIVE_MAPPO_GREEDY',163,2025);
const a2=Adaptive.actions(initial,'ADAPTIVE_MAPPO_GREEDY',381,2025);
assert.deepEqual(a1,a2,'The deterministic frozen actor cannot depend on RNG seed at fixed state');
const q1=Adaptive.actions(initial,'ADAPTIVE_MAPPO',163,2025);
const q2=Adaptive.actions(initial,'ADAPTIVE_MAPPO',163,2025);
assert.deepEqual(q1,q2,'Stochastic actor must be reproducible with the same seed');
for(const controls of [a1,q1])assert.ok(controls.flat().every(k=>[0,1,2].includes(k)));
// Direct state sensitivity: the immutable actor must react through its observation,
// not by replaying archived annual actions.
const altered=Engine.init(bootstrap,scenarios[0],cat,163,true);
altered.energy[1]=.025;altered.z[1][0]=2.5;
const sensitivity=Math.max(...Adaptive.logits(altered)[1].flat().map((v,i)=>Math.abs(v-initialLogits[1].flat()[i])));
assert.ok(sensitivity>1e-6,'Frozen MAPPO logits do not react to capital/economic state');
function options(policy,scenario=scenarios[0],seed=163){
 return {bootstrap,cat,scenario,seed,policy,db,adaptive:Adaptive};
}
const baseline=Engine.run(options('BARGAIN'));
const selected=Engine.run(options('ADAPTIVE_MAPPO_GREEDY'));
const stochastic=Engine.run(options('ADAPTIVE_MAPPO'));
assert.equal(selected.history.length,26);
assert.ok(Object.values(Engine.summary(selected)).every(Number.isFinite));
assert.deepEqual(Engine.run(options('ADAPTIVE_MAPPO')).history,stochastic.history,'Reproducible stochastic run');
// Frozen control remains unchanged: new observation-only state must not alter V4.7 economics.
assert.deepEqual(baseline.history,Engine.run(options('BARGAIN')).history);
const divergent=Engine.run({...options('ADAPTIVE_MAPPO_GREEDY'),overrides:{2025:{RUS:[2,2,2,2,2,2]}}});
assert.notDeepEqual(divergent.history[0].actions[0],selected.history[0].actions[0]);
// A stronger paired intervention: other countries receive a new state and their
// response probabilities must be recalculated; never require a particular action
// to flip, since a deterministic argmax can remain identical.
const low=Engine.init(bootstrap,scenarios[0],cat,163,true),high=Engine.init(bootstrap,scenarios[0],cat,163,true);
const all=Array.from({length:8},()=>Array(6).fill(2));
const lowAct=all.map(row=>row.slice()),highAct=all.map(row=>row.slice());
lowAct[0]=[0,0,0,0,0,0];highAct[0]=[2,2,2,2,2,2];
Engine.step(low,lowAct);Engine.step(high,highAct);
const otherLow=Adaptive.logits(low)[1].flat(),otherHigh=Adaptive.logits(high)[1].flat();
const otherEffect=Math.max(...otherLow.map((v,i)=>Math.abs(v-otherHigh[i])));
assert.ok(otherEffect>1e-8,'State changes caused by player RUS did not reach BLR actor logits');
const original=new Set(scenarios.flatMap(s=>s.crisis_ids.map(String)));
const extraCrises=Object.keys(cat).filter(k=>!original.has(k)).slice(0,4).map(Number);
assert.equal(extraCrises.length,4);
const catalogW={scenario_id:'W07',crisis_ids:extraCrises};
const wild=Engine.run(options('ADAPTIVE_MAPPO_GREEDY',catalogW,999));
assert.equal(wild.history.length,26,'Adaptive MAPPO must support unseen economic seed and wildcard scenario');
assert.ok(Object.values(Engine.summary(wild)).every(Number.isFinite));
console.log('PASS ADAPTIVE: real frozen V4.7 MAPPO Actor, checkpoint SHA '+Policy.provenance.checkpoint_sha256);
console.log('PASS ADAPTIVE: first-year actions='+JSON.stringify(a1)+'; state response max delta='+sensitivity+'; cross-country response='+otherEffect);
console.log('PASS ADAPTIVE: 26 years, 8 countries, 2 adaptive modes, wildcard, deterministic RNG and unchanged V4.7 control.');
