'use strict';
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'..');
const ctx={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'assets/data.js'),'utf8'),ctx,{timeout:30000});
const D=ctx.window.EURASIA_DATA,M=require('../assets/model.js');
const keys=Object.keys(D.runs);
assert.strictEqual(keys.length,240);assert.strictEqual(D.countries.length,8);
assert.strictEqual(D.scenarios.length,20);assert.strictEqual(D.fields.length,15);
assert.deepStrictEqual(Array.from(D.manifest.seeds),[163,272,381]);
let states=0,actions=0;
for(const k of keys){
 const [scenario,policy,seed]=k.split('|'),run=D.runs[k];
 assert.strictEqual(run.years.length,26,k);assert.strictEqual(run.actions.length,26,k);
 for(let i=0;i<26;i++){
  assert.strictEqual(run.years[i].length,D.fields.length,k);
  assert.strictEqual(run.actions[i].length,8,k);
  for(const a of run.actions[i]){
   assert.strictEqual(a.length,6,k);assert(a.every(v=>Number.isInteger(v)&&v>=0&&v<=2),k);
   actions++;
  }
  const snap=M.at(D,scenario,policy,Number(seed),2025+i);
  for(const field of D.fields)assert.strictEqual(snap.values[field],run.years[i][D.fields.indexOf(field)]);
  states++;
 }
 const csv=M.exportCsv(D,scenario,policy,Number(seed)).trim().split('\n');
 assert.strictEqual(csv.length,27,k);
}
assert.strictEqual(states,6240);assert.strictEqual(actions,49920);
assert.strictEqual(D.manifest.simulation,'archived_replay_only');
assert.strictEqual(D.manifest.research_version,'V4.7');
console.log('PASS: 240 trajectories, 6240 yearly states, 49920 agent actions, 8 countries, 20 scenarios, 4 policies, 3 seeds');
