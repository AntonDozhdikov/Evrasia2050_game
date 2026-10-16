#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const Core=require('../assets/party_core.js');
assert.equal(Core.COUNTRIES.length,8);
assert.equal(Core.START,2025);
assert.equal(Core.END,2050);
assert.equal(Core.validScenario('S20'),true);
assert.equal(Core.validScenario('W10'),true);
assert.equal(Core.validScenario('W11'),false);
assert.equal(Core.validScenario('S21'),false);
let p=Core.make({scenario:'W10',policy:'BARGAIN',seed:42});
p=Core.control(p,['RUS','ARM','KAZ']);
for(let year=2025;year<=2050;year++){
 for(let k=0;k<3;k++)p=Core.plan(p,year,p.controlled[k],[year%3,k%3,2,1,0,2]);
}
assert.equal(Object.keys(p.years).length,26);
assert.equal(Object.keys(p.years[2030]).length,3);
assert.deepEqual(p.years[2030].RUS,[2030%3,0,2,1,0,2]);
assert.equal(Core.validate(p),true);
const copy=JSON.parse(JSON.stringify(p));
assert.equal(Core.validate(copy),true);
assert.throws(()=>Core.plan(copy,2030,'BLR',[0,1,2,1,1,1]));
assert.throws(()=>Core.plan(copy,2030,'RUS',[0,1,3,1,1,1]));
assert.throws(()=>Core.control(copy,[]));
assert.throws(()=>Core.validate({...copy,controlled:['RUS','RUS']}));
assert.throws(()=>Core.validate({...copy,year:2051}));
assert.throws(()=>Core.validate({...copy,years:{2031:{KAZ:[1,1,1,1,1,7]}}}));
const newSeason=Core.setScenario(copy,'S02','NEUTRAL',163);
assert.equal(Object.keys(newSeason.years).length,0);
assert.deepEqual(newSeason.controlled,['RUS','ARM','KAZ']);
console.log('Проверены восемь стран, 26 игровых лет, шесть действий, три уровня, сохранение и валидация партий.');
