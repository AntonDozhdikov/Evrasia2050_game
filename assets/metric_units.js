/* Нормализация физических единиц для всех игровых сравнений (не меняет экономику V4.7). */
(function(root,factory){
 const value=factory();
 if(typeof module==='object'&&module.exports)module.exports=value;
 else root.EurasiaUnits=value;
})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const TRADE_SCALE=1e9;
 const units={
  growth:'%',inflation:'%',investments:'%',exports:'%',imports:'%',unemployment:'%',population:'%',remittances:'%',
  projects:'шт.',matured:'шт.',agreements:'шт.',mobility:'шт.',
  expenses:'усл. ед.',benefits:'усл. ед.',net:'усл. ед.',
  trade:'млрд долл.',budget:'усл. ед.',network:'коэф.',concentration:'индекс',
  reward:'усл. ед.',crises:'кризисо-лет'
 };
 const fromSummary=(key,raw)=>{
  if(!Number.isFinite(raw))throw Error('Недопустимое значение '+key);
  return key==='trade'?raw/TRADE_SCALE:raw;
 };
 const delta=(key,one,other)=>fromSummary(key,one)-fromSummary(key,other);
 const countryTrade=usd=>fromSummary('trade',usd);
 const format=(n,digits=2)=>Number.isFinite(n)?new Intl.NumberFormat('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:digits}).format(n):'—';
 const signed=(x,digits=2)=>(x>0?'+':'')+format(x,digits);
 return {units,TRADE_SCALE,fromSummary,delta,countryTrade,format,signed};
});
