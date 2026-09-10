'use strict';
const $ = id => document.getElementById(id);
const E = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
const EN = {
setup:'INSTALLATION',local:'On your computer',localDescription:'Your settings stay in PlugArr.',tui:'Open terminal TUI',assistant:'Configuration assistant',demoNotice:'Demo mode — no real installation, no Docker calls.',existingNotice:'Existing installation: credentials, versions and paths will be preserved.',loading:'Loading your assistant…',
step1:'STEP 01 / 06',step2:'STEP 02 / 06',step3:'STEP 03 / 06',step4:'STEP 04 / 06',step5:'STEP 05 / 06',step6:'STEP 06 / 06',servicesTitle:'Your stack, your way.',servicesIntro:'Choose your applications. PlugArr will add the required dependencies and connect them.',selectionHelp:'Editable before installation',foldersTitle:'A place for every file.',foldersIntro:'These paths refer to the computer running PlugArr.',platform:'Platform',projectName:'Docker stack name',dataRoot:'Media and downloads folder',dataHelp:'A shared folder preserves hardlinks where supported by the filesystem.',configRoot:'Application settings folder',username:'Service username',passwordHelp:'PlugArr generates the passwords.',timezone:'Time zone',serviceLanguage:'Service language',projectFolder:'Project folder',vpnTitle:'Your download connection.',vpnIntro:'Use Gluetun to route your download client through your VPN provider.',noTorrent:'No download client selected: this step is not needed.',enableVpn:'Enable VPN',vpnHelp:'Your VPN credentials stay on this computer.',provider:'Provider',protocol:'Protocol',wireguardKey:'WireGuard private key',wireguardAddress:'WireGuard addresses (if required by your provider)',vpnUser:'OpenVPN username',vpnPassword:'OpenVPN password',location:'Location (optional)',vpnPreserved:'Leave credentials empty to keep those of the same provider and protocol.',vpnWarning:'Without a VPN, downloads will use this computer’s public IP address.',qualityTitle:'The quality you want.',qualityIntro:'Recyclarr applies TRaSH profiles to Sonarr and Radarr.',noQuality:'Select Recyclarr with Sonarr or Radarr to use quality profiles.',qualityDefaults:'Choose one profile per application from all available templates, or keep the default profile.',loadProfiles:'Refresh available profiles',reviewTitle:'Check before you start.',reviewIntro:'Review the applications and paths. Installation starts only after your confirmation.',recheck:'Check again',confirm:'I confirm the settings and operations shown above.',progressTitle:'Your stack is taking shape.',progressIntro:'Keep PlugArr open during installation. Completed steps appear below.',logs:'Detailed log',openAdmin:'Open administration in a new tab',adminWaiting:'Opening administration…',adminOpened:'Administration opened in another tab. You can keep this installation summary open.',adminBlocked:'Use the link below to open administration in a new tab.',adminLink:'Open administration in a new tab',retry:'Review settings and try again',remember:'Use the web interface next time',back:'Back',next:'Continue',
services:'Applications',folders:'Folders',vpn:'VPN',quality:'Quality',review:'Review',installation:'Installation',arr:'Automation',download:'Downloads',media:'Media libraries',ui:'Interfaces',selected:'applications selected',defaultProfile:'PlugArr default',checking:'Checking configuration…',install:'Confirm and install',simulate:'Run simulation',blocked:'Resolve the blocking checks before continuing.',demoCheck:'Checks are simulated. Docker availability has not been checked.',ready:'Ready for confirmation',running:'Installation in progress…',done:'Installation completed',partial:'Installation completed with wiring errors',error:'Installation interrupted',demoDone:'Simulation completed — nothing was installed.',idle:'Waiting to start',checkingTemplates:'Loading available profiles…',noTemplates:'Profiles could not be loaded. Keep the default profiles or try again.',templatesReady:'Available profiles loaded.',bundledProfiles:'Complete catalog included with this demo (7 September 2026).',saving:'Saving your choice…',sessionMissing:'Session missing. Open the full URL shown in the terminal.',networkError:'Connection lost. Keep the PlugArr terminal open and try again.',noSelection:'Choose at least one application.',switched:'Return to the terminal: the TUI is opening. Unsaved web entries were not transferred.',retryWarning:'Review the settings and run the checks again before retrying.',unavailable:'Unavailable',vpnOn:'Enabled',vpnOff:'Disabled',simulation:'SIMULATION',localBadge:'LOCAL',profile:'Profile',notInstalled:'The demo administration opens in a new tab. No service was installed.',existingLocked:'Already installed',progressError:'Progress temporarily unavailable. Reconnecting…',optional:'optional',qualityInherited:'Existing profile',sizeEstimate:'Indicative size',sizeDisclaimer:'Broad estimates only, not download limits. Actual size depends on duration, source, codec, audio tracks and the release found.',movie2h:'2-hour movie',episode45:'45-minute episode',
};
const FR = {adminWaiting:'Ouverture de l’administration…',adminOpened:'L’administration est ouverte dans un autre onglet. Vous pouvez conserver ce récapitulatif.',adminBlocked:'Utilisez le lien ci-dessous pour ouvrir l’administration dans un nouvel onglet.',services:'Applications',folders:'Dossiers',vpn:'VPN',quality:'Qualité',review:'Vérification',installation:'Installation',arr:'Automatisation',download:'Téléchargements',media:'Médiathèques',ui:'Interfaces',selected:'applications sélectionnées',defaultProfile:'Défaut PlugArr',checking:'Vérification de la configuration…',install:'Confirmer et installer',simulate:'Lancer la simulation',blocked:'Résolvez les contrôles bloquants avant de continuer.',demoCheck:'Les contrôles sont simulés. La disponibilité de Docker n’a pas été vérifiée.',ready:'Prêt pour confirmation',running:'Installation en cours…',done:'Installation terminée',partial:'Installation terminée avec des erreurs de câblage',error:'Installation interrompue',demoDone:'Simulation terminée — rien n’a été installé.',idle:'En attente de lancement',checkingTemplates:'Chargement des profils disponibles…',noTemplates:'Impossible de charger les profils. Conservez les profils par défaut ou réessayez.',templatesReady:'Profils disponibles chargés.',bundledProfiles:'Catalogue complet fourni avec cette démo (7 septembre 2026).',saving:'Enregistrement du choix…',sessionMissing:'Session absente. Ouvrez le lien complet affiché dans le terminal.',networkError:'Connexion perdue. Gardez le terminal PlugArr ouvert, puis réessayez.',noSelection:'Choisissez au moins une application.',switched:'Retournez au terminal : le TUI s’ouvre. Les saisies web non enregistrées ne sont pas transférées.',retryWarning:'Relisez les réglages et relancez les vérifications avant de réessayer.',unavailable:'Indisponible',vpnOn:'Activé',vpnOff:'Désactivé',simulation:'SIMULATION',localBadge:'LOCAL',profile:'Profil',notInstalled:'La console de démonstration s’ouvre dans un nouvel onglet. Aucun service n’a été installé.',existingLocked:'Déjà installé',progressError:'Progression momentanément indisponible. Reconnexion…',optional:'facultatif',qualityInherited:'Profil existant',sizeEstimate:'Taille indicative',sizeDisclaimer:'Ordres de grandeur uniquement, pas des limites de téléchargement. La taille réelle dépend de la durée, de la source, du codec, des pistes audio et de la version trouvée.',movie2h:'film de 2 h',episode45:'épisode de 45 min'};
document.querySelectorAll('[data-i18n]').forEach(e => { FR[e.dataset.i18n] = e.textContent; });
let lang = 'fr', step = 0, bootstrap, form, effective = [], plan = null, busy = false, installed = false, lastProgress = null, polling = null;
let templatesLoaded = false;
let demoAdminOpened = false, adminOpening = false, adminUrl = null;
let graphView, graphSnapshot = null, graphRequest = 0, graphTimer, liveController;
const GRAPH_LABELS = {
  fr: {graphe:'Carte des connexions',prevu:'Prévu',actif:'Étape en cours',fait:'Étape réussie',echoue:'Étape échouée',avertissement:'À vérifier',configure:'Configuré, non testé',etapes:'étapes traitées',
    colonnes:{indexeurs:'Indexeurs',arr:'Automatisation',telechargement:'Téléchargements',vpn:'VPN',media:'Médiathèques'},
    preview:'Plan selon votre sélection. Aucun lien n’est encore présenté comme vérifié.',
    live:'Mise à jour en direct par PlugArr. Les animations représentent les résultats des étapes, pas le trafic réseau.',
    demo:'Démonstration : tous les états et animations sont simulés.',
    disconnected:'Connexion interrompue : derniers états reçus affichés. Reconnexion en cours…',
    updating:'Mise à jour du plan…',failed:'Impossible d’actualiser le graphe. Réessayez une sélection.',
    details:'Avancement par application',expand:'Agrandir',collapse:'Réduire',finished:'Résultats de l’installation. Les liaisons de configuration ne constituent pas un test réseau.'},
  en: {graphe:'Connection map',prevu:'Planned',actif:'Step running',fait:'Step succeeded',echoue:'Step failed',avertissement:'Check required',configure:'Configured, untested',etapes:'steps processed',
    colonnes:{indexeurs:'Indexers',arr:'Automation',telechargement:'Downloads',vpn:'VPN',media:'Media libraries'},
    preview:'Plan based on your selection. No link is claimed to be verified yet.',
    live:'Live updates from PlugArr. Animations represent step results, not network traffic.',
    demo:'Demonstration: all statuses and animations are simulated.',
    disconnected:'Connection interrupted: showing the last received statuses. Reconnecting…',
    updating:'Updating the plan…',failed:'Could not update the graph. Try changing the selection again.',
    details:'Progress by application',expand:'Expand',collapse:'Collapse',finished:'Installation results. Configuration links are not network tests.'}
};
function displayGraph(snapshot) {
  if(!snapshot?.graph || !bootstrap) return;
  graphSnapshot = snapshot;
  if(!graphView) graphView = new window.PlugArrGraphe.Vue($('graph-canvas'),$('graph-count'),$('graph-bar'),$('graph-state-list'));
  const labels = GRAPH_LABELS[lang];
  graphView.appliquer(snapshot,bootstrap.icons,labels,lang);
  $('wiring-graph').classList.remove('disconnected');
  $('graph-title').textContent=labels.graphe;
  $('graph-details-title').textContent=labels.details;
  $('graph-status').textContent=labels[snapshot.status==='idle'?'preview':snapshot.status==='running'?'live':'finished']+(snapshot.demo?' '+labels.demo:'');
  $('graph-legend').replaceChildren(...[['prevu',''],['actif','running'],['fait','done'],['echoue','failed'],['configure','structural']].map(([key,cls])=>E('span',labels[key],cls)));
}
function scheduleGraph() {
  if(!bootstrap || installed || step>=4) return;
  clearTimeout(graphTimer);
  const revision=++graphRequest;
  $('graph-status').textContent=GRAPH_LABELS[lang].updating;
  $('wiring-graph').classList.add('disconnected');
  graphTimer=setTimeout(async()=>{
    try {
      const snapshot=await api('/api/graph',{services:form.services,language:$('language').value||form.language,vpn_enabled:$('vpn-enabled').checked});
      if(revision===graphRequest&&!installed&&step<4)displayGraph(snapshot);
    } catch(_){if(revision===graphRequest)$('graph-status').textContent=GRAPH_LABELS[lang].failed;}
  },100);
}
const tr = key => (lang === 'en' ? EN : FR)[key] || FR[key] || key;
let token = new URLSearchParams(location.hash.slice(1)).get('token');
try { if (token) sessionStorage.setItem('plugarr-wizard-token', token); else token = sessionStorage.getItem('plugarr-wizard-token'); } catch (_) { /* La session reste utilisable en memoire. */ }
if (location.hash) history.replaceState(null, '', location.pathname);
async function api(path, body) {
  let response;
  try { response = await fetch(path, {method:body === undefined ? 'GET':'POST',headers:{Authorization:'Bearer '+(token || ''),...(body === undefined ? {}:{'Content-Type':'application/json'})},...(body === undefined ? {}:{body:JSON.stringify(body)})}); }
  catch (_) { throw new Error(tr('networkError')); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || tr('unavailable'));
  return data;
}
function error(message) { $('error').hidden = !message; $('error').textContent = message || ''; if(message) $('error').scrollIntoView({block:'nearest'}); }
function setBusy(value) { busy=value; $('next').disabled = value || (step===4 && (!plan?.plan_id || !$('confirm').checked)); $('back').disabled=value; $('recheck').disabled=value; }
function translate() {
  document.documentElement.lang=lang;
  document.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = tr(e.dataset.i18n); });
  $('mode').textContent=tr(bootstrap?.demo ? 'simulation':'localBadge');
  if(graphSnapshot)displayGraph(graphSnapshot);
  if(bootstrap) { renderSteps(); renderServices(); updateConditional(); refreshProfileEstimates(); if(plan) renderReview(); if(lastProgress) renderProgress(lastProgress); updateButtons(); }
}
function renderSteps() {
  $('steps').replaceChildren();
  ['services','folders','vpn','quality','review','installation'].forEach((key,i)=>{ const item=E('li',undefined,i===step?'current':i<step?'completed':''); if(i===step)item.setAttribute('aria-current','step'); item.append(E('span', i<step?'✓':String(i+1).padStart(2,'0'),'step-number'),E('span',tr(key),'step-label')); $('steps').append(item); });
}
function updateButtons() {
  $('back').hidden=step===0 || step===5;
  $('footer').hidden=step===5;
  $('next').textContent=step===4?tr(bootstrap.demo?'simulate':'install'):tr('next');
  $('remember').closest('label').hidden=bootstrap.demo;
  setBusy(busy);
}
function showStep(index) {
  step=index;
  document.querySelectorAll('.step-panel').forEach(e=>e.hidden=Number(e.dataset.step)!==index);
  error(''); renderSteps(); updateConditional(); updateButtons();
  const panel=document.querySelector(`.step-panel[data-step="${index}"]`);
  panel.insertBefore($('wiring-graph'),panel.children[3]||null);
  if(index<4)scheduleGraph();
  if(index===3&&!templatesLoaded&&!$('quality-controls').hidden)loadTemplates();
  document.querySelector(`.step-panel[data-step="${index}"] h1`)?.focus({preventScroll:true});
}

function profileEstimate(service,name) {
  const id=(name||'').toLowerCase();
  if(!id)return null;
  let film='4–15 GB',episode='1.5–6 GB',quality='1080p WEB / Blu-ray';
  const is2160=id.includes('2160p')||id.includes('uhd')||/^sqp-[2-5]/.test(id);
  const isRemux=id.includes('remux');
  if(is2160&&isRemux){film='35–100 GB';episode='13–38 GB';quality='4K Remux / WEB';}
  else if(is2160){film='12–40 GB';episode='5–15 GB';quality='4K WEB / Blu-ray';}
  else if(isRemux){film='15–40 GB';episode='6–15 GB';quality='1080p Remux / WEB';}
  if(lang==='fr'){film=film.replace('GB','Go');episode=episode.replace('GB','Go');}
  return {quality,size:service==='radarr'?`${film} / ${tr('movie2h')}`:`${episode} / ${tr('episode45')}`};
}
function profileOption(service,name) {
  const option=new Option(name||tr('defaultProfile'),name);option.dataset.profileName=name;
  const estimate=profileEstimate(service,name);if(estimate)option.textContent=`${name} — ${estimate.size}`;
  return option;
}
function refreshProfileEstimate(service) {
  const select=$('quality-'+service),detail=$('quality-size-'+service);if(!select||!detail)return;
  for(const option of select.options){const name=option.dataset.profileName;if(name!==undefined){const estimate=profileEstimate(service,name);option.textContent=estimate?`${name} — ${estimate.size}`:tr('defaultProfile');}}
  const estimate=profileEstimate(service,select.value);
  detail.textContent=estimate?`${tr('sizeEstimate')} : ${estimate.size} · ${estimate.quality}`:tr('sizeDisclaimer');
}
function refreshProfileEstimates(){for(const service of ['sonarr','radarr'])refreshProfileEstimate(service);}
function renderServices() {
  const target=$('services'); target.replaceChildren();
  for(const category of ['arr','download','media','ui']) {
    const list=bootstrap.catalog.filter(s=>s.category===category); if(!list.length) continue;
    target.append(E('h2',tr(category),'category-title')); const grid=E('div',undefined,'service-grid');
    for(const service of list) {
      const label=E('label',undefined,'service-card');
      const icon=bootstrap.icons[service.id];
      if(icon){const img=E('img');img.src=icon;img.alt='';img.width=38;img.height=38;label.append(img);}else label.append(E('span',service.name.slice(0,1),'initial'));
      label.append(E('span',service.name,'service-name'));
      const input=E('input');input.type='checkbox';input.value=service.id;input.checked=form.services.includes(service.id);input.setAttribute('aria-label',service.name);
      if(bootstrap.existing && bootstrap.form.services.includes(service.id)){input.disabled=true;input.title=tr('existingLocked');}
      input.addEventListener('change',()=>{ form.services=[...target.querySelectorAll('input:checked')].map(e=>e.value); plan=null; updateSelection(); scheduleGraph(); });
      label.append(input,E('p',service.notes));
      if(service.experimental)label.append(E('p',service.experimental,'experimental'));
      grid.append(label);
    }
    target.append(grid);
  }
  updateSelection();
}
function updateSelection() { $('selection-count').textContent=`${form.services.length} ${tr('selected')}`; }
function readFields() {
  for(const id of ['platform','project_name','data_root','config_root','username','timezone','language']) form[id]=$(id).value;
  form.ui_language=lang;
  form.vpn={enabled:$('vpn-enabled').checked,provider:$('vpn-provider').value,vpn_type:$('vpn-type').value,wireguard_private_key:$('vpn-key').value,wireguard_addresses:$('vpn-addresses').value,openvpn_user:$('vpn-user').value,openvpn_password:$('vpn-password').value,countries:$('vpn-countries').value};
  if(!effective.some(s=>bootstrap.download_clients.includes(s))) form.vpn.enabled=false;
  form.recyclarr_templates={};
  if(effective.includes('recyclarr')) for(const service of ['sonarr','radarr']) {const select=$('quality-'+service);if(effective.includes(service)&&select?.value)form.recyclarr_templates[service]=select.value;}
}
function fillFields() {
  for(const id of ['platform','project_name','data_root','config_root','username','timezone','language'])$(id).value=form[id];
  if(bootstrap.existing)for(const id of ['platform','project_name','data_root','config_root','username'])$(id).disabled=true;
  $('vpn-provider').replaceChildren(new Option('—',''),...Object.keys(bootstrap.providers).map(p=>new Option(p,p)));
  $('vpn-enabled').checked=form.vpn.enabled;
  $('vpn-provider').value=form.vpn.provider;
  $('vpn-type').value=form.vpn.vpn_type;
  $('vpn-key').value=form.vpn.wireguard_private_key;
  $('vpn-addresses').value=form.vpn.wireguard_addresses;
  $('vpn-user').value=form.vpn.openvpn_user;
  $('vpn-password').value=form.vpn.openvpn_password;
  $('vpn-countries').value=form.vpn.countries;
  $('project-dir').textContent=bootstrap.project_dir;
  $('vpn-preserved').hidden=!bootstrap.existing || !bootstrap.form.vpn.enabled;
  for(const service of ['sonarr','radarr']) {
    const label=E('label');label.id='quality-label-'+service;label.append(E('span',service==='sonarr'?'Sonarr':'Radarr'));
    const select=E('select');select.id='quality-'+service;select.append(profileOption(service,''));
    const existing=form.recyclarr_templates[service];if(existing){select.append(profileOption(service,existing));select.value=existing;}
    const detail=E('small',tr('sizeDisclaimer'),'profile-size');detail.id='quality-size-'+service;
    select.addEventListener('change',()=>refreshProfileEstimate(service));
    label.append(select,detail);$('quality-fields').append(label);refreshProfileEstimate(service);
  }
  updatePlaces();
}
function updatePlaces() {
  const provider=bootstrap.providers[$('vpn-provider').value];
  $('vpn-places').replaceChildren(...(provider?.choices || []).map(x=>new Option(x,x)));
  $('places-label').textContent=(lang==='fr'&&provider?.label?provider.label:tr('location'));
}
function updateConditional() {
  const hasDownload=effective.some(s=>bootstrap.download_clients.includes(s));
  $('no-torrent').hidden=hasDownload; $('vpn-controls').hidden=!hasDownload;
  $('vpn-fields').hidden=!$('vpn-enabled').checked;
  $('vpn-warning').hidden=$('vpn-enabled').checked;
  $('wireguard-fields').hidden=$('vpn-type').value!=='wireguard';$('openvpn-fields').hidden=$('vpn-type').value!=='openvpn';
  const hasQuality=effective.includes('recyclarr')&&effective.some(s=>['sonarr','radarr'].includes(s));
  $('no-quality').hidden=hasQuality;$('quality-controls').hidden=!hasQuality;
  for(const service of ['sonarr','radarr'])if($('quality-label-'+service))$('quality-label-'+service).hidden=!effective.includes(service);
}
function renderReview() {
  const target=$('review');target.replaceChildren();
  const grid=E('div',undefined,'summary-grid');
  for(const [label,value] of [[tr('projectName'),plan.project_name],[tr('vpn'),tr(plan.vpn?'vpnOn':'vpnOff')],[tr('dataRoot'),plan.data_root],[tr('configRoot'),plan.config_root]]) {const box=E('div',undefined,'summary-box');box.append(E('span',label),E('strong',value));grid.append(box);}target.append(grid);
  for(const s of plan.services){const row=E('div',undefined,'review-service'),left=E('div');left.append(E('strong',s.name),E('small',s.image));row.append(left,E('code',s.port?':'+s.port:'—'));target.append(row);}
  for(const [service,name] of Object.entries(plan.recyclarr_templates))target.append(E('p',`${tr('profile')} ${service} : ${name}`,'muted'));
  for(const warning of plan.warnings)target.append(E('p',warning,'notice warning'));
  if(plan.demo)target.append(E('p',tr('demoCheck'),'notice demo'));
  const checks=E('ul',undefined,'checks');
  for(const c of plan.checks){const li=E('li',undefined,'check');li.append(E('span',c.ok?'✓':c.blocking?'×':'!',c.ok?'ok':'fail'));const detail=E('div');detail.append(E('strong',c.name),E('small',c.detail));li.append(detail);checks.append(li);}target.append(checks);
  target.append(E('p',tr(plan.blocked?'blocked':'ready'),plan.blocked?'notice error':'muted'));
  $('confirm-label').hidden=plan.blocked;
}
async function validate() {
  readFields();plan=null;$('confirm').checked=false;setBusy(true);$('review').replaceChildren(E('p',tr('checking'),'notice'));
  try {plan=await api('/api/validate',form);displayGraph({graph:plan.graph,graph_results:{},status:'idle',demo:bootstrap.demo,deployed:false});renderReview();}catch(e){$('review').replaceChildren();error(e.message);}finally{setBusy(false);}
}
function renderProgress(data) {
  lastProgress=data;
  displayGraph(data);
  const complete=['done','partial','error'].includes(data.status);
  installed=data.status==='running'||complete;
  $('progress-state').textContent=tr(data.demo&&data.status==='done'?'demoDone':data.status);
  $('progress-state').className='progress-state '+(data.status==='running'?'running':'');
  $('progress-title').textContent=tr(data.demo&&data.status==='done'?'demoDone':complete?data.status:'progressTitle');
  if(data.demo&&complete)$('progress-description').textContent=tr('notInstalled');
  const recent=data.events.slice(-10);
  $('event-list').replaceChildren(...recent.map(event=>{const li=E('li');li.append(E('b',event.ok?'✓':'×',event.ok?'ok':'fail'));const text=E('div');text.append(E('span',event.phase),E('small',event.message));li.append(text);return li;}));
  $('logs').textContent=data.events.map(e=>`${e.ok?'OK':'ERREUR'} · ${e.phase} · ${e.message}`).join('\n');
  $('admin').hidden=!['done','partial'].includes(data.status);
  if(data.demo&&data.status==='done'&&!demoAdminOpened){demoAdminOpened=true;openAdmin();}
  $('retry').hidden=data.status!=='error';
  $('tui').hidden=true;
  return complete;
}
async function poll() {
  liveController?.abort(); liveController=new AbortController();
  const controller=liveController;
  try {
    const response=await fetch('/api/events',{headers:{Authorization:'Bearer '+token},signal:controller.signal});
    if(!response.ok||!response.body)throw new Error('stream');
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    while(true){
      const part=await reader.read();if(part.done)break;
      buffer+=decoder.decode(part.value,{stream:true});
      let boundary;
      while((boundary=buffer.indexOf('\n\n'))!==-1){
        const message=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
        if(!message.startsWith('data: '))continue;
        const data=JSON.parse(message.slice(6));error('');
        if(renderProgress(data)){await reader.cancel();return;}
      }
    }
  }catch(e){
    if(e.name==='AbortError')return;
    $('progress-state').textContent=tr('progressError');
    $('graph-status').textContent=GRAPH_LABELS[lang].disconnected;
    $('wiring-graph').classList.add('disconnected');
  }
  if(liveController===controller)polling=setTimeout(poll,750);
}
$('wizard').noValidate=true;
$('wizard').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;error('');
  try {
    if(step===0){if(!form.services.length)throw new Error(tr('noSelection'));setBusy(true);effective=(await api('/api/selection',{services:form.services})).services;setBusy(false);}
    if(step===1){for(const input of document.querySelectorAll('[data-step="1"] input'))if(!input.reportValidity())return;}
    if(step<4){readFields();showStep(step+1);if(step===4)await validate();return;}
    if(step===4&&plan?.plan_id&&$('confirm').checked){
      setBusy(true);
      if($('remember').checked&&!bootstrap.demo)await api('/api/preference',{interface:'web'});
      await api('/api/install',{plan_id:plan.plan_id,confirm:true});installed=true;showStep(5);poll();
    }
  }catch(e){error(e.message);}finally{setBusy(false);}
});
$('back').addEventListener('click',()=>{if(!busy){readFields();plan=null;showStep(Math.max(0,step-1));}});
$('recheck').addEventListener('click',()=>validate());
$('confirm').addEventListener('change',()=>setBusy(busy));
$('language').addEventListener('change',scheduleGraph);
$('vpn-enabled').addEventListener('change',scheduleGraph);
$('platform').addEventListener('change',()=>{if(!bootstrap.existing){const d=bootstrap.profiles[$('platform').value];$('data_root').value=d.data_root;$('config_root').value=d.config_root;}});
for(const id of ['vpn-enabled','vpn-type'])$(id).addEventListener('change',updateConditional);
$('vpn-provider').addEventListener('change',()=>{$('vpn-countries').value='';updatePlaces();});
$('ui-language').addEventListener('change',()=>{lang=$('ui-language').value;translate();});
async function loadTemplates(){
  if($('load-templates').disabled)return;
  $('load-templates').disabled=true;$('template-status').textContent=tr('checkingTemplates');
  try {const data=await api('/api/templates');if(data.problem)throw new Error(tr('noTemplates'));
    for(const service of ['sonarr','radarr']){const select=$('quality-'+service),old=select.value;select.replaceChildren(profileOption(service,''),...(data.names[service]||[]).map(n=>profileOption(service,n)));if(old&&!data.names[service]?.includes(old))select.append(profileOption(service,old));select.value=old;refreshProfileEstimate(service);}
    templatesLoaded=true;
    const counts=['sonarr','radarr'].filter(s=>effective.includes(s)).map(s=>s.charAt(0).toUpperCase()+s.slice(1)+' : '+(data.names[s]||[]).length).join(' · ');
    $('template-status').textContent=tr('templatesReady')+' '+counts+(data.bundled?' — '+tr('bundledProfiles'):'');
  }catch(e){$('template-status').textContent=e.message;}finally{$('load-templates').disabled=false;}
}
$('load-templates').addEventListener('click',loadTemplates);
$('tui').addEventListener('click',async()=>{try{await api('/api/tui',{});$('wizard').hidden=true;$('loading').hidden=false;$('loading').textContent=tr('switched');$('tui').hidden=true;}catch(e){error(e.message);}});
async function openAdmin(){
  if(adminOpening)return;
  adminOpening=true;
  let page=null;
  try{
    // Open synchronously on a button click, before awaiting the local API.
    // Automatic completion may be blocked; the native link remains usable.
    page=window.open('about:blank','_blank');
    if(page){page.opener=null;page.document.title='PlugArr — Administration';page.document.body.textContent=tr('adminWaiting');}
    adminUrl=adminUrl||(await api('/api/admin',{})).url;
    $('admin-link').href=adminUrl;$('admin-link').hidden=false;
    if(page&&!page.closed){page.location.replace(adminUrl);$('admin-notice').textContent=tr('adminOpened');}
    else{$('admin-notice').textContent=tr('adminBlocked');}
  }catch(e){if(page&&!page.closed)page.close();error(e.message);}
  finally{adminOpening=false;}
}
$('admin').addEventListener('click',openAdmin);
$('retry').addEventListener('click',async()=>{try{await api('/api/reload',{});installed=false;location.reload();}catch(e){error(e.message);}});
window.addEventListener('beforeunload',event=>{if(installed&&lastProgress?.status==='running'){event.preventDefault();event.returnValue='';}});
async function boot(){
  try{if(!token)throw new Error(tr('sessionMissing'));bootstrap=await api('/api/bootstrap');form=structuredClone(bootstrap.form);effective=(await api('/api/selection',{services:form.services})).services;lang=form.ui_language;$('ui-language').value=lang;
    $('demo-banner').hidden=!bootstrap.demo;$('existing-banner').hidden=!bootstrap.existing;$('tui').hidden=!bootstrap.can_tui;
    if(bootstrap.icons.plugarr){$('brand-icon').src=bootstrap.icons.plugarr;$('brand-icon').hidden=false;}
    fillFields();translate();$('loading').hidden=true;$('wizard').hidden=false;showStep(0);
    const progress=await api('/api/progress');if(progress.status!=='idle'){showStep(5);if(!renderProgress(progress))poll();}
  }catch(e){$('loading').hidden=true;error(e.message);}
}
boot();
