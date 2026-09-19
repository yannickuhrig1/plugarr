/* Shared remote-access step and mobile forms, including the offline HTML report. */
'use strict';
globalThis.PlugArrRemote = (() => {
  const $ = id => document.getElementById(id);
  const el = (tag, text) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; return n; };
  const ids=['sonarr','radarr','qbittorrent'];
  // Fiches du telephone : SABnzbd en plus, sans acces distant gere par PlugArr.
  const mobileIds=[...ids,'sabnzbd'];
  // Version 1 server-export schema observed in the user's Arr Control export.
  // Only service identifiers present in that sample are supported here.
  const arrServices={
    sonarr:{category:'library',notifications:['onGrab','onDownload','onUpgrade','onHealthIssue']},
    radarr:{category:'library',notifications:['onGrab','onDownload','onUpgrade','onHealthIssue']},
    prowlarr:{category:'indexers',notifications:['onHealthIssue','onApplicationUpdate']},
    seerr:{category:'requests',notifications:['pending','approved','available','failed']},
    qbittorrent:{category:'downloads',notifications:[]},
  };
  let bootstrap, form, request, renderReport, language=()=>document.documentElement.lang;
  let current, selected=[], effective=[], pollTimer, mounted=false;
  const text = (fr,en) => language()==='en'?en:fr;
  const english = {
    remoteTitle:'Your applications, wherever you are.',remoteIntro:'Choose your access. Activate the gateway after installation without blocking local use.',
    remoteLocal:'At home only',remoteLocalHelp:'Use your applications on your local network.',
    remoteTailscale:'Private access with Tailscale',remoteTailscaleHelp:'No domain required. Connect Tailscale on your devices too.',
    remoteHttps:'With my domain name',remoteHttpsHelp:'HTTPS addresses. Requires a domain and a reachable inbound connection.',
    remoteDomain:'Your domain',remoteDomainHelp:'Domain only, without https://. One subdomain per application.',
    remoteDnsHelp:'Point subdomains at your public connection and forward ports 80 and 443 to the server. A certificate does not bypass CGNAT.',
    remoteHeading:'Remote access',remoteConfirm:'I authorize the chosen gateway configuration and access to the selected applications.',
    remoteActivate:'Activate remote access',remoteAssociate:'Connect my Tailscale account',remoteRefresh:'Refresh status',
    mobileTitle:'Set up my phone',mobileIntro:'Select your app and copy the fields. A check from the server does not replace a phone test.',
    mobileClient:'Mobile app',mobileConnection:'Connection',
  };
  function mode(){return document.querySelector('input[name="remote-mode"]:checked')?.value||'local';}
  function refresh(services=effective){
    effective=services;
    if(!$('remote-domain-box'))return;
    $('remote-domain-box').hidden=mode()!=='https';
    $('remote-tail-help').hidden=mode()!=='tailscale';
    $('remote-tail-help').textContent=bootstrap?.demo?text('Association simulée à la fin de la démonstration.','Account association is simulated at the end of this demo.'):text('Sur Linux, PlugArr prépare Tailscale et propose le lien de connexion à la fin. Sur Windows, installez et connectez Tailscale sur ce PC. Le réseau privé peut donner accès aux autres ports du serveur selon vos règles Tailscale.','On Linux, PlugArr prepares Tailscale and provides the login link after installation. On Windows, install and connect Tailscale on this PC. Your tailnet policy may also allow access to other server ports.');
    $('remote-services').replaceChildren();
    for(const sid of ids.filter(s=>effective.includes(s))){
      const label=el('label'),input=el('input');label.className='inline-choice';input.type='checkbox';input.checked=selected.includes(sid);input.value=sid;
      input.addEventListener('change',()=>{selected=input.checked?[...new Set([...selected,sid])]:selected.filter(s=>s!==sid);});
      label.append(input,el('span',`${sid} · https://${sid==='qbittorrent'?'qb':sid}.${$('remote-domain').value.trim()||text('votre-domaine.fr','your-domain.com')}`));$('remote-services').append(label);
    }
    $('remote-step-summary').textContent=mode()==='local'?text('Vous pourrez configurer un accès distant lors d’une prochaine installation.','You can configure remote access during a later installation.'):text('Les adresses et fiches mobiles seront disponibles à la fin. L’activation distante est une opération séparée.','Addresses and mobile forms will appear after installation. Remote activation is a separate operation.');
  }
  function read(services=effective){return {mode:mode(),domain:mode()==='https'?$('remote-domain').value.trim():'',services:mode()==='https'?selected.filter(s=>services.includes(s)):[]};}
  function valid(){
    $('remote-domain').setCustomValidity('');
    if(mode()==='https'){
      const value=$('remote-domain').value.trim();
      if(!/^[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\.?$/.test(value)||!selected.some(s=>effective.includes(s))) {
        $('remote-domain').setCustomValidity(text('Indiquez un domaine seul et choisissez au moins une application.','Enter a domain only and select at least one application.'));
        $('remote-domain').reportValidity();return false;
      }
    }
    return true;
  }
  async function action(action){
    $('remote-activate').disabled=true;$('remote-refresh').disabled=true;
    try {await request('/api/remote',{action,confirm:$('remote-confirm').checked});await update();}
    catch(e){$('remote-status').textContent=e.message;$('remote-refresh').disabled=false;$('remote-activate').disabled=!$('remote-confirm').checked;}
  }
  async function update(){
    clearTimeout(pollTimer);
    try {renderReport(await request('/api/report'));}
    catch(e){$('remote-status').textContent=e.message;$('remote-refresh').disabled=false;}
  }
  function init(boot,fields,api,render,getLanguage){
    bootstrap=boot;form=fields;request=api;renderReport=render;language=getLanguage;
    const remote=form.remote_access||{mode:'local',domain:'',services:[]};selected=[...remote.services];
    document.querySelectorAll('input[name="remote-mode"]').forEach(n=>{n.checked=n.value===remote.mode;n.addEventListener('change',()=>{if(mode()==='https'&&!selected.length)selected=ids.filter(s=>effective.includes(s));refresh();});});
    $('remote-domain').value=remote.domain||'';
    $('remote-domain').addEventListener('input',()=>{$('remote-domain').setCustomValidity('');refresh();});
    $('remote-confirm').addEventListener('change',()=>$('remote-activate').disabled=!$('remote-confirm').checked);
    $('remote-activate').addEventListener('click',()=>action('activate'));
    $('remote-refresh').addEventListener('click',()=>action('inspect'));
    const disable=el('button',text('Désactiver la passerelle PlugArr','Disable the PlugArr gateway'));disable.id='remote-disable';disable.type='button';disable.className='secondary';disable.hidden=true;disable.addEventListener('click',()=>{if($('remote-confirm').checked)action('deactivate');else $('remote-status').textContent=text('Cochez la confirmation avant de désactiver la passerelle.','Check the confirmation before disabling the gateway.');});$('remote-refresh').parentElement.append(disable);
    mountMobile();refresh(fields.services);
  }
  function report(data){
    current=data;
    if($('remote-result')){
      const remote=data.remote||{mode:'local',message:'',status:'local'};
      $('remote-result').hidden=remote.mode==='local'&&!data.remote_managed;
      $('remote-status').textContent=(data.demo?text('Démonstration : ','Demo: '):'')+remote.message;
      $('remote-activate').disabled=remote.status==='running'||!$('remote-confirm').checked;
      $('remote-refresh').disabled=remote.status==='running';
      $('remote-activate').hidden=remote.mode==='local';
      if($('remote-disable')){$('remote-disable').hidden=!data.remote_managed;$('remote-disable').disabled=remote.status==='running';}
      if(remote.mode==='local'&&data.remote_managed&&remote.status!=='disabled')$('remote-status').textContent=text('Une passerelle PlugArr existe encore. Désactivez-la ici pour fermer cet accès distant.','A PlugArr gateway still exists. Disable it here to close that remote access.');
      $('remote-auth').hidden=true;
      if(remote.auth_url){try{const u=new URL(remote.auth_url);if(u.protocol==='https:'&&u.hostname==='login.tailscale.com'){$('remote-auth').href=u.href;$('remote-auth').hidden=false;}}catch{}}
      $('remote-links').replaceChildren();
      for(const service of data.services.filter(s=>s.remote_url)){
        const row=el('p');row.append(el('strong',service.name+' : '));
        if(data.demo)row.append(el('code',service.remote_url));
        else {const link=el('a',service.remote_url);link.href=service.remote_url;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
        $('remote-links').append(row);
      }
      clearTimeout(pollTimer);if(remote.status==='running')pollTimer=setTimeout(update,2500);
    }
    mobile();
  }
  async function copy(value){
    try {await navigator.clipboard.writeText(value);$('mobile-copy-status').textContent=text('Copié.','Copied.');}
    catch {const area=el('textarea');area.value=value;document.body.append(area);area.select();let done=false;try{done=document.execCommand('copy');}catch{}area.remove();$('mobile-copy-status').textContent=done?text('Copié.','Copied.'):text('Sélectionnez le champ puis copiez-le manuellement.','Select the field and copy it manually.');}
  }
  function field(label,value,secret=false){
    const row=el('div');row.className='mobile-field';const title=el('label',label),input=el('input');input.readOnly=true;input.value=value;input.type=secret?'password':'text';input.setAttribute('aria-label',label);title.append(input);row.append(title);
    if(secret){const show=el('button',text('Afficher','Show'));show.type='button';show.className='secondary';show.addEventListener('click',()=>{input.type=input.type==='password'?'text':'password';show.textContent=input.type==='password'?text('Afficher','Show'):text('Masquer','Hide');});row.append(show);}
    const button=el('button',text('Copier','Copy'));button.type='button';button.className='secondary';button.addEventListener('click',()=>copy(value));row.append(button);return row;
  }
  function mountMobile(data){
    if(!mounted){
      const option=el('option','Arr Control');option.value='arrcontrol';$('mobile-client').append(option);
      const box=el('section');box.id='arr-export';box.className='mobile-export';box.hidden=true;
      const label=el('label',text('Profil à restaurer dans Arr Control','Profile to restore in Arr Control'));
      const select=el('select');select.id='arr-export-network';
      for(const [value,fr,en] of [['local','Réseau local','Local network'],['remote','À distance','Remote']]){const o=el('option',text(fr,en));o.value=value;select.append(o);}
      label.append(select);box.append(label);
      const notice=el('p');notice.id='arr-export-notice';notice.className='notice';box.append(notice);
      const button=el('button',text('Télécharger pour Arr Control','Download for Arr Control'));button.id='arr-export-download';button.type='button';button.className='primary';
      button.addEventListener('click',downloadArrControl);select.addEventListener('change',renderArrExport);box.append(button);
      const help=el('p',text('Dans Arr Control, utilisez l’import/restauration de serveur avec ce JSON. Sauvegardez vos réglages actuels avant l’import. Ce fichier contient vos secrets : gardez-le privé. Compatibilité à confirmer sur téléphone.','In Arr Control, import/restore this JSON server file. Back up existing settings first. This file contains your secrets: keep it private. Compatibility still needs phone validation.'));box.append(help);
      $('mobile-fields').after(box);
      const nzbBox=el('section');nzbBox.id='nzb-export';nzbBox.className='mobile-export';
      const nzbLabel=el('label',text('Profil nzb360 24.4.1','nzb360 24.4.1 profile'));
      const nzbSelect=select.cloneNode(true);nzbSelect.id='nzb-export-network';nzbLabel.append(nzbSelect);nzbBox.append(nzbLabel);
      const nzbSsidLabel=el('label',text('Nom du Wi-Fi de la maison (facultatif) : un seul fichier, nzb360 bascule alors sur les adresses locales','Home Wi-Fi name (optional): one file, nzb360 then switches to local addresses'));
      nzbSsidLabel.id='nzb-export-ssid-label';const nzbSsid=el('input');nzbSsid.id='nzb-export-ssid';nzbSsid.maxLength=32;nzbSsid.autocomplete='off';nzbSsid.spellcheck=false;
      nzbSsid.addEventListener('input',renderNzbExport);nzbSsidLabel.append(nzbSsid);nzbBox.append(nzbSsidLabel);
      const nzbNotice=el('p');nzbNotice.id='nzb-export-notice';nzbNotice.className='notice';nzbBox.append(nzbNotice);
      const consent=el('label');consent.className='inline-choice';const check=el('input');check.type='checkbox';check.id='nzb-export-confirm';
      consent.append(check,el('span',text('J’ai sauvegardé mes réglages nzb360. La restauration de ce ZIP remplace tous mes réglages nzb360, y compris les services qui n’y figurent pas.','I backed up my nzb360 settings. Restoring this ZIP replaces all my nzb360 settings, including services it does not contain.')));nzbBox.append(consent);
      const nzbButton=el('button',text('Télécharger pour nzb360','Download for nzb360'));nzbButton.id='nzb-export-download';nzbButton.type='button';nzbButton.className='primary';nzbButton.disabled=true;
      nzbButton.addEventListener('click',downloadNzb360);check.addEventListener('change',renderNzbExport);
      nzbSelect.addEventListener('change',()=>{check.checked=false;renderNzbExport();});nzbBox.append(nzbButton);
      nzbBox.append(el('p',text('Dans nzb360 24.4.1, utilisez Sauvegarde / Restauration avec ce ZIP. Testez de préférence dans une installation séparée. Secrets non chiffrés : ne partagez pas ce fichier. Aucun achat ni licence n’est inclus.','In nzb360 24.4.1, use Backup / Restore with this ZIP. Prefer a separate test installation. Unencrypted secrets: do not share this file. No purchases or licenses are included.')));
      box.after(nzbBox);
      const qbBox=el('section');qbBox.id='qb-export';qbBox.className='mobile-export';qbBox.hidden=true;
      const qbLabel=el('label',text('Profil qbRemote 1.8.0','qbRemote 1.8.0 profile'));
      const qbSelect=select.cloneNode(true);qbSelect.id='qb-export-network';qbLabel.append(qbSelect);qbBox.append(qbLabel);
      const ssidLabel=el('label',text('Nom du Wi-Fi de la maison (facultatif) : qbRemote bascule alors seul sur l’adresse locale','Home Wi-Fi name (optional): qbRemote then switches to the local address by itself'));
      ssidLabel.id='qb-export-ssid-label';const ssid=el('input');ssid.id='qb-export-ssid';ssid.maxLength=32;ssid.autocomplete='off';ssid.spellcheck=false;ssidLabel.append(ssid);qbBox.append(ssidLabel);
      const passwordLabel=el('label',text('Mot de passe du fichier (demandé par qbRemote à la restauration)','File password (qbRemote asks for it when restoring)'));
      const password=el('input');password.id='qb-export-password';password.type='password';password.autocomplete='new-password';password.maxLength=128;passwordLabel.append(password);qbBox.append(passwordLabel);
      const qbNotice=el('p');qbNotice.id='qb-export-notice';qbNotice.className='notice';qbBox.append(qbNotice);
      const qbConsent=el('label');qbConsent.className='inline-choice';const qbCheck=el('input');qbCheck.type='checkbox';qbCheck.id='qb-export-confirm';
      qbConsent.append(qbCheck,el('span',text('J’ai sauvegardé mes réglages qbRemote. La restauration de ce fichier remplace tous mes serveurs qbRemote ; les préférences d’affichage restent.','I backed up my qbRemote settings. Restoring this file replaces all my qbRemote servers; display preferences stay.')));qbBox.append(qbConsent);
      const qbButton=el('button',text('Télécharger pour qbRemote','Download for qbRemote'));qbButton.id='qb-export-download';qbButton.type='button';qbButton.className='primary';qbButton.disabled=true;
      qbButton.addEventListener('click',downloadQbRemote);qbBox.append(qbButton);
      qbSelect.addEventListener('change',()=>{qbCheck.checked=false;renderQbExport();});
      for(const input of [ssid,password])input.addEventListener('input',renderQbExport);qbCheck.addEventListener('change',renderQbExport);
      qbBox.append(el('p',text('Dans qbRemote 1.8.0, restaurez ce fichier depuis la fonction de sauvegarde, avec le mot de passe choisi ici. Seul le serveur qBittorrent est inclus : vos préférences d’affichage ne sont pas touchées. Le fichier est chiffré, mais gardez-le privé.','In qbRemote 1.8.0, restore this file from the backup feature with the password chosen here. Only the qBittorrent server is included: display preferences are untouched. The file is encrypted, but keep it private.')));
      nzbBox.after(qbBox);
      for(const id of ['mobile-client','mobile-service','mobile-network'])$(id).addEventListener('change',mobile);mounted=true;
    }
    if(data){current=data;mobile();}
  }
  function buildArrControlExport(data,network='local',now=Date.now()){
    if(!['local','remote'].includes(network))throw new Error('Unknown export network');
    const services=[], omitted=[];
    const present=value=>typeof value==='string'&&value.length>0&&value!=='-';
    for(const service of data.services){
      const spec=Object.hasOwn(arrServices,service.id)?arrServices[service.id]:null;if(!spec)continue;
      const address=network==='remote'?service.remote_url:(service.local_url||service.url);
      let url;try{url=new URL(address);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error();}catch{omitted.push(service.name);continue;}
      const qb=service.id==='qbittorrent';
      if(qb?(!present(service.username)||!present(service.password)):!present(service.api_key)){omitted.push(service.name);continue;}
      const fields=qb?{username:service.username,password:service.password,localUrl:address}:{apiKey:service.api_key,localUrl:address};
      services.push({categoryId:spec.category,serviceId:service.id,name:service.name,url:address,
        apiKey:qb?null:service.api_key,
        // A fixed-network profile uses the sample's proven localUrl schema.
        // No guess about Arr Control's unverified remote-switching behaviour.
        config:{fields,remoteAccess:false,remoteUrl:'',secureHeaders:false,headerType:'custom',headers:[],networkMode:'auto',retryRemoteOnAuthError:false,
          notifications:Object.fromEntries(spec.notifications.map(key=>[key,true]))}});
    }
    return {payload:{version:1,exportedAt:now,server:`PlugArr${data.demo?' DEMO':''} (${network==='remote'?'remote':'local'})`,services},omitted};
  }
  function renderArrExport(){
    const box=$('arr-export');if(!box)return;
    box.hidden=$('mobile-client').value!=='arrcontrol';if(box.hidden||!current)return;
    const {payload,omitted}=buildArrControlExport(current,$('arr-export-network').value);
    $('arr-export-download').disabled=payload.services.length===0;
    let message=text(`${payload.services.length} application(s) incluse(s). Le fichier contient toutes les applications compatibles de ce profil, pas seulement la fiche affichée.`,`${payload.services.length} service(s) included. The file includes all compatible services in this profile, not just the displayed form.`);
    if(omitted.length)message+=' '+text('Non incluses (adresse ou identifiants indisponibles) : ','Not included (address or credentials unavailable): ')+omitted.join(', ')+'.';
    message+=' '+text('Un profil utilise un seul réseau, sans bascule automatique.','A profile uses one network, without automatic switching.');
    if(current.demo)message+=' '+text('DÉMONSTRATION : accès fictifs uniquement.','DEMO: fictitious connections only.');
    if($('arr-export-network').value==='remote')message+=' '+text('Vérifiez l’accès distant sur le téléphone. Avec Tailscale, connectez aussi le téléphone.','Verify remote access on your phone. With Tailscale, connect the phone too.');
    $('arr-export-notice').textContent=message;
  }
  function downloadArrControl(){
    if(!current)return;
    const network=$('arr-export-network').value,{payload}=buildArrControlExport(current,network);
    if(!payload.services.length)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
    const link=el('a');link.href=url;link.download=`plugarr${current.demo?'-demo':''}-arr-control-${network}.json`;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  // Java Object Serialization stream: bounded String/Boolean HashMap writer.
  // Class descriptors/UIDs match the inspected 24.4.1 export, not user values.
  function javaPreferences(preferences){
    const out=[];
    const be=(value,n)=>{for(let i=n-1;i>=0;i--)out.push((value>>> (i*8))&255);};
    const utf=value=>{
      const bytes=[];
      for(let i=0;i<value.length;i++){
        const c=value.charCodeAt(i);
        if(c>=1&&c<=127)bytes.push(c);
        else if(c<=2047)bytes.push(192|(c>>6),128|(c&63));
        else bytes.push(224|(c>>12),128|((c>>6)&63),128|(c&63));
      }
      if(bytes.length>65535)throw new Error('nzb360: champ trop long / field too long');
      be(bytes.length,2);for(const b of bytes)out.push(b);
    };
    const desc=(name,uid,flags,fields)=>{
      out.push(0x72);utf(name);for(let i=0;i<16;i+=2)out.push(parseInt(uid.slice(i,i+2),16));
      out.push(flags);be(fields.length,2);
      for(const [type,name] of fields){out.push(type.charCodeAt(0));utf(name);}
      out.push(0x78,0x70);
    };
    const entries=Object.entries(preferences);if(entries.length>256)throw new Error('Too many preferences');
    out.push(0xac,0xed,0,5,0x73);
    desc('java.util.HashMap','0507dac1c31660d1',3,[['F','loadFactor'],['I','threshold']]);
    let capacity=16;while(capacity*0.75<entries.length)capacity*=2;
    out.push(0x3f,0x40,0,0);be(Math.floor(capacity*0.75),4);
    out.push(0x77,8);be(capacity,4);be(entries.length,4);
    for(const [key,value] of entries){
      out.push(0x74);utf(key);
      if(typeof value==='string'){out.push(0x74);utf(value);}
      else if(typeof value==='boolean'){
        out.push(0x73);desc('java.lang.Boolean','cd207280d59cfaee',2,[['Z','value']]);out.push(value?1:0);
      }else throw new Error('Unsupported preference type');
    }
    out.push(0x78);return Uint8Array.from(out);
  }
  function crc32(data){
    let crc=0xffffffff;for(const b of data){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;
  }
  // PKZIP stored entries, CRC-32, central directory. Works offline without a CDN.
  function zipStored(files){
    const out=[],central=[];
    const le=(target,value,n)=>{for(let i=0;i<n;i++)target.push((value>>>(i*8))&255);};
    const put=(target,bytes)=>{for(const b of bytes)target.push(b);};
    for(const [name,data] of files){
      const filename=Array.from(name,c=>c.charCodeAt(0)),offset=out.length;
      const crc=crc32(data);
      le(out,0x04034b50,4);for(const v of [20,0,0,0,33])le(out,v,2);
      for(const v of [crc,data.length,data.length])le(out,v,4);le(out,filename.length,2);le(out,0,2);put(out,filename);put(out,data);
      le(central,0x02014b50,4);for(const v of [20,20,0,0,0,33])le(central,v,2);
      for(const v of [crc,data.length,data.length])le(central,v,4);
      for(const v of [filename.length,0,0,0,0])le(central,v,2);
      le(central,0,4);le(central,offset,4);put(central,filename);
    }
    const start=out.length;put(out,central);le(out,0x06054b50,4);
    for(const v of [0,0,files.length,files.length])le(out,v,2);
    le(out,central.length,4);le(out,start,4);le(out,0,2);return Uint8Array.from(out);
  }
  // nzb360 keys observed in the 24.4.1 sample. Each service has a primary
  // address, a local address and a Wi-Fi name (SSID): with the three filled,
  // one file serves both at home and away. The sample left the local fields
  // empty, so the switch itself remains to be confirmed on a phone.
  // SABnzbd has no `sabnzbd_server_enabled_preference` in the sample: nzb360
  // started as a SABnzbd client, and its generic `server_enabled_preference`
  // and `server_SSID_preference` are taken to be SABnzbd's (inferred).
  function buildNzb360Export(data,network='local',ssid=''){
    const {payload,omitted}=buildArrControlExport({...data,services:data.services.filter(s=>ids.includes(s.id))},network);
    const home=network==='remote'&&ssid?ssid:'';
    const localAddress=id=>{
      const service=data.services.find(s=>s.id===id);
      try{const url=new URL(service.local_url||service.url);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url.href.replace(/\/$/,''):'';}catch{return '';}
    };
    const preferences={version:'24.4.1',nzbdrone_server_enabled_preference:false,radarr_server_enabled_preference:false,torrent_server_enabled_preference:false,server_enabled_preference:false};
    let switching=0;
    for(const service of payload.services){
      const prefix={sonarr:'nzbdrone',radarr:'radarr',qbittorrent:'torrent'}[service.serviceId];
      const local=home?localAddress(service.serviceId):'';
      if(local)switching++;
      preferences[`${prefix}_server_enabled_preference`]=true;
      preferences[`${prefix}_server_primary_connectionstring_preference`]=service.url;
      preferences[`${prefix}_server_local_connectionstring_preference`]=local;
      preferences[`${prefix}_server_SSID_preference`]=local?home:'';
      // Without this switch nzb360 keeps the addresses but never uses the local
      // one. Key names read from a 24.4.1 backup made with the switch enabled.
      preferences[`${prefix}_localconnectionswitch_preference`]=Boolean(local);
      if(service.serviceId==='qbittorrent'){
        preferences.torrent_client_preference='qbittorrent';
        preferences.torrent_username=service.config.fields.username;preferences.torrent_password=service.config.fields.password;
        preferences.torrent_rpc_path='';
      }else preferences[`${prefix}_apikey_preference`]=service.apiKey;
    }
    let count=payload.services.length;
    const sab=data.services.find(s=>s.id==='sabnzbd');
    if(sab){
      let address='';
      try{const url=new URL(network==='remote'?sab.remote_url:(sab.local_url||sab.url));if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password)address=url.href.replace(/\/$/,'');}catch{}
      const key=typeof sab.api_key==='string'&&sab.api_key!=='-'?sab.api_key:'';
      if(address&&key){
        const local=home?localAddress('sabnzbd'):'';
        if(local)switching++;
        preferences.server_enabled_preference=true;
        preferences.sabnzbd_server_primary_connectionstring_preference=address;
        preferences.sabnzbd_server_local_connectionstring_preference=local;
        preferences.server_SSID_preference=local?home:'';
        preferences.sabapi_preference=key;
        count++;
      }else omitted.push(sab.name);
    }
    const files=[['com.kevinforeman.nzb360_preferences.xml',javaPreferences(preferences)],
      ['nzb360prefs.xml',javaPreferences({version:'24.4.1'})],['servers.xml',javaPreferences({})]];
    return {bytes:zipStored(files),count,omitted,switching};
  }
  function renderNzbExport(){
    const box=$('nzb-export');if(!box)return;
    box.hidden=$('mobile-client').value!=='nzb360';if(box.hidden||!current)return;
    try{
      const remote=current.services.some(s=>ids.includes(s.id)&&s.remote_url);
      $('nzb-export-network').querySelector('option[value="remote"]').disabled=!remote;
      if(!remote)$('nzb-export-network').value='local';
      const distant=$('nzb-export-network').value==='remote';
      $('nzb-export-ssid-label').hidden=!distant;
      const result=buildNzb360Export(current,$('nzb-export-network').value,distant?$('nzb-export-ssid').value.trim():'');
      $('nzb-export-download').disabled=!result.count||!$('nzb-export-confirm').checked;
      const switching=result.switching
        ?text(` Sur le Wi-Fi « ${$('nzb-export-ssid').value.trim()} », ${result.switching} application(s) passent sur l’adresse locale. Autorisez la localisation quand nzb360 la demande : Android en a besoin pour lire le nom du Wi-Fi.`,` On Wi-Fi "${$('nzb-export-ssid').value.trim()}", ${result.switching} service(s) switch to the local address. Allow location when nzb360 asks: Android needs it to read the Wi-Fi name.`)
        :(distant?text(' Sans nom de Wi-Fi, ce profil utilise toujours l’adresse distante.',' Without a Wi-Fi name, this profile always uses the remote address.'):'');
      $('nzb-export-notice').textContent=text(`nzb360 24.4.1 : ${result.count} application(s) parmi Sonarr, Radarr, qBittorrent et SABnzbd (SABnzbd encore expérimental).`, `nzb360 24.4.1: ${result.count} service(s) among Sonarr, Radarr, qBittorrent and SABnzbd (SABnzbd still experimental).`)
        +switching
        +(result.omitted.length?' '+text('Exclues (adresse ou identifiants indisponibles pour ce réseau) : ','Excluded (address or credentials unavailable for this network): ')+result.omitted.join(', ')+'.':'')
        +(current.demo?' '+text('DÉMONSTRATION : accès fictifs.','DEMO: fictitious connections.'):'')
        +($('nzb-export-network').value==='remote'&&current.remote?.mode==='tailscale'?' '+text('Avec Tailscale, connectez aussi le téléphone.','With Tailscale, connect the phone too.'):'');
    }catch{ $('nzb-export-download').disabled=true;$('nzb-export-notice').textContent=text('Export impossible : un champ dépasse la taille prise en charge.','Export unavailable: a field exceeds the supported size.'); }
  }
  function downloadNzb360(){
    if(!current||!$('nzb-export-confirm').checked)return;
    try{
      const network=$('nzb-export-network').value,result=buildNzb360Export(current,network,network==='remote'?$('nzb-export-ssid').value.trim():'');if(!result.count)return;
      const url=URL.createObjectURL(new Blob([result.bytes],{type:'application/zip'}));
      const link=el('a');link.href=url;link.download=`plugarr${current.demo?'-demo':''}-nzb360-24.4.1-${network}.zip`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch{renderNzbExport();}
  }
  // qbRemote 1.8.0 backup, schema observed in a backup made by the app itself:
  // WinZip AES-256 (AE-1) ZIP holding JSON files. Only manifest.json and
  // servers.json are written, so the app's display preferences are not imposed.
  const QB_APP_VERSION='1.8.0(73)';
  function buildQbRemoteServer(data,network='local',ssid=''){
    if(!['local','remote'].includes(network))throw new Error('Unknown export network');
    const service=data.services.find(s=>s.id==='qbittorrent');
    const present=value=>typeof value==='string'&&value.length>0&&value!=='-';
    if(!service||!present(service.username)||!present(service.password))return null;
    const parse=address=>{try{const url=new URL(address);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url:null;}catch{return null;}};
    const main=parse(network==='remote'?service.remote_url:(service.local_url||service.url));
    if(!main)return null;
    // The home Wi-Fi name lets qbRemote switch to the local address by itself.
    const local=network==='remote'&&ssid?parse(service.local_url||service.url):null;
    const port=url=>url.port||(url.protocol==='https:'?'443':'80');
    const path=url=>url.pathname&&url.pathname!=='/'?url.pathname:null;
    return {id:1,name:`PlugArr${data.demo?' DEMO':''}`,scheme:main.protocol.slice(0,-1),host:main.hostname,port:port(main),path:path(main),trustCertificates:false,
      username:service.username,password:service.password,customHeaders:null,
      localSsid:local?ssid:null,localScheme:local?local.protocol.slice(0,-1):null,localHost:local?local.hostname:null,localPort:local?port(local):null,localPath:local?path(local):null,
      localTrustCertificates:local?false:null,localDisableAuthentication:null,apiKey:null,basicAuthEnabled:null,basicAuthUsername:null,basicAuthPassword:null,
      macAddress:null,wolBroadcastAddress:null,wolPort:null,notifyOnComplete:null,apiVersion:null,networkStackOverride:'inherit',
      defaultTls:{trustMode:'system'},localTls:{trustMode:'system'},clientIdentity:{type:'none'}};
  }
  // WinZip AES (AE-1, AES-256): PBKDF2-HMAC-SHA1 x1000, AES-CTR with a
  // little-endian counter starting at 1, HMAC-SHA1 truncated to 10 bytes.
  // Headers copy those of the qbRemote sample: version 20, flags 0x801.
  async function zipAes(files,password,now=new Date()){
    const subtle=globalThis.crypto&&globalThis.crypto.subtle;
    if(!subtle||typeof CompressionStream!=='function')throw new Error('Browser cannot encrypt');
    const encoder=new TextEncoder(),out=[],central=[];
    const le=(target,value,n)=>{for(let i=0;i<n;i++)target.push((value>>>(i*8))&255);};
    const put=(target,bytes)=>{for(const b of bytes)target.push(b);};
    const time=(now.getHours()<<11)|(now.getMinutes()<<5)|(now.getSeconds()>>1);
    const date=((now.getFullYear()-1980)<<9)|((now.getMonth()+1)<<5)|now.getDate();
    const extra=[0x01,0x99,0x07,0x00,0x01,0x00,0x41,0x45,0x03,0x08,0x00];
    const base=await subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveBits']);
    for(const [name,content] of files){
      const plain=encoder.encode(content),filename=encoder.encode(name),offset=out.length;
      const compressed=new Uint8Array(await new Response(new Blob([plain]).stream().pipeThrough(new CompressionStream('deflate-raw'))).arrayBuffer());
      const salt=globalThis.crypto.getRandomValues(new Uint8Array(16));
      const bits=new Uint8Array(await subtle.deriveBits({name:'PBKDF2',hash:'SHA-1',salt,iterations:1000},base,66*8));
      const aesKey=await subtle.importKey('raw',bits.slice(0,32),'AES-CTR',false,['encrypt']);
      const macKey=await subtle.importKey('raw',bits.slice(32,64),{name:'HMAC',hash:'SHA-1'},false,['sign']);
      const cipher=new Uint8Array(compressed.length);
      for(let start=0,block=1;start<compressed.length;start+=16,block++){
        const counter=new Uint8Array(16);for(let i=0,n=block;n>0;i++,n=Math.floor(n/256))counter[i]=n&255;
        cipher.set(new Uint8Array(await subtle.encrypt({name:'AES-CTR',counter,length:128},aesKey,compressed.subarray(start,start+16))),start);
      }
      const mac=new Uint8Array(await subtle.sign('HMAC',macKey,cipher)).subarray(0,10);
      const size=16+2+cipher.length+10,crc=crc32(plain);
      le(out,0x04034b50,4);for(const v of [20,0x801,99,time,date])le(out,v,2);
      for(const v of [crc,size,plain.length])le(out,v,4);le(out,filename.length,2);le(out,extra.length,2);
      put(out,filename);put(out,extra);put(out,salt);put(out,bits.subarray(64,66));put(out,cipher);put(out,mac);
      le(central,0x02014b50,4);for(const v of [20,20,0x801,99,time,date])le(central,v,2);
      for(const v of [crc,size,plain.length])le(central,v,4);
      for(const v of [filename.length,extra.length,0,0,0])le(central,v,2);
      le(central,0x01a40000,4);le(central,offset,4);put(central,filename);put(central,extra);
    }
    const start=out.length;put(out,central);le(out,0x06054b50,4);
    for(const v of [0,0,files.length,files.length])le(out,v,2);
    le(out,central.length,4);le(out,start,4);le(out,0,2);return Uint8Array.from(out);
  }
  async function buildQbRemoteExport(data,network,ssid,password,now=new Date()){
    const server=buildQbRemoteServer(data,network,ssid);
    if(!server)return null;
    const manifest={version:1,createdAt:now.toISOString(),appVersion:QB_APP_VERSION};
    return zipAes([['manifest.json',JSON.stringify(manifest)],['servers.json',JSON.stringify([server])]],password,now);
  }
  const QB_PASSWORD_MIN=4;
  function renderQbExport(){
    const box=$('qb-export');if(!box)return;
    box.hidden=$('mobile-client').value!=='qbremote';if(box.hidden||!current)return;
    const network=$('qb-export-network').value,service=current.services.find(s=>s.id==='qbittorrent');
    $('qb-export-network').querySelector('option[value="remote"]').disabled=!(service&&service.remote_url);
    if(network==='remote'&&!(service&&service.remote_url))$('qb-export-network').value='local';
    $('qb-export-ssid-label').hidden=$('qb-export-network').value!=='remote';
    const server=buildQbRemoteServer(current,$('qb-export-network').value,$('qb-export-ssid').value.trim());
    const password=$('qb-export-password').value;
    $('qb-export-download').disabled=!server||!$('qb-export-confirm').checked||password.length<QB_PASSWORD_MIN;
    let message=server
      ?text(`qbRemote 1.8.0 : serveur « ${server.name} » vers ${server.scheme}://${server.host}:${server.port}.`,`qbRemote 1.8.0: server "${server.name}" at ${server.scheme}://${server.host}:${server.port}.`)
      :text('Export impossible : adresse ou identifiants de qBittorrent indisponibles pour ce réseau.','Export unavailable: qBittorrent address or credentials missing for this network.');
    if(server&&server.localHost)message+=' '+text(`Sur le Wi-Fi « ${server.localSsid} », qbRemote utilisera ${server.localScheme}://${server.localHost}:${server.localPort}. Après la restauration, ouvrez une fois Paramètres > Serveurs > ${server.name} > Réseau local pour autoriser la localisation : sans elle, Android ne donne pas le nom du Wi-Fi.`,`On Wi-Fi "${server.localSsid}", qbRemote will use ${server.localScheme}://${server.localHost}:${server.localPort}. After restoring, open Settings > Servers > ${server.name} > Local network once to allow location: without it, Android does not expose the Wi-Fi name.`);
    if(server&&password.length<QB_PASSWORD_MIN)message+=' '+text(`Choisissez un mot de passe d’au moins ${QB_PASSWORD_MIN} caractères : qbRemote le demandera à la restauration.`,`Choose a password of at least ${QB_PASSWORD_MIN} characters: qbRemote asks for it when restoring.`);
    if(current.demo)message+=' '+text('DÉMONSTRATION : accès fictifs.','DEMO: fictitious connections.');
    $('qb-export-notice').textContent=message;
  }
  async function downloadQbRemote(){
    if(!current||$('qb-export-download').disabled)return;
    const network=$('qb-export-network').value;
    $('qb-export-download').disabled=true;
    try{
      const bytes=await buildQbRemoteExport(current,network,$('qb-export-ssid').value.trim(),$('qb-export-password').value);
      if(!bytes)return;
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));
      const link=el('a');link.href=url;link.download=`qbRemote_plugarr${current.demo?'-demo':''}-${network}.backup.zip`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch{$('qb-export-notice').textContent=text('Ce navigateur ne sait pas chiffrer le fichier. Ouvrez la page dans Chrome, Edge ou Firefox récents.','This browser cannot encrypt the file. Open the page in a recent Chrome, Edge or Firefox.');}
    finally{renderQbExport();}
  }
  function mobile(){
    if(!current||!$('mobile-service'))return;
    const client=$('mobile-client').value;
    renderArrExport();
    renderNzbExport();
    renderQbExport();
    const services=current.services.filter(s=>(client==='arrcontrol'?Object.hasOwn(arrServices,s.id):mobileIds.includes(s.id))&&(client!=='qbremote'||s.id==='qbittorrent'));
    const chosen=$('mobile-service').value;
    $('mobile-service').replaceChildren(...services.map(s=>{const o=el('option',s.name);o.value=s.id;return o;}));
    if(services.some(s=>s.id===chosen))$('mobile-service').value=chosen;
    $('mobile-service').disabled=client==='qbremote'||!services.length;
    $('mobile-fields').replaceChildren();
    if(!services.length){$('mobile-help').textContent=text('Aucune application compatible sélectionnée.','No compatible service selected.');$('mobile-network').disabled=true;return;}
    const service=services.find(s=>s.id===$('mobile-service').value)||services[0];
    const previous=$('mobile-network').value;
    $('mobile-network').replaceChildren();
    for(const [value,label] of [['local',text('Réseau local','Local network')],['remote',text('À distance','Remote')]]){
      if(value==='remote'&&!service.remote_url)continue;const option=el('option',label);option.value=value;$('mobile-network').append(option);
    }
    if(previous==='remote'&&service.remote_url)$('mobile-network').value='remote';
    $('mobile-network').disabled=false;
    const distant=$('mobile-network').value==='remote';
    const raw=distant?service.remote_url:(service.local_url||service.url);
    let url;try{url=new URL(raw);if(!['http:','https:'].includes(url.protocol))throw Error();}catch{$('mobile-help').textContent=text('Adresse indisponible.','Address unavailable.');return;}
    let note=current.demo?text('Simulation : ces coordonnées ne correspondent pas à une installation réelle. ','Simulation: these addresses are not a real installation. '):'';
    note+=distant?(current.remote?.mode==='tailscale'?text('Connectez Tailscale sur le téléphone, puis testez dans votre application.','Connect Tailscale on your phone, then test in your app.'):text('Testez depuis le téléphone en 4G/5G. La connexion extérieure reste à confirmer.','Test from your phone on mobile data. External connectivity is not yet confirmed.')):text('Connectez le téléphone au même réseau que le serveur.','Connect your phone to the server’s local network.');
    if(!distant&&current.remote?.mode!=='local'&&!service.remote_url)note+=' '+text('Accès distant non activé pour cette application.','Remote access is not activated for this application.');
    $('mobile-help').textContent=note;
    const rows=[[text('Nom','Name'),service.name],[text('URL complète','Full URL'),raw],[text('Hôte (si demandé séparément)','Host (if requested separately)'),url.hostname],[text('Port','Port'),url.port||(url.protocol==='https:'?'443':'80')],['HTTPS / SSL',url.protocol==='https:'?text('Activé','Enabled'):text('Désactivé','Disabled')]];
    if(url.pathname!=='/')rows.push([text('Chemin de base','Base path'),url.pathname]);
    if(service.id==='qbittorrent')rows.push([text('Utilisateur','Username'),service.username],[text('Mot de passe','Password'),service.password,true]);
    else rows.push([text('Clé API','API key'),service.api_key,true]);
    rows.forEach(([label,value,secret])=>$('mobile-fields').append(field(label,value||'',secret)));
    $('mobile-copy-status').textContent='';
  }
  return {english,init,refresh,read,valid,report,mountMobile,buildArrControlExport,buildNzb360Export,buildQbRemoteServer,buildQbRemoteExport};
})();
