/* Data access module. Numeric values are immutable recordings of the original V4.7 run. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.EurasiaModel = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const policyNames = {'MAPPO_GREEDY':'MAPPO V4.7 · детерминированная','MAPPO':'MAPPO V4.7 · стохастическая', 'BARGAIN':'BARGAIN · эвристическая', 'NEUTRAL':'NEUTRAL · без инициативы'};
  const countryNames = {'RUS':'Россия','BLR':'Беларусь','KAZ':'Казахстан','KGZ':'Кыргызстан','UZB':'Узбекистан','TJK':'Таджикистан','TKM':'Туркменистан','ARM':'Армения'};
  const actionNames = ['Торговля','Инвестиции','Координация','Устойчивость','Фокус на партнере','Трудовая мобильность'];
  function runKey(scenario,policy,seed){return [scenario,policy,seed].join('|');}
  function getRun(db,scenario,policy,seed){let r=db.runs[runKey(scenario,policy,seed)]; if(!r)throw Error('Нет архивной траектории: '+runKey(scenario,policy,seed));return r;}
  function metricIndex(db,name){let idx=db.fields.indexOf(name);if(idx<0)throw Error('Неизвестный показатель: '+name);return idx;}
  function at(db,scenario,policy,seed,year){let i=year-2025; if(i<0||i>25)throw Error('Год вне диапазона');let run=getRun(db,scenario,policy,seed),values=Object.fromEntries(db.fields.map((k,n)=>[k,run.years[i][n]]));return {scenario,policy,seed,year,values,actions:Object.fromEntries(db.countries.map((c,j)=>[c,run.actions[i][j]]))};}
  function series(db,scenario,policy,seed,metric){let run=getRun(db,scenario,policy,seed),idx=metricIndex(db,metric);return run.years.map((v,i)=>({year:2025+i,value:v[idx]}));}
  function previous(db,scenario,policy,seed,year,metric){if(year<=2025)return null;return at(db,scenario,policy,seed,year-1).values[metric];}
  function historic(db,country,year=2024){let item=db.history[country]&&db.history[country][String(year)];if(!item)return null;return Object.fromEntries(db.historyFields.map((key,i)=>[key,{value:item.v[i],observed:!!item.observed[i]}]));}
  function exportCsv(db,scenario,policy,seed){let data=getRun(db,scenario,policy,seed);let header=['year',...db.fields];let esc=v=>v===null?'':String(v);return [header.join(','),...data.years.map((v,i)=>[2025+i,...v].map(esc).join(','))].join('\n');}
  return {policyNames,countryNames,actionNames,runKey,getRun,metricIndex,at,series,previous,historic,exportCsv};
});
