// Execute the completion renderer with a minimal DOM, without browser QA.
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('src/plugarr/web/wizard.js','utf8');

// Changing step keeps the reader's scroll position while retaining focus semantics.
const navigation=source.slice(source.indexOf('function showStep('),source.indexOf('function profileEstimate('));
{
  let focusOptions=null,scrollCalls=0;
  const panel={children:[],insertBefore:()=>{}};
  const context={step:0,templatesLoaded:true,bootstrap:{},installed:false,
    document:{querySelectorAll:()=>[],querySelector:selector=>selector.includes(' h1')?{focus:options=>{focusOptions=options}}:panel},
    error:()=>{},renderSteps:()=>{},updateConditional:()=>{},updateButtons:()=>{},scheduleGraph:()=>{},loadTemplates:()=>{},
    $:id=>id==='quality-controls'?{hidden:false}:{},window:{scrollTo:()=>scrollCalls++}};
  vm.createContext(context);vm.runInContext(navigation,context);context.showStep(2);
  assert.equal(focusOptions.preventScroll,true);assert.equal(scrollCalls,0);
}

// Every named profile gets a readable, explicitly indicative volume.
const estimates=source.slice(source.indexOf('function profileEstimate('),source.indexOf('function renderServices('));
{
  const context={lang:'fr',tr:key=>({movie2h:'film de 2 h',episode45:'épisode de 45 min',defaultProfile:'Défaut PlugArr',sizeDisclaimer:'indicatif',sizeEstimate:'Taille indicative'})[key]||key,$:()=>null,Option:function(){}};
  vm.createContext(context);vm.runInContext(estimates,context);
  assert.match(context.profileEstimate('radarr','french-multi-vf-uhd-remux-web').size,/35–100 Go/);
  assert.match(context.profileEstimate('sonarr','web-1080p').size,/1.5–6 Go/);
  assert.equal(context.profileEstimate('radarr',''),null);
}

const renderer=source.slice(source.indexOf('function renderProgress('),source.indexOf('async function poll('));
function scenario(demo,status){
  const elements={};let opens=0;
  const context={demoAdminOpened:false,displayGraph:()=>{},tr:x=>x,openAdmin:()=>opens++,
    $:id=>elements[id]??=( {replaceChildren:()=>{}} ),E:()=>({append:()=>{}})};
  vm.createContext(context);vm.runInContext(renderer,context);
  const snapshot={demo,status,events:[]};
  context.renderProgress(snapshot);context.renderProgress(snapshot);
  return {opens,elements};
}
assert.equal(scenario(true,'running').opens,0);
assert.equal(scenario(true,'error').opens,0);
assert.equal(scenario(false,'done').opens,0);
const done=scenario(true,'done');
assert.equal(done.opens,1); // repeated final snapshots never open twice
assert.equal(done.elements.admin.hidden,false); // manual retry remains available
assert.equal(scenario(false,'done').elements.admin.hidden,false);
console.log('Demo completion transition OK');

// The real opener preserves the wizard, including popup blocking and retry.
const opener=source.slice(source.indexOf('async function openAdmin('),source.indexOf("$('admin').addEventListener"));
async function openingScenario(blocked=false,failed=false){
  const events=[],elements={};let resolve;
  const pending=new Promise(r=>resolve=r);
  const page={closed:false,document:{body:{}},location:{replace:url=>events.push(['navigate',url])},close:()=>events.push(['close'])};
  const context={adminOpening:false,adminUrl:null,tr:x=>x,$:id=>elements[id]??={},
    window:{open:(...args)=>{events.push(['open',...args]);return blocked?null:page;}},
    api:async()=>{events.push(['request']);await pending;if(failed)throw new Error('offline');return {url:'http://127.0.0.1:9999/?t=demo'};},
    error:message=>events.push(['error',message]),location:{assign:()=>assert.fail('Must keep wizard open')}};
  vm.createContext(context);vm.runInContext(opener,context);
  const task=context.openAdmin();
  assert.equal(events[0][0],'open');assert.equal(events[0][2],'_blank');
  await context.openAdmin();assert.equal(events.filter(e=>e[0]==='open').length,1);
  resolve();await task;
  assert.equal(context.adminOpening,false);
  if(failed){assert(events.some(e=>e[0]==='close'));assert(events.some(e=>e[0]==='error'));}
  else{
    assert.equal(elements['admin-link'].href,'http://127.0.0.1:9999/?t=demo');
    assert.equal(elements['admin-link'].hidden,false);
    assert.equal(elements['admin-notice'].textContent,blocked?'adminBlocked':'adminOpened');
    if(!blocked){assert.equal(page.opener,null);assert(events.some(e=>e[0]==='navigate'));}
  }
}
(async()=>{await openingScenario();await openingScenario(true);await openingScenario(false,true);console.log('New tab, blocked popup and retry contracts OK');})().catch(e=>{console.error(e);process.exitCode=1;});
