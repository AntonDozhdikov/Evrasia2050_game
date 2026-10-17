/* Интерактивная навигация и актуальность результатов. Без изменения расчетного движка. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
function openTarget(fragment){
 const id=(fragment||'').replace(/^#/,'');
 if(!id)return;
 const target=$(id);
 if(!target)return;
 let node=target;
 while(node){
  if(node.tagName==='DETAILS')node.open=true;
  node=node.parentElement;
 }
 if(id==='countries'||id==='archive-results')$('archive-results').open=true;
 window.requestAnimationFrame(()=>target.scrollIntoView({behavior:'smooth',block:'start'}));
}
document.querySelectorAll('a[href^="#"]').forEach(link=>{
 link.addEventListener('click',()=>{
  const href=link.getAttribute('href')||'';
  const id=href.slice(1),target=$(id);
  if(!target)return;
  let node=target;
  while(node){
   if(node.tagName==='DETAILS')node.open=true;
   node=node.parentElement;
  }
  if(link.dataset.uxOpen)openTarget('#'+link.dataset.uxOpen);
 });
});
const navLinks=[...document.querySelectorAll('.topnav a[href^="#"],.mobile-jump-nav a[href^="#"]')];
function activeNav(id){
 for(const link of navLinks){
  if(link.getAttribute('href')==='#'+id)link.setAttribute('aria-current','location');
  else link.removeAttribute('aria-current');
 }
}
const navigationSections=['party-planner','results','archive-results','reference'];
function updateCurrentSection(){
 const offset=window.innerWidth<=650?145:100;
 let selected='party-planner';
 for(const id of navigationSections){
  const node=$(id);if(node&&node.getBoundingClientRect().top<=offset)selected=id;
 }
 activeNav(selected);
}
let frame=false;
window.addEventListener('scroll',()=>{
 if(frame)return;frame=true;
 window.requestAnimationFrame(()=>{frame=false;updateCurrentSection();});
},{passive:true});
window.addEventListener('resize',updateCurrentSection);
navLinks.forEach(a=>a.addEventListener('click',()=>activeNav((a.getAttribute('href')||'').slice(1))));
if(window.location.hash)openTarget(window.location.hash);
updateCurrentSection();
window.addEventListener('hashchange',()=>{if(window.location.hash)openTarget(window.location.hash);});
window.addEventListener('eurasia:party-edited',()=>{
 const output=$('partyResultsContent'),status=$('partyResultsStatus');
 if(output&&!output.hidden){output.hidden=true;if(status)status.textContent='Решения изменены. Рассчитайте итоги снова, чтобы сравнить обновленную партию.';}
});
})();