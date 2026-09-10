/* Shared wizard renderer, driven by saved connection tests and live container states. */
window.PlugArrMap=(()=>{
'use strict';
const icons=__ICONS__, $=id=>document.getElementById(id);
const labels={graphe:'Services et connexions',etapes:'tests renseignés',
  colonnes:{indexeurs:'Indexeurs',arr:'Automatisation',telechargement:'Téléchargements',vpn:'VPN',media:'Médiathèques'},
  liens:{prevu:'À vérifier',actif:'Test en cours',fait:'Dernier test réussi',echoue:'Test en échec',avertissement:'Dernier test réussi · extrémité indisponible',configure:'Configuration · sans test'},
  noeuds:{fait:'En marche',actif:'Démarrage',echoue:'Problème de santé',arrete:'Arrêté',inconnu:'Non vérifié'}};
// Kept pure so runtime semantics can be verified independently of the DOM.
function snapshot(data,status,busyEdge){
  const node_states={},node_details={},link_states={},graph_results={};
  for(const node of data.nodes){
    const current=status?.services?.find(s=>s.id===node.id);
    let state='inconnu',detail='Non vérifié';
    if(status?.engine_available===false)detail='Docker inaccessible';
    else if(current){
      if(current.state==='unknown')detail='État inconnu';
      else if(current.health==='unhealthy'){state='echoue';detail='Santé en échec';}
      else if(current.up&&current.health==='starting'){state='actif';detail='Démarrage';}
      else if(current.up){state='fait';detail='En marche';}
      else{state='arrete';detail=({absent:'Conteneur absent',paused:'En pause',restarting:'Redémarrage'})[current.state]||'Arrêté';}
    }
    node_states[node.id]=state;node_details[node.id]=detail;
  }
  for(const edge of data.connections){
    const tested=edge.testable&&edge.checked_at&&['verifiee','en echec'].includes(edge.state);
    if(tested)graph_results[edge.id]={ok:edge.state==='verifiee',warnings:[]};
    link_states[edge.id]=edge.id===busyEdge?'actif':!edge.testable?'configure':!tested?'prevu':edge.state==='en echec'?'echoue':
      node_states[edge.source]==='fait'&&node_states[edge.target]==='fait'?'fait':'avertissement';
  }
  return {graph:data.graph,node_states,node_details,link_states,graph_results,deployed:true,status:'done'};
}
let data=null,serviceStatus=null,selected=null,focused=null,api=null,afterChange=null,request=0,busyEdge=null,timer=null;
const html=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el};
const name=id=>data?.nodes.find(n=>n.id===id)?.name||id;
const state=e=>!e.testable?'configuration':e.checked_at&&e.state==='verifiee'?'verified':e.checked_at&&e.state==='en echec'?'failed':'pending';
const statusLabel=e=>({configuration:'Configuration · sans test disponible',verified:'Dernier test réussi',failed:'Test en échec',pending:'À vérifier'})[state(e)];
const view=new window.PlugArrGraphe.Vue($('graph'),$('map-progress'),$('map-bar'),$('map-states'),{noeud:chooseNode,lien:chooseEdge});
function draw(){
  if(!data)return;
  view.appliquer(snapshot(data,serviceStatus,busyEdge),icons,labels,'fr');
  view.selectionner(focused,selected);
}
function updateStatus(next){serviceStatus=next;draw();}
function list(){
  const visible=focused?data.connections.filter(e=>e.source===focused||e.target===focused):data.connections;
  $('map-list-title').textContent=(focused?'Liaisons de '+name(focused):'Toutes les liaisons')+' ('+visible.length+')';
  const box=$('connection-list');box.replaceChildren();
  if(!visible.length)box.append(html('p','','Aucune liaison représentée pour cette sélection.'));
  for(const edge of visible){
    const row=html('div','connection-row'),text=html('div');
    text.append(html('strong','',name(edge.source)+' → '+name(edge.target)),html('p','',edge.label+' · '+statusLabel(edge)));
    const button=html('button','','Voir');button.type='button';button.setAttribute('aria-label','Voir '+name(edge.source)+' vers '+name(edge.target));button.onclick=()=>chooseEdge(edge.id,true);
    row.append(text,button);box.append(row);
  }
}
function detail(){
  const box=$('map-detail');box.replaceChildren();const edge=data?.connections.find(e=>e.id===selected);
  if(!edge){
    box.append(html('h3','',focused?name(focused):'Explorez votre câblage'),html('p','',focused?'Sélectionnez une de ses liaisons pour voir son dernier test.':'Sélectionnez un service ou un câble. Le même graphe que dans l’assistant affiche ici les états de votre installation.'));
    return;
  }
  box.append(html('div','map-kicker',edge.label+' · '+edge.basis),html('h3','',name(edge.source)+' → '+name(edge.target)),html('p','',edge.description));
  const result=html('p','map-result',busyEdge===edge.id?'Opération en cours…':statusLabel(edge));result.dataset.state=state(edge);box.append(result);
  if(edge.checked_at)box.append(html('p','map-kicker','Dernier test : '+new Date(edge.checked_at).toLocaleString()));
  if(edge.detail)box.append(html('p','',edge.detail));
  if(!edge.testable){box.append(html('p','map-kicker','Liaison issue de la configuration. Aucun test individuel disponible ici.'));return;}
  const actions=html('div','actions');box.append(actions);
  for(const repair of [false,true]){
    if(repair&&!edge.repairable)continue;
    const button=html('button','',repair?'Réappliquer cette liaison':'Tester la connexion');button.type='button';button.disabled=!!busyEdge;actions.append(button);
    button.onclick=async()=>{
      if(busyEdge)return;
      if(repair&&!confirm('Réappliquer '+name(edge.source)+' → '+name(edge.target)+' ? PlugArr peut synchroniser les champs gérés, dont les identifiants.'))return;
      busyEdge=edge.id;draw();detail();
      try{await api('connections/'+(repair?'repair':'test'),{id:edge.id,confirmed:repair});busyEdge=null;await load(api,afterChange);await afterChange();}
      catch(error){busyEdge=null;draw();detail();$('map-detail').append(html('p','map-result',error.message));}
    };
  }
  if(!edge.repairable)box.append(html('p','map-kicker','Service adopté : réparation automatique désactivée.'));
}
function chooseEdge(id,moveFocus=false){selected=id;focused=null;draw();detail();list();if(moveFocus)$('map-detail').focus();}
function chooseNode(id){focused=id;selected=null;draw();detail();list();}
async function load(apiCall,changed){
  api=apiCall;afterChange=changed;const version=++request;clearTimeout(timer);
  try{
    const next=await api('connections');if(version!==request)return;
    const changedData=JSON.stringify(next)!==JSON.stringify(data);data=next;
    if(!data.connections.some(e=>e.id===selected))selected=null;
    if(!data.nodes.some(n=>n.id===focused))focused=null;
    const tests=data.connections.filter(e=>e.testable);
    $('metric-connections').textContent=tests.filter(e=>state(e)==='verified').length+' / '+tests.length+' testables';
    $('map-count').textContent=data.nodes.length+' services · '+data.connections.length+' liaisons · actualisé à '+new Date().toLocaleTimeString();
    $('wiring-graph').classList.remove('disconnected');draw();
    if(changedData||!$('map-detail').children.length){detail();list();}
  }catch(error){
    if(version!==request)return;
    $('wiring-graph').classList.add('disconnected');draw();detail();$('map-count').textContent='Connexion à la console interrompue. Nouvelle tentative dans 5 secondes.';
  }finally{if(version===request)timer=setTimeout(()=>load(apiCall,changed),5000);}
}
$('map-reset').onclick=()=>{selected=null;focused=null;draw();detail();if(data)list();};
return {load,updateStatus,snapshot};
})();
