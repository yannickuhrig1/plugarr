/* Shared remote-access step and mobile forms, including the offline HTML report. */
'use strict';
globalThis.PlugArrRemote = (() => {
  const $ = id => document.getElementById(id);
  const el = (tag, text) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; return n; };
  const ids=['sonarr','radarr','qbittorrent'];
  // Fiches du telephone : services sans acces distant gere par PlugArr en plus.
  const mobileIds=[...ids,'sabnzbd','lidarr','seerr','transmission'];
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
  // Sauvegardes chargees pour la fusion. Elles restent dans le navigateur.
  let nzbBase=null, nzbBaseError='', qbStatus='';
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
      const nzbBaseLabel=el('label',text('Partir de ma sauvegarde nzb360 (facultatif) : ses réglages sont gardés, PlugArr y ajoute ses applications','Start from my nzb360 backup (optional): its settings are kept, PlugArr adds its applications'));
      const nzbBaseInput=el('input');nzbBaseInput.type='file';nzbBaseInput.id='nzb-export-base';nzbBaseInput.accept='.zip,application/zip';
      nzbBaseInput.addEventListener('change',loadNzbBase);nzbBaseLabel.append(nzbBaseInput);nzbBox.append(nzbBaseLabel);
      const nzbConflicts=el('div');nzbConflicts.id='nzb-export-conflicts';nzbBox.append(nzbConflicts);
      const nzbNotice=el('p');nzbNotice.id='nzb-export-notice';nzbNotice.className='notice';nzbBox.append(nzbNotice);
      const consent=el('label');consent.className='inline-choice';const check=el('input');check.type='checkbox';check.id='nzb-export-confirm';
      consent.append(check,el('span',text('J’ai sauvegardé mes réglages nzb360. La restauration de ce ZIP remplace tous mes réglages nzb360, y compris les services qui n’y figurent pas.','I backed up my nzb360 settings. Restoring this ZIP replaces all my nzb360 settings, including services it does not contain.')));nzbBox.append(consent);
      const nzbButton=el('button',text('Télécharger pour nzb360','Download for nzb360'));nzbButton.id='nzb-export-download';nzbButton.type='button';nzbButton.className='primary';nzbButton.disabled=true;
      nzbButton.addEventListener('click',()=>downloadNzb360());check.addEventListener('change',renderNzbExport);
      nzbSelect.addEventListener('change',()=>{check.checked=false;renderNzbExport();});nzbBox.append(nzbButton);
      phoneButton(nzbBox,'nzb',()=>downloadNzb360(true));
      nzbBox.append(el('p',text('Dans nzb360 24.4.1, utilisez Sauvegarde / Restauration avec ce ZIP. Sans sauvegarde de départ, il ne contient que les applications PlugArr, sans achat ni licence ; en fusion, il reprend toute votre sauvegarde. Secrets non chiffrés : ne partagez pas ce fichier.','In nzb360 24.4.1, use Backup / Restore with this ZIP. Without a starting backup it only holds the PlugArr applications, with no purchase or licence; when merged it carries your whole backup. Unencrypted secrets: do not share this file.')));
      box.after(nzbBox);
      const qbBox=el('section');qbBox.id='qb-export';qbBox.className='mobile-export';qbBox.hidden=true;
      const qbLabel=el('label',text('Profil qbRemote 1.8.0','qbRemote 1.8.0 profile'));
      const qbSelect=select.cloneNode(true);qbSelect.id='qb-export-network';qbLabel.append(qbSelect);qbBox.append(qbLabel);
      const ssidLabel=el('label',text('Nom du Wi-Fi de la maison (facultatif) : qbRemote bascule alors seul sur l’adresse locale','Home Wi-Fi name (optional): qbRemote then switches to the local address by itself'));
      ssidLabel.id='qb-export-ssid-label';const ssid=el('input');ssid.id='qb-export-ssid';ssid.maxLength=32;ssid.autocomplete='off';ssid.spellcheck=false;ssidLabel.append(ssid);qbBox.append(ssidLabel);
      const passwordLabel=el('label',text('Mot de passe du fichier (demandé par qbRemote à la restauration)','File password (qbRemote asks for it when restoring)'));
      const password=el('input');password.id='qb-export-password';password.type='password';password.autocomplete='new-password';password.maxLength=128;passwordLabel.append(password);qbBox.append(passwordLabel);
      const qbBaseLabel=el('label',text('Partir de ma sauvegarde qbRemote (facultatif) : vos serveurs et préférences sont gardés, le serveur PlugArr est ajouté','Start from my qbRemote backup (optional): your servers and preferences are kept, the PlugArr server is added'));
      const qbBaseInput=el('input');qbBaseInput.type='file';qbBaseInput.id='qb-export-base';qbBaseInput.accept='.zip,application/zip';qbBaseLabel.append(qbBaseInput);qbBox.append(qbBaseLabel);
      qbBaseInput.addEventListener('change',()=>{qbStatus='';qbCheck.checked=false;renderQbExport();});
      const qbNotice=el('p');qbNotice.id='qb-export-notice';qbNotice.className='notice';qbBox.append(qbNotice);
      const qbConsent=el('label');qbConsent.className='inline-choice';const qbCheck=el('input');qbCheck.type='checkbox';qbCheck.id='qb-export-confirm';
      qbConsent.append(qbCheck,el('span',text('J’ai sauvegardé mes réglages qbRemote. La restauration de ce fichier remplace tous mes serveurs qbRemote ; les préférences d’affichage restent.','I backed up my qbRemote settings. Restoring this file replaces all my qbRemote servers; display preferences stay.')));qbBox.append(qbConsent);
      const qbButton=el('button',text('Télécharger pour qbRemote','Download for qbRemote'));qbButton.id='qb-export-download';qbButton.type='button';qbButton.className='primary';qbButton.disabled=true;
      qbButton.addEventListener('click',()=>downloadQbRemote());qbBox.append(qbButton);
      phoneButton(qbBox,'qb',()=>downloadQbRemote(true));
      qbSelect.addEventListener('change',()=>{qbCheck.checked=false;renderQbExport();});
      for(const input of [ssid,password])input.addEventListener('input',()=>{qbStatus='';renderQbExport();});qbCheck.addEventListener('change',renderQbExport);
      qbBox.append(el('p',text('Dans qbRemote 1.8.0, restaurez ce fichier depuis la fonction de sauvegarde, avec le mot de passe choisi ici. Sans sauvegarde de départ, seul le serveur PlugArr est inclus et vos préférences d’affichage ne sont pas touchées ; en fusion, tout le contenu de votre sauvegarde est repris. Le fichier est chiffré, mais gardez-le privé.','In qbRemote 1.8.0, restore this file from the backup feature with the password chosen here. Without a starting backup only the PlugArr server is included and display preferences are untouched; when merged, your whole backup is carried over. The file is encrypted, but keep it private.')));
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
  // Java Object Serialization stream: bounded HashMap writer for the value
  // types seen in nzb360 backups. UIDs read from the JDK (ObjectStreamClass);
  // HashMap and Boolean also match the inspected 24.4.1 export.
  const JAVA_NUMBERS={I:['java.lang.Integer','12e2a0a4f7818738'],J:['java.lang.Long','3b8be490cc8f23df'],
    F:['java.lang.Float','daedc9a2db3cf0ec'],D:['java.lang.Double','80b3c24a296bfb04']};
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
    const desc=(name,uid,flags,fields,parent)=>{
      out.push(0x72);utf(name);for(let i=0;i<16;i+=2)out.push(parseInt(uid.slice(i,i+2),16));
      out.push(flags);be(fields.length,2);
      for(const [type,name] of fields){out.push(type.charCodeAt(0));utf(name);}
      out.push(0x78);if(parent)parent();else out.push(0x70);
    };
    const number=()=>desc('java.lang.Number','86ac951d0b94e08b',2,[]);
    const entries=Object.entries(preferences);if(entries.length>4096)throw new Error('Too many preferences');
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
      }else if(value&&typeof value==='object'&&Object.hasOwn(JAVA_NUMBERS,value.t)){
        const [name,uid]=JAVA_NUMBERS[value.t],view=new DataView(new ArrayBuffer(8));
        out.push(0x73);desc(name,uid,2,[[value.t,'value']],number);
        if(value.t==='I'){view.setInt32(0,value.v);out.push(...new Uint8Array(view.buffer,0,4));}
        else if(value.t==='J'){view.setBigInt64(0,BigInt(value.v));out.push(...new Uint8Array(view.buffer));}
        else if(value.t==='F'){view.setFloat32(0,value.v);out.push(...new Uint8Array(view.buffer,0,4));}
        else{view.setFloat64(0,value.v);out.push(...new Uint8Array(view.buffer));}
      }else throw new Error('Unsupported preference type');
    }
    out.push(0x78);return Uint8Array.from(out);
  }
  // Passive reader for the same streams: a HashMap of String keys to String,
  // Boolean or boxed numbers. Anything else is refused rather than guessed,
  // so a merge never rewrites a value it did not understand.
  function readJavaPreferences(bytes){
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),handles=[];let i=0;
    const need=n=>{if(i+n>bytes.length)throw new Error('Truncated stream');};
    const u1=()=>{need(1);return bytes[i++];};
    const u2=()=>{need(2);const v=view.getUint16(i);i+=2;return v;};
    const i4=()=>{need(4);const v=view.getInt32(i);i+=4;return v;};
    const modifiedUtf=n=>{
      need(n);const end=i+n;let s='';
      while(i<end){
        const a=bytes[i++];
        if(a<0x80)s+=String.fromCharCode(a);
        else if((a&0xe0)===0xc0){const b=bytes[i++];s+=String.fromCharCode(((a&0x1f)<<6)|(b&0x3f));}
        else if((a&0xf0)===0xe0){const b=bytes[i++],c=bytes[i++];s+=String.fromCharCode(((a&0x0f)<<12)|((b&0x3f)<<6)|(c&0x3f));}
        else throw new Error('Bad string');
      }
      if(i!==end)throw new Error('Bad string');return s;
    };
    const reference=()=>{const h=i4()-0x7e0000;if(h<0||h>=handles.length)throw new Error('Bad reference');return handles[h];};
    function classDesc(){
      const tc=u1();if(tc===0x70)return null;if(tc===0x71)return reference();
      if(tc!==0x72)throw new Error('Unsupported class descriptor');
      const d={name:modifiedUtf(u2()),fields:[]};need(8);i+=8;handles.push(d);d.flags=u1();
      for(let n=u2();n>0;n--){const type=String.fromCharCode(u1()),name=modifiedUtf(u2());if(type==='L'||type==='[')content();d.fields.push([type,name]);}
      if(u1()!==0x78)throw new Error('Unsupported class annotation');
      d.parent=classDesc();return d;
    }
    function primitive(type){
      if(type==='Z')return u1()!==0;
      if(type==='I')return i4();
      if(type==='J'){need(8);const v=view.getBigInt64(i);i+=8;return v;}
      if(type==='F'){need(4);const v=view.getFloat32(i);i+=4;return v;}
      if(type==='D'){need(8);const v=view.getFloat64(i);i+=8;return v;}
      throw new Error('Unsupported field type');
    }
    function content(){
      const tc=u1();
      if(tc===0x74){const s=modifiedUtf(u2());handles.push(s);return s;}
      if(tc===0x71)return reference();
      if(tc===0x70)return null;
      if(tc!==0x73)throw new Error('Unsupported content');
      const d=classDesc(),handle=handles.length;handles.push(null);
      const chain=[];for(let c=d;c;c=c.parent)chain.unshift(c);
      const values={},objects=[];
      for(const c of chain){
        for(const [type,name] of c.fields)values[name]=primitive(type);
        if(c.flags&1)for(;;){
          need(1);
          if(bytes[i]===0x78){i++;break;}
          if(bytes[i]===0x77){i++;const n=u1();need(n);i+=n;}
          else objects.push(content());
        }
      }
      let value;
      if(d.name==='java.util.HashMap'){
        if(objects.length%2)throw new Error('Bad map');
        value=new Map();
        for(let k=0;k<objects.length;k+=2){if(typeof objects[k]!=='string')throw new Error('Bad key');value.set(objects[k],objects[k+1]);}
      }else if(d.name==='java.lang.Boolean')value=values.value;
      else{
        const t=Object.keys(JAVA_NUMBERS).find(k=>JAVA_NUMBERS[k][0]===d.name);
        if(!t)throw new Error('Unsupported type '+d.name);
        value={t,v:values.value};
      }
      handles[handle]=value;return value;
    }
    if(bytes.length<4||view.getUint32(0)!==0xaced0005)throw new Error('Not a Java stream');
    i=4;const map=content();
    if(!(map instanceof Map))throw new Error('Not a map');
    if(i!==bytes.length)throw new Error('Trailing data');
    return map;
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
  // Keys PlugArr writes, grouped by service, so a merge can add or replace a
  // whole service and leave every other key of the user's backup untouched.
  function nzb360Groups(data,network='local',ssid=''){
    const {payload,omitted}=buildArrControlExport({...data,services:data.services.filter(s=>ids.includes(s.id))},network);
    const home=network==='remote'&&ssid?ssid:'';
    const localAddress=id=>{
      const service=data.services.find(s=>s.id===id);
      try{const url=new URL(service.local_url||service.url);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url.href.replace(/\/$/,''):'';}catch{return '';}
    };
    const groups={},switching=new Set();
    for(const service of payload.services){
      const prefix={sonarr:'nzbdrone',radarr:'radarr',qbittorrent:'torrent'}[service.serviceId];
      const local=home?localAddress(service.serviceId):'';
      if(local)switching.add(service.serviceId);
      const group={
        [`${prefix}_server_enabled_preference`]:true,
        [`${prefix}_server_primary_connectionstring_preference`]:service.url,
        [`${prefix}_server_local_connectionstring_preference`]:local,
        [`${prefix}_server_SSID_preference`]:local?home:'',
        // Without this switch nzb360 keeps the addresses but never uses the local
        // one. Key names read from a 24.4.1 backup made with the switch enabled.
        [`${prefix}_localconnectionswitch_preference`]:Boolean(local),
      };
      if(service.serviceId==='qbittorrent')Object.assign(group,{torrent_client_preference:'qbittorrent',
        torrent_username:service.config.fields.username,torrent_password:service.config.fields.password,torrent_rpc_path:''});
      else group[`${prefix}_apikey_preference`]=service.apiKey;
      groups[service.serviceId]=group;
    }
    const sab=data.services.find(s=>s.id==='sabnzbd');
    if(sab){
      let address='';
      try{const url=new URL(network==='remote'?sab.remote_url:(sab.local_url||sab.url));if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password)address=url.href.replace(/\/$/,'');}catch{}
      const key=typeof sab.api_key==='string'&&sab.api_key!=='-'?sab.api_key:'';
      if(address&&key){
        const local=home?localAddress('sabnzbd'):'';
        if(local)switching.add('sabnzbd');
        groups.sabnzbd={server_enabled_preference:true,sabnzbd_server_primary_connectionstring_preference:address,
          sabnzbd_server_local_connectionstring_preference:local,server_SSID_preference:local?home:'',sabapi_preference:key};
      }else omitted.push(sab.name);
    }
    // Lidarr, Seerr (`overseerr_` keys) and Transmission: key names read from a
    // 24.4.1 backup made after configuring them in a second profile. Like
    // SABnzbd, PlugArr gives them no remote access: local profile only.
    // nzb360 has a single torrent slot: qBittorrent keeps it when both exist.
    const present=value=>typeof value==='string'&&value.length>0&&value!=='-';
    for(const [id,prefix] of [['lidarr','lidarr'],['seerr','overseerr'],['transmission','torrent']]){
      const service=data.services.find(s=>s.id===id);
      if(!service||(id==='transmission'&&groups.qbittorrent))continue;
      let address='';
      try{const url=new URL(network==='remote'?service.remote_url:(service.local_url||service.url));if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password)address=url.href.replace(/\/$/,'');}catch{}
      const needed=id==='transmission'?[service.username,service.password]:[service.api_key];
      if(!address||!needed.every(present)){omitted.push(service.name);continue;}
      const secrets=id==='transmission'?{torrent_client_preference:'transmission',torrent_username:service.username,torrent_password:service.password,torrent_rpc_path:''}
        :{[`${prefix}_apikey_preference`]:service.api_key};
      const local=home?localAddress(id):'';
      if(local)switching.add(id);
      groups[id]={[`${prefix}_server_enabled_preference`]:true,[`${prefix}_server_primary_connectionstring_preference`]:address,
        [`${prefix}_server_local_connectionstring_preference`]:local,[`${prefix}_server_SSID_preference`]:local?home:'',
        [`${prefix}_localconnectionswitch_preference`]:Boolean(local),...secrets};
    }
    return {groups,omitted,switching};
  }
  function buildNzb360Export(data,network='local',ssid=''){
    const {groups,omitted,switching}=nzb360Groups(data,network,ssid);
    const preferences={version:'24.4.1',nzbdrone_server_enabled_preference:false,radarr_server_enabled_preference:false,torrent_server_enabled_preference:false,server_enabled_preference:false,
      lidarr_server_enabled_preference:false,overseerr_server_enabled_preference:false};
    for(const group of Object.values(groups))Object.assign(preferences,group);
    const files=[['com.kevinforeman.nzb360_preferences.xml',javaPreferences(preferences)],
      ['nzb360prefs.xml',javaPreferences({version:'24.4.1'})],['servers.xml',javaPreferences({})]];
    return {bytes:zipStored(files),count:Object.keys(groups).length,omitted,switching:switching.size};
  }
  const NZB360_FILE='com.kevinforeman.nzb360_preferences.xml';
  // Slots of the Default profile. qBittorrent and Transmission share the
  // single torrent slot (`torrent_` keys, client in torrent_client_preference).
  const NZB360_PRIMARY={sonarr:'nzbdrone_server_primary_connectionstring_preference',radarr:'radarr_server_primary_connectionstring_preference',
    torrent:'torrent_server_primary_connectionstring_preference',sabnzbd:'sabnzbd_server_primary_connectionstring_preference',
    lidarr:'lidarr_server_primary_connectionstring_preference',seerr:'overseerr_server_primary_connectionstring_preference'};
  const NZB360_ENABLED={sonarr:'nzbdrone_server_enabled_preference',radarr:'radarr_server_enabled_preference',
    torrent:'torrent_server_enabled_preference',sabnzbd:'server_enabled_preference',
    lidarr:'lidarr_server_enabled_preference',seerr:'overseerr_server_enabled_preference'};
  const NZB360_NAMES={sonarr:'Sonarr',radarr:'Radarr',qbittorrent:'qBittorrent',transmission:'Transmission',sabnzbd:'SABnzbd',lidarr:'Lidarr',seerr:'Seerr'};
  const nzbSlot=id=>['qbittorrent','transmission'].includes(id)?'torrent':id;
  // A service counts as present as soon as it has an address, even disabled:
  // replacing it would lose that address.
  async function inspectNzb360Backup(bytes){
    const files=await readZipFiles(bytes);
    const index=files.findIndex(([name])=>name===NZB360_FILE);
    if(index<0)throw new Error('Not an nzb360 backup');
    const preferences=readJavaPreferences(files[index][1]);
    const configured=Object.keys(NZB360_PRIMARY)
      .filter(id=>{const value=preferences.get(NZB360_PRIMARY[id]);return typeof value==='string'&&value.length>0;})
      .map(id=>({id,url:preferences.get(NZB360_PRIMARY[id]),enabled:preferences.get(NZB360_ENABLED[id])===true}));
    // PlugArr writes the Default profile. nzb360prefs.xml names the profile in
    // use: "*" for Default, "001" for the profile stored in 001.xml, etc.
    let activeProfile='*';
    try{const app=files.find(([name])=>name==='nzb360prefs.xml');const value=app&&readJavaPreferences(app[1]).get('lastActiveProfile');if(typeof value==='string'&&value)activeProfile=value;}catch{}
    return {files,preferences,configured,activeProfile};
  }
  // Name shown for an occupied slot: the torrent slot names its client.
  function nzbSlotName(base,slot){
    if(slot!=='torrent')return NZB360_NAMES[slot];
    const client=base.preferences.get('torrent_client_preference');
    return NZB360_NAMES[client]||text('Client torrent','Torrent client');
  }
  function mergeNzb360(base,data,network='local',ssid='',replace=[]){
    const {groups,omitted,switching}=nzb360Groups(data,network,ssid);
    const preferences=new Map(base.preferences),added=[],replaced=[],kept=[];
    for(const [id,group] of Object.entries(groups)){
      const present=base.configured.some(c=>c.id===nzbSlot(id));
      if(present&&!replace.includes(nzbSlot(id))){kept.push(nzbSlot(id));continue;}
      for(const [key,value] of Object.entries(group))preferences.set(key,value);
      (present?replaced:added).push(id);
    }
    const files=base.files.map(([name,content])=>[name,name===NZB360_FILE?javaPreferences(Object.fromEntries(preferences)):content]);
    return {bytes:zipStored(files),added,replaced,kept,omitted,switching:[...switching].filter(id=>!kept.includes(nzbSlot(id))).length};
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
      const result=nzbResult($('nzb-export-network').value,distant?$('nzb-export-ssid').value.trim():'');
      $('nzb-export-download').disabled=!result.count||!$('nzb-export-confirm').checked;
      if($('nzb-export-phone'))$('nzb-export-phone').disabled=$('nzb-export-download').disabled;
      const switching=result.switching
        ?text(` Sur le Wi-Fi « ${$('nzb-export-ssid').value.trim()} », ${result.switching} application(s) passent sur l’adresse locale. Autorisez la localisation quand nzb360 la demande : Android en a besoin pour lire le nom du Wi-Fi.`,` On Wi-Fi "${$('nzb-export-ssid').value.trim()}", ${result.switching} service(s) switch to the local address. Allow location when nzb360 asks: Android needs it to read the Wi-Fi name.`)
        :(distant?text(' Sans nom de Wi-Fi, ce profil utilise toujours l’adresse distante.',' Without a Wi-Fi name, this profile always uses the remote address.'):'');
      $('nzb-export-notice').textContent=text(`nzb360 24.4.1 : ${result.count} application(s) parmi Sonarr, Radarr, Lidarr, Seerr, qBittorrent ou Transmission, et SABnzbd. nzb360 n’a qu’un client torrent : qBittorrent passe avant Transmission. Lidarr, Seerr, Transmission et SABnzbd n’ont pas encore été essayés sur un téléphone.`, `nzb360 24.4.1: ${result.count} service(s) among Sonarr, Radarr, Lidarr, Seerr, qBittorrent or Transmission, and SABnzbd. nzb360 has a single torrent client: qBittorrent comes before Transmission. Lidarr, Seerr, Transmission and SABnzbd have not yet been tried on a phone.`)
        +switching
        +(result.omitted.length?' '+text('Exclues (adresse ou identifiants indisponibles pour ce réseau) : ','Excluded (address or credentials unavailable for this network): ')+result.omitted.join(', ')+'.':'')
        +(result.merge?' '+result.merge:'')
        +(nzbBaseError?' '+nzbBaseError:'')
        +(current.demo?' '+text('DÉMONSTRATION : accès fictifs.','DEMO: fictitious connections.'):'')
        +($('nzb-export-network').value==='remote'&&current.remote?.mode==='tailscale'?' '+text('Avec Tailscale, connectez aussi le téléphone.','With Tailscale, connect the phone too.'):'');
    }catch{ $('nzb-export-download').disabled=true;if($('nzb-export-phone'))$('nzb-export-phone').disabled=true;$('nzb-export-notice').textContent=text('Export impossible : un champ dépasse la taille prise en charge.','Export unavailable: a field exceeds the supported size.'); }
  }
  const nzbReplace=()=>[...document.querySelectorAll('#nzb-export-conflicts input[data-replace]:checked')].map(box=>box.dataset.replace);
  // Fresh export, or merge into the loaded backup: same notice, same button.
  function nzbResult(network,ssid){
    if(!nzbBase)return buildNzb360Export(current,network,ssid);
    const result=mergeNzb360(nzbBase,current,network,ssid,nzbReplace());
    // added/replaced name PlugArr's services, kept names the user's slots.
    const names=list=>list.map(id=>NZB360_NAMES[id]).join(', ')||text('aucune','none');
    const slots=list=>list.map(slot=>nzbSlotName(nzbBase,slot)).join(', ')||text('aucune','none');
    const profile=nzbBase.activeProfile!=='*'?' '+text('Votre sauvegarde est sur un autre profil que Default : les applications PlugArr sont dans le profil Default, à choisir en bas du menu de nzb360.','Your backup is on a profile other than Default: the PlugArr services are in the Default profile, selectable at the bottom of the nzb360 menu.'):'';
    return {...result,count:result.added.length+result.replaced.length,
      merge:text(`Fusion avec votre sauvegarde : ajoutées : ${names(result.added)} ; remplacées : ${names(result.replaced)} ; gardées telles quelles : ${slots(result.kept)}. Tout le reste de votre sauvegarde est conservé (autres services, profils, préférences, licence).${profile}`,
        `Merged with your backup: added: ${names(result.added)}; replaced: ${names(result.replaced)}; kept as they are: ${slots(result.kept)}. Everything else in your backup is kept (other services, profiles, preferences, licence).${profile}`)};
  }
  async function loadNzbBase(){
    const file=$('nzb-export-base').files[0];
    nzbBase=null;nzbBaseError='';$('nzb-export-conflicts').replaceChildren();
    if(file){
      try{
        if(file.size>1048576)throw new Error('Too large');
        nzbBase=await inspectNzb360Backup(new Uint8Array(await file.arrayBuffer()));
        if(nzbBase.configured.length)$('nzb-export-conflicts').append(el('p',text('Déjà présents dans votre sauvegarde, gardés tels quels sauf si vous cochez :','Already in your backup, kept as they are unless ticked:')));
        for(const service of nzbBase.configured){
          const label=el('label'),box=el('input');label.className='inline-choice';box.type='checkbox';box.dataset.replace=service.id;
          box.addEventListener('change',()=>{$('nzb-export-confirm').checked=false;renderNzbExport();});
          const detail=service.url+(service.enabled?'':text(', désactivé',', disabled'));
          label.append(box,el('span',text(`Remplacer ${nzbSlotName(nzbBase,service.id)} (${detail}) par celui de PlugArr`,`Replace ${nzbSlotName(nzbBase,service.id)} (${detail}) with PlugArr's`)));
          $('nzb-export-conflicts').append(label);
        }
      }catch{nzbBase=null;nzbBaseError=text('Ce fichier n’est pas une sauvegarde nzb360 lisible : export sans fusion.','This file is not a readable nzb360 backup: export without merge.');}
    }
    $('nzb-export-confirm').checked=false;renderNzbExport();
  }
  async function downloadNzb360(toPhone=false){
    if(!current||!$('nzb-export-confirm').checked)return;
    try{
      const network=$('nzb-export-network').value,result=nzbResult(network,network==='remote'?$('nzb-export-ssid').value.trim():'');if(!result.count)return;
      await deliver(result.bytes,nzbBase?`nzb360_backup_plugarr${current.demo?'-demo':''}-fusion-${network}.zip`:`plugarr${current.demo?'-demo':''}-nzb360-24.4.1-${network}.zip`,toPhone&&'nzb');
    }catch{renderNzbExport();}
  }
  function saveFile(bytes,name){
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));
    const link=el('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  // The file goes to the PC, or to the phone through a one-time link on the
  // local network, shown as a QR code (wizard only: the offline page has no server).
  async function deliver(bytes,name,phone){
    if(!phone)return saveFile(bytes,name);
    const box=$(`${phone}-export-qr`);box.hidden=false;box.replaceChildren(el('p',text('Préparation du lien…','Preparing the link…')));
    try{
      const shared=await request(`/api/phone-share?name=${encodeURIComponent(name)}`,new Blob([bytes],{type:'application/octet-stream'}));
      const until=new Date(Date.now()+shared.expires_in*1000).toLocaleTimeString(language()==='en'?'en':'fr',{hour:'2-digit',minute:'2-digit'});
      box.replaceChildren(qrSvg(shared.url),
        el('p',(shared.demo?text('DÉMONSTRATION : aucun lien n’est réellement ouvert. ','DEMO: no link is actually opened. '):'')
          +text(`Scannez avec l’appareil photo du téléphone, connecté au même Wi-Fi que ce serveur. Le lien sert une seule fois, jusqu’à ${until}. Le fichier arrive dans Téléchargements : restaurez-le ensuite dans l’application.`,
            `Scan with the phone camera, on the same Wi-Fi as this server. The link works once, until ${until}. The file lands in Downloads: then restore it in the app.`)),el('code',shared.url));
    }catch(error){box.replaceChildren(el('p',error.message||text('Lien impossible à ouvrir.','The link could not be opened.')));}
  }
  function phoneButton(parent,prefix,action){
    if(!request)return;
    const button=el('button',text('Envoyer au téléphone (QR code)','Send to the phone (QR code)'));button.id=`${prefix}-export-phone`;button.type='button';button.className='secondary';button.disabled=true;
    button.addEventListener('click',action);
    const box=el('div');box.id=`${prefix}-export-qr`;box.className='phone-qr';box.hidden=true;
    parent.append(button,box);
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
  // ZIP reader for the backups loaded in a merge: stored, deflate and WinZip AES.
  function zipEntries(bytes){
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),decoder=new TextDecoder();
    let end=-1;
    for(let p=bytes.length-22;p>=0&&p>=bytes.length-65557;p--)if(view.getUint32(p,true)===0x06054b50){end=p;break;}
    if(end<0)throw new Error('Not a ZIP file');
    const entries=[];let p=view.getUint32(end+16,true);
    for(let n=view.getUint16(end+10,true);n>0;n--){
      if(p+46>bytes.length||view.getUint32(p,true)!==0x02014b50)throw new Error('Bad ZIP directory');
      const flags=view.getUint16(p+8,true),method=view.getUint16(p+10,true),crc=view.getUint32(p+16,true),size=view.getUint32(p+20,true);
      const nameLength=view.getUint16(p+28,true),extraLength=view.getUint16(p+30,true),commentLength=view.getUint16(p+32,true),offset=view.getUint32(p+42,true);
      const name=decoder.decode(bytes.subarray(p+46,p+46+nameLength)),extra=bytes.subarray(p+46+nameLength,p+46+nameLength+extraLength);
      if(offset+30>bytes.length||view.getUint32(offset,true)!==0x04034b50)throw new Error('Bad ZIP entry');
      const start=offset+30+view.getUint16(offset+26,true)+view.getUint16(offset+28,true);
      if(start+size>bytes.length)throw new Error('Truncated ZIP');
      let aes=null;
      for(let q=0;q+4<=extra.length;){
        const id=extra[q]|(extra[q+1]<<8),length=extra[q+2]|(extra[q+3]<<8);
        if(id===0x9901&&length>=7)aes={version:extra[q+4]|(extra[q+5]<<8),strength:extra[q+8],method:extra[q+9]|(extra[q+10]<<8)};
        q+=4+length;
      }
      entries.push({name,flags,method,crc,aes,data:bytes.subarray(start,start+size)});
      p+=46+nameLength+extraLength+commentLength;
    }
    return entries;
  }
  async function transform(bytes,stream){return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer());}
  // WinZip AES: PBKDF2-HMAC-SHA1 x1000, AES-CTR with a little-endian counter
  // starting at 1, HMAC-SHA1 truncated to 10 bytes.
  async function aesKeys(password,salt,keyLength){
    const subtle=globalThis.crypto.subtle;
    const base=await subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);
    const bits=new Uint8Array(await subtle.deriveBits({name:'PBKDF2',hash:'SHA-1',salt,iterations:1000},base,(2*keyLength+2)*8));
    return {aes:await subtle.importKey('raw',bits.slice(0,keyLength),'AES-CTR',false,['encrypt']),
      mac:await subtle.importKey('raw',bits.slice(keyLength,2*keyLength),{name:'HMAC',hash:'SHA-1'},false,['sign']),
      check:bits.slice(2*keyLength)};
  }
  async function aesCtr(key,data){
    const out=new Uint8Array(data.length);
    for(let start=0,block=1;start<data.length;start+=16,block++){
      const counter=new Uint8Array(16);for(let i=0,n=block;n>0;i++,n=Math.floor(n/256))counter[i]=n&255;
      out.set(new Uint8Array(await globalThis.crypto.subtle.encrypt({name:'AES-CTR',counter,length:128},key,data.subarray(start,start+16))),start);
    }
    return out;
  }
  class ZipPasswordError extends Error{}
  async function readZipFiles(bytes,password=''){
    const files=[];
    for(const entry of zipEntries(bytes)){
      let data=entry.data,method=entry.method;
      if(method===99){
        const keyLength=entry.aes&&{1:16,2:24,3:32}[entry.aes.strength];
        if(!keyLength)throw new Error('Unknown ZIP encryption');
        if(!password)throw new ZipPasswordError('Password required');
        const saltLength=keyLength/2;
        if(data.length<saltLength+12)throw new Error('Truncated entry');
        const keys=await aesKeys(password,data.slice(0,saltLength),keyLength);
        if(keys.check[0]!==data[saltLength]||keys.check[1]!==data[saltLength+1])throw new ZipPasswordError('Wrong password');
        const cipher=data.subarray(saltLength+2,data.length-10);
        const mac=new Uint8Array(await globalThis.crypto.subtle.sign('HMAC',keys.mac,cipher)).subarray(0,10);
        if(mac.some((b,k)=>b!==data[data.length-10+k]))throw new Error('Corrupted entry');
        data=await aesCtr(keys.aes,cipher);method=entry.aes.method;
      }else if(entry.flags&1)throw new Error('Unsupported ZIP encryption');
      if(method===8)data=await transform(data,new DecompressionStream('deflate-raw'));
      else if(method!==0)throw new Error('Unsupported compression');
      // AE-2 leaves the CRC at zero; AE-1 and plain entries keep the real one.
      if(!(entry.aes&&entry.aes.version===2)&&crc32(data)!==entry.crc)throw new Error('Corrupted entry');
      files.push([entry.name,data]);
    }
    return files;
  }
  // Headers copy those of the qbRemote sample: version 20, flags 0x801, AE-1.
  async function zipAes(files,password,now=new Date()){
    const subtle=globalThis.crypto&&globalThis.crypto.subtle;
    if(!subtle||typeof CompressionStream!=='function')throw new Error('Browser cannot encrypt');
    const encoder=new TextEncoder(),out=[],central=[];
    const le=(target,value,n)=>{for(let i=0;i<n;i++)target.push((value>>>(i*8))&255);};
    const put=(target,bytes)=>{for(const b of bytes)target.push(b);};
    const time=(now.getHours()<<11)|(now.getMinutes()<<5)|(now.getSeconds()>>1);
    const date=((now.getFullYear()-1980)<<9)|((now.getMonth()+1)<<5)|now.getDate();
    const extra=[0x01,0x99,0x07,0x00,0x01,0x00,0x41,0x45,0x03,0x08,0x00];
    for(const [name,content] of files){
      const plain=typeof content==='string'?encoder.encode(content):content,filename=encoder.encode(name),offset=out.length;
      const compressed=await transform(plain,new CompressionStream('deflate-raw'));
      const salt=globalThis.crypto.getRandomValues(new Uint8Array(16));
      const keys=await aesKeys(password,salt,32);
      const cipher=await aesCtr(keys.aes,compressed);
      const mac=new Uint8Array(await subtle.sign('HMAC',keys.mac,cipher)).subarray(0,10);
      const size=16+2+cipher.length+10,crc=crc32(plain);
      le(out,0x04034b50,4);for(const v of [20,0x801,99,time,date])le(out,v,2);
      for(const v of [crc,size,plain.length])le(out,v,4);le(out,filename.length,2);le(out,extra.length,2);
      put(out,filename);put(out,extra);put(out,salt);put(out,keys.check);put(out,cipher);put(out,mac);
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
  // Adds the PlugArr server to the user's own qbRemote backup: other servers,
  // settings and histories are copied back untouched, then re-encrypted with
  // the same password. A server already named PlugArr is updated in place.
  async function mergeQbRemote(bytes,password,data,network='local',ssid='',now=new Date()){
    const server=buildQbRemoteServer(data,network,ssid);
    if(!server)return null;
    const files=await readZipFiles(bytes,password);
    const index=files.findIndex(([name])=>name==='servers.json');
    const servers=index<0?[]:JSON.parse(new TextDecoder().decode(files[index][1]));
    if(!Array.isArray(servers))throw new Error('Unexpected servers.json');
    const same=servers.findIndex(s=>s&&s.name===server.name);
    if(same>=0){server.id=servers[same].id;servers[same]=server;}
    else{server.id=servers.reduce((max,s)=>Math.max(max,Number(s&&s.id)||0),0)+1;servers.push(server);}
    if(index<0)files.push(['servers.json',JSON.stringify(servers)]);else files[index]=['servers.json',JSON.stringify(servers)];
    if(!files.some(([name])=>name==='manifest.json'))files.unshift(['manifest.json',JSON.stringify({version:1,createdAt:now.toISOString(),appVersion:QB_APP_VERSION})]);
    return {bytes:await zipAes(files,password,now),kept:servers.length-1,updated:same>=0};
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
    if($('qb-export-phone'))$('qb-export-phone').disabled=$('qb-export-download').disabled;
    let message=server
      ?text(`qbRemote 1.8.0 : serveur « ${server.name} » vers ${server.scheme}://${server.host}:${server.port}.`,`qbRemote 1.8.0: server "${server.name}" at ${server.scheme}://${server.host}:${server.port}.`)
      :text('Export impossible : adresse ou identifiants de qBittorrent indisponibles pour ce réseau.','Export unavailable: qBittorrent address or credentials missing for this network.');
    if(server&&server.localHost)message+=' '+text(`Sur le Wi-Fi « ${server.localSsid} », qbRemote utilisera ${server.localScheme}://${server.localHost}:${server.localPort}. Après la restauration, ouvrez une fois Paramètres > Serveurs > ${server.name} > Réseau local pour autoriser la localisation : sans elle, Android ne donne pas le nom du Wi-Fi.`,`On Wi-Fi "${server.localSsid}", qbRemote will use ${server.localScheme}://${server.localHost}:${server.localPort}. After restoring, open Settings > Servers > ${server.name} > Local network once to allow location: without it, Android does not expose the Wi-Fi name.`);
    if(server&&password.length<QB_PASSWORD_MIN)message+=' '+text(`Choisissez un mot de passe d’au moins ${QB_PASSWORD_MIN} caractères : qbRemote le demandera à la restauration.`,`Choose a password of at least ${QB_PASSWORD_MIN} characters: qbRemote asks for it when restoring.`);
    if(server&&$('qb-export-base').files[0])message+=' '+text('Fusion : saisissez le mot de passe de votre sauvegarde ; le fichier produit utilise le même. Si elle n’en a pas, celui saisi ici protégera le fichier produit.','Merge: enter your backup password; the produced file uses the same one. If it has none, the one entered here protects the produced file.');
    if(qbStatus)message+=' '+qbStatus;
    if(current.demo)message+=' '+text('DÉMONSTRATION : accès fictifs.','DEMO: fictitious connections.');
    $('qb-export-notice').textContent=message;
  }
  async function downloadQbRemote(toPhone=false){
    if(!current||$('qb-export-download').disabled)return;
    const network=$('qb-export-network').value;
    $('qb-export-download').disabled=true;if($('qb-export-phone'))$('qb-export-phone').disabled=true;
    try{
      const base=$('qb-export-base').files[0];let bytes;
      if(base){
        if(base.size>1048576)throw new Error('Too large');
        const merged=await mergeQbRemote(new Uint8Array(await base.arrayBuffer()),$('qb-export-password').value,current,network,$('qb-export-ssid').value.trim());
        if(!merged)return;
        bytes=merged.bytes;
        qbStatus=text(`Fusion faite : ${merged.kept} serveur(s) de votre sauvegarde gardé(s), serveur PlugArr ${merged.updated?'mis à jour':'ajouté'}.`,`Merged: ${merged.kept} server(s) from your backup kept, PlugArr server ${merged.updated?'updated':'added'}.`);
      }else bytes=await buildQbRemoteExport(current,network,$('qb-export-ssid').value.trim(),$('qb-export-password').value);
      if(!bytes)return;
      await deliver(bytes,base?`qbRemote_plugarr${current.demo?'-demo':''}-fusion-${network}.backup.zip`:`qbRemote_plugarr${current.demo?'-demo':''}-${network}.backup.zip`,toPhone&&'qb');
    }catch(error){
      qbStatus=error instanceof ZipPasswordError
        ?text('Mot de passe incorrect pour cette sauvegarde qbRemote.','Wrong password for this qbRemote backup.')
        :$('qb-export-base').files[0]
          ?text('Ce fichier n’est pas une sauvegarde qbRemote lisible.','This file is not a readable qbRemote backup.')
          :text('Ce navigateur ne sait pas chiffrer le fichier. Ouvrez la page dans Chrome, Edge ou Firefox récents.','This browser cannot encrypt the file. Open the page in a recent Chrome, Edge or Firefox.');
    }
    finally{renderQbExport();}
  }
  // QR code (ISO/IEC 18004), byte mode, error correction M, versions 1 to 10:
  // enough for the one-time link to the phone. Written here rather than loaded
  // from a CDN, which the wizard's CSP forbids.
  const QR_BLOCKS=[null,[[1,16]],[[1,28]],[[1,44]],[[2,32]],[[2,43]],[[4,27]],[[4,31]],[[2,38],[2,39]],[[3,36],[2,37]],[[4,43],[1,44]]];
  const QR_ECC=[0,10,16,26,18,24,16,18,22,22,26];
  const QR_ALIGN=[null,[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50]];
  const qrMul=(x,y)=>{let z=0;for(let i=7;i>=0;i--){z=(z<<1)^((z>>>7)*0x11d);z^=((y>>>i)&1)*x;}return z;};
  function qrEcc(data,degree){
    const divisor=new Array(degree-1).fill(0);divisor.push(1);let root=1;
    for(let i=0;i<degree;i++){for(let j=0;j<divisor.length;j++){divisor[j]=qrMul(divisor[j],root);if(j+1<divisor.length)divisor[j]^=divisor[j+1];}root=qrMul(root,2);}
    const result=new Array(degree).fill(0);
    for(const b of data){const factor=b^result.shift();result.push(0);divisor.forEach((c,i)=>{result[i]^=qrMul(c,factor);});}
    return result;
  }
  function qrMatrix(textValue,forcedMask){
    const bytes=[...new TextEncoder().encode(textValue)];
    const capacity=v=>QR_BLOCKS[v].reduce((n,[count,size])=>n+count*size,0);
    let version=1;while(version<=10&&4+(version<10?8:16)+8*bytes.length>8*capacity(version))version++;
    if(version>10)throw new Error('Too long for a QR code');
    const bits=[];const put=(value,n)=>{for(let i=n-1;i>=0;i--)bits.push((value>>>i)&1);};
    put(4,4);put(bytes.length,version<10?8:16);for(const b of bytes)put(b,8);
    const total=8*capacity(version);put(0,Math.min(4,total-bits.length));while(bits.length%8)bits.push(0);
    for(let pad=0xec;bits.length<total;pad^=0xec^0x11)put(pad,8);
    const data=[];for(let i=0;i<bits.length;i+=8)data.push(bits.slice(i,i+8).reduce((a,b)=>a*2+b,0));
    const blocks=[];let offset=0;
    for(const [count,size] of QR_BLOCKS[version])for(let i=0;i<count;i++){blocks.push(data.slice(offset,offset+size));offset+=size;}
    const eccs=blocks.map(block=>qrEcc(block,QR_ECC[version]));
    const codewords=[];
    for(let i=0;i<Math.max(...blocks.map(b=>b.length));i++)for(const block of blocks)if(i<block.length)codewords.push(block[i]);
    for(let i=0;i<QR_ECC[version];i++)for(const ecc of eccs)codewords.push(ecc[i]);
    const size=17+4*version;
    const modules=Array.from({length:size},()=>new Array(size).fill(false));
    const reserved=Array.from({length:size},()=>new Array(size).fill(false));
    const set=(x,y,dark)=>{modules[y][x]=dark;reserved[y][x]=true;};
    for(let i=0;i<size;i++){set(6,i,i%2===0);set(i,6,i%2===0);}
    for(const [cx,cy] of [[3,3],[size-4,3],[3,size-4]])
      for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){const x=cx+dx,y=cy+dy,d=Math.max(Math.abs(dx),Math.abs(dy));if(x>=0&&x<size&&y>=0&&y<size)set(x,y,d!==2&&d!==4);}
    const align=QR_ALIGN[version],last=align.length-1;
    for(let i=0;i<align.length;i++)for(let j=0;j<align.length;j++){
      if((i===0&&j===0)||(i===0&&j===last)||(i===last&&j===0))continue;
      for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++)set(align[i]+dx,align[j]+dy,Math.max(Math.abs(dx),Math.abs(dy))!==1);
    }
    const format=mask=>{
      const value=(0<<3)|mask;let rem=value;for(let i=0;i<10;i++)rem=(rem<<1)^((rem>>>9)*0x537);
      const f=((value<<10)|rem)^0x5412,bit=i=>((f>>>i)&1)===1;
      for(let i=0;i<=5;i++)set(8,i,bit(i));
      set(8,7,bit(6));set(8,8,bit(7));set(7,8,bit(8));
      for(let i=9;i<15;i++)set(14-i,8,bit(i));
      for(let i=0;i<8;i++)set(size-1-i,8,bit(i));
      for(let i=8;i<15;i++)set(8,size-15+i,bit(i));
      set(8,size-8,true);
    };
    format(0);
    if(version>=7){
      let rem=version;for(let i=0;i<12;i++)rem=(rem<<1)^((rem>>>11)*0x1f25);
      const v=(version<<12)|rem;
      for(let i=0;i<18;i++){const dark=((v>>>i)&1)===1,a=size-11+i%3,b=Math.floor(i/3);set(a,b,dark);set(b,a,dark);}
    }
    let index=0;
    for(let right=size-1;right>=1;right-=2){
      if(right===6)right=5;
      for(let vert=0;vert<size;vert++)for(let j=0;j<2;j++){
        const x=right-j,y=((right+1)&2)===0?size-1-vert:vert;
        if(!reserved[y][x]&&index<codewords.length*8){modules[y][x]=((codewords[index>>>3]>>>(7-(index&7)))&1)===1;index++;}
      }
    }
    const masks=[(x,y)=>(x+y)%2===0,(x,y)=>y%2===0,x=>x%3===0,(x,y)=>(x+y)%3===0,(x,y)=>(Math.floor(x/3)+Math.floor(y/2))%2===0,
      (x,y)=>x*y%2+x*y%3===0,(x,y)=>(x*y%2+x*y%3)%2===0,(x,y)=>((x+y)%2+x*y%3)%2===0];
    const apply=mask=>{for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(!reserved[y][x]&&masks[mask](x,y))modules[y][x]=!modules[y][x];};
    // Penalty rules of the standard: runs, 2x2 blocks, finder-like patterns, balance.
    const penalty=()=>{
      let score=0,dark=0;
      const lines=[...modules,...modules[0].map((_,x)=>modules.map(row=>row[x]))];
      for(const line of lines){
        let run=1;for(let i=1;i<=size;i++){if(i<size&&line[i]===line[i-1])run++;else{if(run>=5)score+=run-2;run=1;}}
        const t=line.map(Number).join('');for(const p of ['10111010000','00001011101'])for(let i=t.indexOf(p);i>=0;i=t.indexOf(p,i+1))score+=40;
      }
      for(let y=0;y<size;y++)for(let x=0;x<size;x++){if(modules[y][x])dark++;if(x<size-1&&y<size-1){const c=modules[y][x];if(c===modules[y][x+1]&&c===modules[y+1][x]&&c===modules[y+1][x+1])score+=3;}}
      return score+10*Math.floor(Math.abs(dark*20-size*size*10)/(size*size));
    };
    let best=forcedMask??-1;
    if(best<0){let lowest=Infinity;for(let mask=0;mask<8;mask++){apply(mask);format(mask);const score=penalty();if(score<lowest){lowest=score;best=mask;}apply(mask);}}
    apply(best);format(best);
    return {version,mask:best,modules};
  }
  function qrSvg(textValue){
    const {modules}=qrMatrix(textValue),size=modules.length,ns='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${size+8} ${size+8}`);svg.setAttribute('role','img');
    svg.setAttribute('aria-label',text('QR code du lien de téléchargement','QR code of the download link'));
    const background=document.createElementNS(ns,'rect');background.setAttribute('width',size+8);background.setAttribute('height',size+8);background.setAttribute('fill','#fff');
    const path=document.createElementNS(ns,'path');let d='';
    modules.forEach((row,y)=>row.forEach((dark,x)=>{if(dark)d+=`M${x+4} ${y+4}h1v1h-1z`;}));
    path.setAttribute('d',d);path.setAttribute('fill','#000');svg.append(background,path);return svg;
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
    if(['qbittorrent','transmission'].includes(service.id))rows.push([text('Utilisateur','Username'),service.username],[text('Mot de passe','Password'),service.password,true]);
    else rows.push([text('Clé API','API key'),service.api_key,true]);
    rows.forEach(([label,value,secret])=>$('mobile-fields').append(field(label,value||'',secret)));
    $('mobile-copy-status').textContent='';
  }
  return {english,init,refresh,read,valid,report,mountMobile,buildArrControlExport,buildNzb360Export,buildQbRemoteServer,buildQbRemoteExport,
    javaPreferences,readJavaPreferences,zipStored,zipAes,readZipFiles,inspectNzb360Backup,mergeNzb360,mergeQbRemote,ZipPasswordError,qrMatrix};
})();
