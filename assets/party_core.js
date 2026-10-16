/* Проверяемая схема записи решений игрока. Никаких экономических расчетов. */
(function(root,factory){
 const value=factory();
 if(typeof module==='object'&&module.exports)module.exports=value;
 else root.EurasiaParty=value;
})(typeof self!=='undefined'?self:this,function(){
'use strict';
const COUNTRIES=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM'];
const POLICIES=['MAPPO_GREEDY','MAPPO','BARGAIN','NEUTRAL','ADAPTIVE_MAPPO_GREEDY','ADAPTIVE_MAPPO'];
const START=2025,END=2050,VERSION=1;
function checkAction(values){
 return Array.isArray(values)&&values.length===6&&values.every(v=>Number.isInteger(v)&&v>=0&&v<=2);
}
function validScenario(s){return /^S(0[1-9]|1[0-9]|20)$/.test(s)||/^W(0[1-9]|10)$/.test(s);}
function make(opts={}){
 const scenario=validScenario(opts.scenario)?opts.scenario:'S01';
 const policy=POLICIES.includes(opts.policy)?opts.policy:'BARGAIN';
 const seed=Number.isInteger(Number(opts.seed))?Number(opts.seed):163;
 return {format:'evrasia2050-party-draft',version:VERSION,model:'V4.7',scenario,policy,seed,year:START,
  controlled:['RUS'],years:{},notes:'Решения игрока сохранены для будущего расчетного движка. Экономические результаты не рассчитаны.'};
}
function validate(value){
 if(!value||typeof value!=='object'||value.format!=='evrasia2050-party-draft'||value.version!==VERSION)throw Error('Неизвестный формат игровой партии');
 if(!validScenario(value.scenario))throw Error('Неизвестный сценарий');
 if(!POLICIES.includes(value.policy))throw Error('Неизвестная стратегия остальных стран');
 if(!Number.isInteger(value.seed)||value.seed<0||value.seed>4294967295)throw Error('Недопустимое начальное число');
 if(!Number.isInteger(value.year)||value.year<START||value.year>END)throw Error('Год вне игрового периода');
 if(!Array.isArray(value.controlled)||value.controlled.length<1||value.controlled.length>8||new Set(value.controlled).size!==value.controlled.length||value.controlled.some(c=>!COUNTRIES.includes(c)))throw Error('Укажите от одного до восьми государств');
 if(!value.years||typeof value.years!=='object'||Array.isArray(value.years))throw Error('Неверная запись ходов');
 if(Object.keys(value.years).length>26)throw Error('Слишком много игровых лет');
 for(const [year,rows] of Object.entries(value.years)){
  const y=Number(year);if(!/^\d{4}$/.test(year)||y<START||y>END)throw Error('Недопустимый год в списке ходов');
  if(!rows||typeof rows!=='object'||Array.isArray(rows)||Object.keys(rows).length>8)throw Error('Неверные решения за год');
  for(const [country,actions] of Object.entries(rows)){
   if(!COUNTRIES.includes(country)||!checkAction(actions))throw Error('Недопустимые решения страны '+country);
  }
 }
 return true;
}
function clone(p){validate(p);return JSON.parse(JSON.stringify(p));}
function control(p,countries){
 if(!Array.isArray(countries)||countries.length<1||new Set(countries).size!==countries.length||countries.some(c=>!COUNTRIES.includes(c)))throw Error('Выберите от одного до восьми государств');
 const q=clone(p);q.controlled=[...countries];validate(q);return q;
}
function plan(p,year,country,actions){
 if(!Number.isInteger(year)||year<START||year>END)throw Error('Год за пределами партии');
 if(!p.controlled.includes(country))throw Error('Страна не передана под управление игроку');
 if(!checkAction(actions))throw Error('Для каждого из шести решений выберите уровень 0, 1 или 2');
 const q=clone(p);if(!q.years[year])q.years[year]={};q.years[year][country]=[...actions];q.year=year;validate(q);return q;
}
function remove(p,year,country){const q=clone(p);if(q.years[year]){delete q.years[year][country];if(!Object.keys(q.years[year]).length)delete q.years[year];}return q;}
function goto(p,year){if(!Number.isInteger(year)||year<START||year>END)throw Error('Недопустимый год');const q=clone(p);q.year=year;return q;}
function setScenario(p,scenario,policy,seed){
 if(!validScenario(scenario)||!POLICIES.includes(policy)||!Number.isInteger(seed)||seed<0||seed>4294967295)throw Error('Неправильные условия партии');
 const q=clone(p);q.scenario=scenario;q.policy=policy;q.seed=seed;q.year=START;q.years={};return q;
}
return {COUNTRIES,POLICIES,START,END,VERSION,checkAction,validScenario,make,validate,clone,control,plan,remove,goto,setScenario};
});