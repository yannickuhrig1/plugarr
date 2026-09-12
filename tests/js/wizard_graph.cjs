// Tests de l'etat du vrai composant, sans navigateur ni mesure visuelle.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag) {
    this.tag=tag;this.children=[];this.attrs={};this.textContent='';this.isConnected=true;this.listeners={};this.dataset={};
    const values=new Set();
    this.classList={add:(...items)=>items.forEach(x=>values.add(x)),remove:(...items)=>items.forEach(x=>values.delete(x)),contains:x=>values.has(x),toggle:(x,force)=>{if(force??!values.has(x))values.add(x);else values.delete(x);}};
    this.style={setProperty:()=>{}};
  }
  addEventListener(event,callback){this.listeners[event]=callback;}
  append(...children){this.children.push(...children);}
  focus(){this.focused=true;}
  setAttribute(key,value){this.attrs[key]=String(value);if(key==='class')String(value).split(' ').forEach(x=>this.classList.add(x));}
  setAttributeNS(ns,key,value){this.setAttribute(key,value);}
  appendChild(child){this.children.push(child);return child;}
  insertBefore(child,ref){const i=this.children.indexOf(ref);if(i<0)this.children.push(child);else this.children.splice(i,0,child);}
  replaceChildren(...children){this.children=children;}
  set innerHTML(value){assert.equal(value,'');this.children=[];}
  querySelector(tag){for(const child of this.children){if(child.tag===tag)return child;const nested=child.querySelector(tag);if(nested)return nested;}return null;}
  getTotalLength(){return 100;}
  getBoundingClientRect(){return {};}
}
const context={window:{setTimeout:callback=>callback(),matchMedia:()=>({matches:true})},document:{createElementNS:(_,tag)=>new Element(tag),createElement:tag=>new Element(tag)},requestAnimationFrame:()=>{},Set};
vm.runInNewContext(fs.readFileSync('src/plugarr/web/graph.js','utf8'),context);
const api=context.window.PlugArrGraphe;
const labels={graphe:'test',prevu:'planned',actif:'active',fait:'done',echoue:'failed',avertissement:'warning',configure:'configured',etapes:'steps',colonnes:{}};
const graph={id:'test',colonnes:['arr','media'],etapes:['s/first','s/second'],noeuds:[
 {id:'s',nom:'S',colonne:'arr',teinte:'primaire',reglages:['s/first','s/second']},
 {id:'t',nom:'T',colonne:'media',teinte:'primaire',reglages:[]},
],liens:[{id:'one',source:'s',cible:'t',etape:'s/first',structure:false,description:'link'},
{id:'two',source:'s',cible:'t',etape:'s/second',structure:false,description:'link'}]};
const host=new Element('div'),count=new Element('span'),bar=new Element('progress'),list=new Element('ul');
const view=new api.Vue(host,count,bar,list);
const snapshot={graph,graph_results:{},status:'idle',deployed:false};
function collect(root,predicate){return root.children.flatMap(child=>[...(predicate(child)?[child]:[]),...collect(child,predicate)]);}
function node(id){return collect(host,e=>e.attrs['data-service']===id)[0];}
view.appliquer(snapshot,{},labels,'fr');
assert.equal(count.textContent,'0 / 2 steps');assert.equal(collect(host,e=>e.classList.contains('tire')).length,0);
assert(node('s').classList.contains('prevu'));
snapshot.status='running';snapshot.active_step='s/first';view.appliquer(snapshot,{},labels,'fr');
assert(node('s').classList.contains('actif'));assert.equal(count.textContent,'0 / 2 steps');
snapshot.graph_results['s/first']={ok:false,warnings:[]};snapshot.active_step='s/second';view.appliquer(snapshot,{},labels,'fr');
assert(node('s').classList.contains('echoue'));assert.equal(count.textContent,'1 / 2 steps');
snapshot.graph_results['s/second']={ok:true,warnings:[]};snapshot.active_step=null;snapshot.status='partial';view.appliquer(snapshot,{},labels,'fr');
assert(node('s').classList.contains('echoue'));assert.equal(count.textContent,'2 / 2 steps');
view.appliquer(snapshot,{},labels,'fr');assert.equal(count.textContent,'2 / 2 steps');
assert(list.children.some(e=>e.textContent==='S : failed'));
// Un resultat composite recu une fois ne compte qu'une fois meme avec deux cables.
graph.id='composite';graph.etapes=['s/first'];graph.noeuds[0].reglages=['s/first'];graph.liens[1].etape='s/first';snapshot.graph_results={'s/first':{ok:true,warnings:['needs verification']}};
view.appliquer(snapshot,{},labels,'fr');assert.equal(count.textContent,'1 / 1 steps');assert(node('s').classList.contains('avertissement'));
// Un tunnel prevu ne devient jamais vert sans evenement, meme en etat termine.
graph.id='structural';graph.liens.forEach(e=>e.structure=true);graph.etapes=[];graph.noeuds.forEach(n=>n.reglages=[]);snapshot.graph_results={};snapshot.status='done';
view.appliquer(snapshot,{},labels,'fr');assert.equal(collect(host,e=>e.classList.contains('structure')).length,0);
snapshot.deployed=true;view.appliquer(snapshot,{},labels,'fr');assert(node('s').classList.contains('configure'));assert(!node('s').classList.contains('fait'));
const empty=api.disposer({colonnes:[],noeuds:[]});assert(empty.largeur>0&&empty.hauteur>0);
console.log('Graph component: planned/live/failure/reconnect/composite/structural states passed');

// Administration adapter + actual shared SVG: runtime failures never inherit install success.
const elements={};
context.document.getElementById=id=>elements[id]??=new Element('div');
context.document.addEventListener=()=>{};
context.setTimeout=()=>1;context.clearTimeout=()=>{};context.Date=Date;
vm.runInNewContext(fs.readFileSync('src/plugarr/web/admin-graph.js','utf8').replace('__ICONS__','{}'),context);
const map=context.window.PlugArrMap;
const topo={nodes:[{id:'s',name:'S'},{id:'t',name:'T'}],
 connections:[{id:'one',source:'s',target:'t',label:'Link',description:'Test',testable:true,repairable:true,state:'non verifiee'}],
 graph:{id:'admin',colonnes:['arr','media'],noeuds:[{id:'s',nom:'S',colonne:'arr',teinte:'primaire',reglages:[]},{id:'t',nom:'T',colonne:'media',teinte:'primaire',reglages:[]}],liens:[{id:'one',source:'s',cible:'t',etape:'one',structure:false,verbe:'Link',description:'Test'}],etapes:['one']}};
const live={engine_available:true,services:[{id:'s',state:'running',up:true,health:''},{id:'t',state:'running',up:true,health:''}]};
assert.equal(map.snapshot(topo,live).node_states.s,'fait');
assert.equal(map.snapshot(topo,live).link_states.one,'prevu');
topo.connections[0].state='verifiee';topo.connections[0].checked_at='2026-09-07T00:00:00Z';
assert.equal(map.snapshot(topo,live).link_states.one,'fait');
live.services[1].up=false;live.services[1].state='exited';
assert.equal(map.snapshot(topo,live).link_states.one,'avertissement');
assert.equal(map.snapshot(topo,live).node_states.t,'arrete');
assert.equal(map.snapshot(topo,{engine_available:false}).node_states.s,'inconnu');
assert.equal(map.snapshot(topo,{engine_available:false}).link_states.one,'avertissement');
topo.connections[0].state='en echec';
assert.equal(map.snapshot(topo,live).link_states.one,'echoue');
assert.equal(map.snapshot(topo,live,'one').link_states.one,'actif');
topo.connections[0].testable=false;
assert.equal(map.snapshot(topo,live).link_states.one,'configure');
topo.connections[0].testable=true;topo.connections[0].state='verifiee';live.services[1].up=true;live.services[1].state='running';
(async()=>{
  await map.load(async()=>topo,async()=>{});map.updateStatus(live);
  const canvas=elements.graph;
  assert(collect(canvas,e=>e.classList.contains('flux')&&e.classList.contains('coule')).length===1);
  const actualNode=collect(canvas,e=>e.attrs['data-service']==='s')[0];
  actualNode.listeners.keydown({key:'Enter',preventDefault:()=>{}});
  assert(actualNode.classList.contains('selected'));
  const sameSvg=canvas.children[0];await map.load(async()=>topo,async()=>{});
  assert.equal(canvas.children[0],sameSvg); // polling preserves the SVG and focus
  map.updateStatus({engine_available:false});
  assert.equal(collect(canvas,e=>e.classList.contains('flux')&&e.classList.contains('coule')).length,0);
  await map.load(async()=>{throw new Error('offline')},async()=>{});
  assert(elements['wiring-graph'].classList.contains('disconnected'));
  await map.load(async()=>topo,async()=>{});
  assert(!elements['wiring-graph'].classList.contains('disconnected'));
  console.log('Administration runtime, shared SVG, selection and reconnect passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
