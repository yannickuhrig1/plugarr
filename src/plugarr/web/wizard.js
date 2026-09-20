'use strict';

const $ = id => document.getElementById(id);
const E = (tag, text, cls) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
};

const EN = {
  qbUiTitle:'qBittorrent web interface', qbUiHelp:'VueTorrent replaces the qBittorrent interface with a more modern one, also handy on a phone. Sonarr, Radarr and mobile apps are not affected.', qbUiOrigin:'Original interface', qbUiVue:'VueTorrent', qbUiTradeoff:'The first qBittorrent start needs Internet to download VueTorrent (version pinned by PlugArr). It is then kept in the qBittorrent folder and survives restarts without Internet. To go back, choose the original interface and run the installation again.', qbUiShort:'qBittorrent interface',
  veilleTitle:'Watch page', veilleHelp:'A read-only page: free space, throughput, VPN exit, container CPU and memory. It runs inside the stack, survives a reboot even when nobody logs in, and can be read from a phone. It can neither stop nor change anything.', veilleEnable:'Install the watch page', veilleNote:'It asks for the console password. Without a password set, it only listens on this machine.', veillePort:'Watch port', veilleShort:'Watch', veilleOn:'Installed',
  setup:'INSTALLATION', local:'On your computer', localDescription:'Your settings stay in PlugArr.', tui:'Open terminal TUI', quit:'Close wizard', assistant:'Configuration assistant', demoNotice:'Demo mode — no real installation, no Docker calls.', existingNotice:'Existing installation detected: you can resume its settings or start fresh before confirming.', loading:'Loading your assistant…',
  step1:'STEP 01 / 06', step2:'STEP 02 / 06', step3:'STEP 03 / 06', step4:'STEP 04 / 06', step5:'STEP 05 / 06', step6:'STEP 06 / 06',
  servicesTitle:'Your stack, your way.', servicesIntro:'Check Docker, use the backup tools if needed, then choose your applications. PlugArr will add their dependencies.', selectionHelp:'Editable before installation',
  dockerCheck:'Docker availability', dockerChecking:'Checking…', refresh:'Refresh',
  backupTitle:'Back up an installation', backupHelp:'Includes the project, application settings and Docker volumes, never media.', backupSource:'Installation folder', backupDestination:'Destination archive', backupLive:'Live backup (risk of inconsistent databases)', backupRun:'Create backup',
  restoreTitle:'Restore a backup', restoreHelp:'Enter a local archive path. Its manifest is shown before anything is written.', restoreArchive:'PlugArr archive', restoreTarget:'New settings folder (optional)', restoreInspect:'Inspect archive', restoreConfirm:'I confirm restoration of this archive.', restoreRun:'Restore now',
  foldersTitle:'A place for every file.', foldersIntro:'These paths and this address refer to the computer running PlugArr.', platform:'Platform', projectName:'Docker stack name', dataRoot:'Media and downloads folder', dataHelp:'A shared folder preserves hardlinks where supported by the filesystem.', configRoot:'Application settings folder', username:'Service username', passwordHelp:'PlugArr generates the passwords.', host:'This machine’s address', hostHelp:'DNS name or IP address used in final links.', timezone:'Time zone', serviceLanguage:'Service language', projectFolder:'Project folder', containerIds:'Container IDs', pathCheck:'Test folder and hardlinks',
  vpnTitle:'Your download connection.', vpnIntro:'Use Gluetun to route selected download clients through your VPN provider.', noTorrent:'No download client selected: this step is not needed.', enableVpn:'Enable VPN', vpnHelp:'Your VPN credentials stay on this computer.', provider:'Provider', protocol:'Protocol', wireguardKey:'WireGuard private key', wireguardAddress:'WireGuard addresses (if required by your provider)', vpnUser:'OpenVPN username', vpnPassword:'OpenVPN password', location:'VPN locations', locationSearch:'Filter locations', locationManual:'Country or region', vpnPreserved:'Leave credentials empty to keep those of the same provider and protocol.', vpnTest:'Test disposable tunnel', vpnWarning:'Without a VPN, BitTorrent traffic will use this computer’s public IP address, visible to peers.', sabRouteTitle:'SABnzbd network route', sabRouteHelp:'SABnzbd talks to a Usenet server, not peers. A VPN is optional and does not replace SSL/TLS.', sabDirect:'Direct connection + provider SSL/TLS (recommended)', sabVpn:'Also route SABnzbd through the VPN', sabTradeoff:'The VPN hides the Usenet server from your ISP, but adds a Gluetun dependency and may reduce throughput.', sabRoute:'SABnzbd route', sabDirectShort:'Direct + SSL/TLS', sabVpnShort:'Via Gluetun + SSL/TLS', preferredTitle:'Preferred download client', preferredHelp:'Sonarr and Radarr use it first. The others stay declared as a fallback: without this choice, they would alternate between them on every download.', preferredShort:'Preferred client',
  qualityTitle:'The quality you want.', qualityIntro:'Recyclarr applies TRaSH profiles to Sonarr and Radarr.', noQuality:'Select Recyclarr with Sonarr or Radarr to use quality profiles.', qualityDefaults:'Choose one profile per application from all available templates, or keep the default profile.', loadProfiles:'Refresh available profiles', sizeDisclaimer:'Broad estimates only, not download limits. Actual size depends on duration, source, codec, audio tracks and the release found.',
  reviewTitle:'Check before you start.', reviewIntro:'Review applications, paths and operations. Nothing starts before your confirmation.', resumeTitle:'Existing installation', resumeYes:'Resume available settings and credentials', resumeNo:'Start fresh with the entered settings', resetTitle:'Clean up old settings', resetKeep:'Keep the old settings', resetDelete:'Delete these settings and start fresh', mediaSafe:'Media files are never deleted.', recheck:'Check again', confirm:'I confirm the settings and operations shown above.',
  progressTitle:'Your stack is taking shape.', progressIntro:'Keep PlugArr open during installation. Completed steps appear below.', logs:'Detailed log', reportTitle:'Access your applications', reportHelp:'Keep this report: it contains generated URLs and credentials.', application:'Application', password:'Password', indexerTitle:'Add indexers to Prowlarr', indexerSearch:'Search for an indexer', search:'Search', openAdmin:'Open administration', accessPage:'Open access page', downloadAccess:'Download access file', finish:'Finish and close', adminLink:'Open administration in a new tab', retry:'Review settings and try again', remember:'Use the web interface next time', back:'Back', next:'Continue',
  services:'Applications', folders:'Folders', vpn:'VPN', quality:'Quality', review:'Review', installation:'Installation', arr:'Automation', download:'Downloads', media:'Media libraries', ui:'Interfaces', selected:'applications selected', dependencies:'dependencies', plannedLinks:'links to configure', defaultProfile:'PlugArr default', profile:'Profile',
  checking:'Checking configuration…', install:'Confirm and install', simulate:'Run simulation', blocked:'Resolve the blocking checks before continuing.', demoCheck:'Checks are simulated. Docker availability has not been checked.', ready:'Ready for confirmation', running:'Installation in progress…', done:'Installation completed', partial:'Installation completed with wiring errors', error:'Installation interrupted', demoDone:'Simulation completed — nothing was installed.', idle:'Waiting to start',
  checkingTemplates:'Loading available profiles…', noTemplates:'Profiles could not be loaded. Keep the default profiles or try again.', templatesReady:'Available profiles loaded.', bundledProfiles:'Complete catalog bundled with this demo.', saving:'Saving your choice…', sessionMissing:'Session missing. Open the full URL shown in the terminal.', networkError:'Connection lost. Keep the PlugArr terminal open and try again.', noSelection:'Choose at least one application.', dockerRequired:'Docker must be available before installation.', switched:'Return to the terminal: the TUI is opening. Unsaved web entries were not transferred.', retryWarning:'Review the settings and run the checks again before retrying.', unavailable:'Unavailable', vpnOn:'Enabled', vpnOff:'Disabled', simulation:'SIMULATION', localBadge:'LOCAL', profile:'Profile', notInstalled:'The demo administration opens in a new tab. No service was installed.', progressError:'Progress temporarily unavailable. Reconnecting…', optional:'optional', qualityInherited:'Existing profile', sizeEstimate:'Indicative size', movie2h:'2-hour movie', episode45:'45-minute episode',
  dockerReady:'Docker is ready.', dockerBlocked:'Docker is unavailable. Fix the reported issue, then refresh.', checkingAction:'Checking…', pathOk:'Folder and hardlink test succeeded.', pathFailed:'The folder is writable, but hardlinks are unavailable.', backupWorking:'Creating backup… Keep this page open.', backupDone:'Backup created', restoreReading:'Reading archive…', restoreWorking:'Restoring… Keep this page open.', restoreDone:'Restoration completed. Reloading the assistant…', hotBackup:'This archive was created live; its databases may be inconsistent.', servicesInArchive:'services in archive',
  portForward:'port forwarding', portForwardReady:'Port forwarding locations only', noPortForward:'No port forwarding advertised', locations:'locations', placesSelected:'locations selected', noLocation:'No location selected', tunnelWorking:'Starting a disposable tunnel…', tunnelSuccess:'VPN tunnel test succeeded.', tunnelFailure:'VPN tunnel test failed.',
  resumeOrigin:'Previous installation', resumedSettings:'Settings resumed', resumedServices:'Credentials resumed', freshInstall:'Fresh configuration selected.', resetCandidates:'Existing settings concerned', resetEnabled:'These settings will be removed immediately before installation.', resetDisabled:'These settings will be kept.',
  puid:'PUID', pgid:'PGID', umask:'UMASK', address:'Address', projectPath:'Project path', envFile:'.env file',
  reportLoading:'Loading final report…', indexersAvailable:'indexer definitions available', configured:'Configured', noneConfigured:'No indexer configured yet.', noIndexerResult:'No matching indexer.', addIndexer:'Add this indexer', addingIndexer:'Adding indexer…', indexerAdded:'Indexer added.', mirrors:'Known mirrors', accessOpening:'Preparing the access page…', accessDownloading:'Preparing the access file…', accessDownloaded:'Access file downloaded.', popupBlocked:'The browser blocked the new tab. Allow pop-ups and try again.', adminWaiting:'Opening administration…', adminOpened:'Administration opened in another tab. You can keep this installation summary open.', adminBlocked:'Use the link below to open administration in a new tab.', closed:'Assistant closed. You can close this tab.',
};

const FR = {
  qbUiShort:'Interface de qBittorrent', veilleShort:'Veille', veilleOn:'Installée',
  services:'Applications', folders:'Dossiers', vpn:'VPN', quality:'Qualité', review:'Vérification', installation:'Installation', arr:'Automatisation', download:'Téléchargements', media:'Médiathèques', ui:'Interfaces', selected:'applications sélectionnées', dependencies:'dépendances', plannedLinks:'liens à configurer', defaultProfile:'Défaut PlugArr', profile:'Profil',
  checking:'Vérification de la configuration…', install:'Confirmer et installer', simulate:'Lancer la simulation', blocked:'Résolvez les contrôles bloquants avant de continuer.', demoCheck:'Les contrôles sont simulés. La disponibilité de Docker n’a pas été vérifiée.', ready:'Prêt pour confirmation', running:'Installation en cours…', done:'Installation terminée', partial:'Installation terminée avec des erreurs de câblage', error:'Installation interrompue', demoDone:'Simulation terminée — rien n’a été installé.', idle:'En attente de lancement',
  checkingTemplates:'Chargement des profils disponibles…', noTemplates:'Impossible de charger les profils. Conservez les profils par défaut ou réessayez.', templatesReady:'Profils disponibles chargés.', bundledProfiles:'Catalogue complet embarqué dans cette démo.', saving:'Enregistrement du choix…', sessionMissing:'Session absente. Ouvrez le lien complet affiché dans le terminal.', networkError:'Connexion perdue. Gardez le terminal PlugArr ouvert, puis réessayez.', noSelection:'Choisissez au moins une application.', dockerRequired:'Docker doit être disponible avant l’installation.', switched:'Retournez au terminal : le TUI s’ouvre. Les saisies web non enregistrées ne sont pas transférées.', retryWarning:'Relisez les réglages et relancez les vérifications avant de réessayer.', unavailable:'Indisponible', vpnOn:'Activé', vpnOff:'Désactivé', simulation:'SIMULATION', localBadge:'LOCAL', profile:'Profil', notInstalled:'La console de démonstration s’ouvre dans un nouvel onglet. Aucun service n’a été installé.', progressError:'Progression momentanément indisponible. Reconnexion…', optional:'facultatif', qualityInherited:'Profil existant', sizeEstimate:'Taille indicative', movie2h:'film de 2 h', episode45:'épisode de 45 min',
  dockerReady:'Docker est prêt.', dockerBlocked:'Docker est indisponible. Corrigez le problème indiqué, puis actualisez.', checkingAction:'Contrôle en cours…', pathOk:'Le dossier et les liens physiques fonctionnent.', pathFailed:'Le dossier est accessible, mais les liens physiques ne sont pas disponibles.', backupWorking:'Sauvegarde en cours… Gardez cette page ouverte.', backupDone:'Sauvegarde créée', restoreReading:'Lecture de l’archive…', restoreWorking:'Restauration en cours… Gardez cette page ouverte.', restoreDone:'Restauration terminée. Rechargement de l’assistant…', hotBackup:'Cette archive a été créée à chaud ; ses bases peuvent être incohérentes.', servicesInArchive:'services dans l’archive',
  portForward:'redirection de port', portForwardReady:'Localisations compatibles avec la redirection de port', noPortForward:'Aucune redirection de port annoncée', locations:'localisations', placesSelected:'localisations sélectionnées', noLocation:'Aucune localisation sélectionnée', tunnelWorking:'Démarrage d’un tunnel jetable…', tunnelSuccess:'Le test du tunnel VPN a réussi.', tunnelFailure:'Le test du tunnel VPN a échoué.',
  resumeOrigin:'Installation précédente', resumedSettings:'Réglages repris', resumedServices:'Identifiants repris', freshInstall:'Nouvelle configuration sélectionnée.', resetCandidates:'Configurations existantes concernées', resetEnabled:'Ces configurations seront supprimées juste avant l’installation.', resetDisabled:'Ces configurations seront conservées.',
  puid:'PUID', pgid:'PGID', umask:'UMASK', address:'Adresse', projectPath:'Dossier du projet', envFile:'Fichier .env',
  reportLoading:'Chargement du rapport final…', indexersAvailable:'définitions d’indexeurs disponibles', configured:'Configurés', noneConfigured:'Aucun indexeur configuré pour le moment.', noIndexerResult:'Aucun indexeur correspondant.', addIndexer:'Ajouter cet indexeur', addingIndexer:'Ajout de l’indexeur…', indexerAdded:'Indexeur ajouté.', mirrors:'Miroirs connus', accessOpening:'Préparation de la page d’accès…', accessDownloading:'Préparation du fichier d’accès…', accessDownloaded:'Fichier d’accès téléchargé.', popupBlocked:'Le navigateur a bloqué le nouvel onglet. Autorisez les fenêtres pop-up puis réessayez.', adminWaiting:'Ouverture de l’administration…', adminOpened:'L’administration est ouverte dans un autre onglet. Vous pouvez conserver ce récapitulatif.', adminBlocked:'Utilisez le lien ci-dessous pour ouvrir l’administration dans un nouvel onglet.', closed:'Assistant fermé. Vous pouvez fermer cet onglet.',
  sabRoute:'Trajet SABnzbd', sabDirectShort:'Direct + SSL/TLS', sabVpnShort:'Via Gluetun + SSL/TLS', preferredShort:'Client préféré',
};

document.querySelectorAll('[data-i18n]').forEach(element => {
  FR[element.dataset.i18n] = element.textContent;
});
// Les placeholders aussi : sans cette ligne, FR n'avait aucune entree pour
// `locationSearch` ni `locationManual`, et tr() retombait sur la CLE. Les deux
// champs de recherche de localisation VPN affichaient « locationSearch » et
// « locationManual » a l'utilisateur francais.
document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
  FR[element.dataset.i18nPlaceholder] = element.placeholder;
});

let lang = 'fr';
let step = 0;
let bootstrap;
let form;
let effective = [];
let selectionMeta = {};
let plan = null;
let busy = false;
let startupReady = false;
let installed = false;
let lastProgress = null;
let polling = null;
let templatesLoaded = false;
let restoreInspection = null;
let reportData = null;
let postInstallLoaded = false;
let demoAdminOpened = false;
let adminOpening = false;
let adminUrl = null;
let graphView;
let graphSnapshot = null;
let graphRequest = 0;
let graphTimer;
let selectionRequest = 0;
let liveController;

const GRAPH_LABELS = {
  fr: {graphe:'Carte des connexions',prevu:'Prévu',actif:'Étape en cours',fait:'Étape réussie',echoue:'Étape échouée',avertissement:'À vérifier',configure:'Configuré, non testé',etapes:'étapes traitées',colonnes:{indexeurs:'Indexeurs',arr:'Automatisation',telechargement:'Téléchargements',vpn:'VPN',media:'Médiathèques'},preview:'Plan selon votre sélection. Aucun lien n’est encore présenté comme vérifié.',live:'Mise à jour en direct par PlugArr. Les animations représentent les résultats des étapes, pas le trafic réseau.',demo:'Démonstration : tous les états et animations sont simulés.',disconnected:'Connexion interrompue : derniers états reçus affichés. Reconnexion en cours…',updating:'Mise à jour du plan…',failed:'Impossible d’actualiser le graphe. Réessayez une sélection.',details:'Avancement par application',finished:'Résultats de l’installation. Les liaisons de configuration ne constituent pas un test réseau.'},
  en: {graphe:'Connection map',prevu:'Planned',actif:'Step running',fait:'Step succeeded',echoue:'Step failed',avertissement:'Check required',configure:'Configured, untested',etapes:'steps processed',colonnes:{indexeurs:'Indexers',arr:'Automation',telechargement:'Downloads',vpn:'VPN',media:'Media libraries'},preview:'Plan based on your selection. No link is claimed to be verified yet.',live:'Live updates from PlugArr. Animations represent step results, not network traffic.',demo:'Demonstration: all statuses and animations are simulated.',disconnected:'Connection interrupted: showing the last received statuses. Reconnecting…',updating:'Updating the plan…',failed:'Could not update the graph. Try changing the selection again.',details:'Progress by application',finished:'Installation results. Configuration links are not network tests.'},
};

const tr = key => (lang === 'en' ? EN : FR)[key] || FR[key] || key;
Object.assign(EN, globalThis.PlugArrRemote?.english || {});
FR.remote = 'Accès à distance'; EN.remote = 'Remote access';
Object.assign(FR, {
  backupChooseFile:'Choisissez d’abord un fichier de sauvegarde.', backupUploading:'Lecture de la sauvegarde…',
  backupNone:'Aucun indexeur dans cette sauvegarde.', backupFound:'indexeur(s) trouvé(s)', backupImportable:'à importer',
  backupStatusConfigured:'déjà configuré', backupStatusUnknown:'définition absente de ce Prowlarr', backupStatusImportable:'importable',
  backupDisabled:'désactivé', backupIgnored:'Laissés de côté, volontairement', backupSourcePlugarr:'Archive PlugArr', backupSourceProwlarr:'Sauvegarde Prowlarr', backupSourceBase:'Base Prowlarr',
  backupIgnoredapplications:'applications', backupIgnoreddownload_clients:'clients de téléchargement', backupIgnoredproxies:'proxys', backupIgnorednotifications:'notifications',
  backupImporting:'Import', backupSelectNone:'Cochez au moins un indexeur.', backupDone:'Import terminé',
});
Object.assign(EN, {
  backupImportTitle:'Import indexers from a backup', backupImportHelp:'Prowlarr backup (.zip) or PlugArr archive. Only indexers are imported: the links to qBittorrent, Sonarr and Radarr stay those of this installation.',
  backupFile:'Backup file', backupInspect:'Inspect', backupImport:'Import selection',
  backupChooseFile:'Choose a backup file first.', backupUploading:'Reading backup…',
  backupNone:'No indexer in this backup.', backupFound:'indexer(s) found', backupImportable:'to import',
  backupStatusConfigured:'already configured', backupStatusUnknown:'definition missing from this Prowlarr', backupStatusImportable:'importable',
  backupDisabled:'disabled', backupIgnored:'Deliberately left out', backupSourcePlugarr:'PlugArr archive', backupSourceProwlarr:'Prowlarr backup', backupSourceBase:'Prowlarr database',
  backupIgnoredapplications:'applications', backupIgnoreddownload_clients:'download clients', backupIgnoredproxies:'proxies', backupIgnorednotifications:'notifications',
  backupImporting:'Importing', backupSelectNone:'Tick at least one indexer.', backupDone:'Import finished',
});
let token = new URLSearchParams(location.hash.slice(1)).get('token');
try {
  if (token) sessionStorage.setItem('plugarr-wizard-token', token);
  else token = sessionStorage.getItem('plugarr-wizard-token');
} catch (_) { /* La session reste utilisable en memoire. */ }
if (location.hash) history.replaceState(null, '', location.pathname);

async function request(path, body, asText = false) {
  let response;
  // Un fichier part tel quel : la sauvegarde peut peser une centaine de Mo et
  // n'a rien a faire dans du JSON.
  const raw = body instanceof Blob;
  try {
    response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {Authorization:'Bearer ' + (token || ''), ...(body === undefined ? {} : {'Content-Type': raw ? 'application/octet-stream' : 'application/json'})},
      ...(body === undefined ? {} : {body: raw ? body : JSON.stringify(body)}),
    });
  } catch (_) {
    throw new Error(tr('networkError'));
  }
  if (asText && response.ok) return response.text();
  let data;
  try { data = await response.json(); }
  catch (_) { data = {error:tr('unavailable')}; }
  if (!response.ok) throw new Error(data.error || tr('unavailable'));
  return data;
}
const api = (path, body) => request(path, body, false);
const apiText = path => request(path, undefined, true);

function error(message) {
  $('error').hidden = !message;
  $('error').textContent = message || '';
  if (message) $('error').scrollIntoView({block:'nearest'});
}

function displayGraph(snapshot) {
  if (!snapshot?.graph || !bootstrap) return;
  graphSnapshot = snapshot;
  if (!graphView) graphView = new window.PlugArrGraphe.Vue($('graph-canvas'), $('graph-count'), $('graph-bar'), $('graph-state-list'));
  const labels = GRAPH_LABELS[lang];
  graphView.appliquer(snapshot, bootstrap.icons, labels, lang);
  $('wiring-graph').classList.remove('disconnected');
  $('graph-title').textContent = labels.graphe;
  $('graph-details-title').textContent = labels.details;
  $('graph-status').textContent = labels[snapshot.status === 'idle' ? 'preview' : snapshot.status === 'running' ? 'live' : 'finished'] + (snapshot.demo ? ' ' + labels.demo : '');
  $('graph-legend').replaceChildren(...[['prevu',''],['actif','running'],['fait','done'],['echoue','failed'],['configure','structural']].map(([key, cls]) => E('span', labels[key], cls)));
}

function scheduleGraph() {
  if (!bootstrap || installed || step >= 4) return;
  clearTimeout(graphTimer);
  const revision = ++graphRequest;
  $('graph-status').textContent = GRAPH_LABELS[lang].updating;
  $('wiring-graph').classList.add('disconnected');
  graphTimer = setTimeout(async () => {
    try {
      const snapshot = await api('/api/graph', {services:form.services, language:$('language').value || form.language, vpn_enabled:$('vpn-enabled').checked, protect_sabnzbd:document.querySelector('input[name="sab-route"]:checked')?.value === 'vpn'});
      if (revision === graphRequest && !installed && step < 4) displayGraph(snapshot);
    } catch (_) {
      if (revision === graphRequest) $('graph-status').textContent = GRAPH_LABELS[lang].failed;
    }
  }, 100);
}

function setBusy(value) {
  busy = value;
  $('next').disabled = value || (step === 0 && !startupReady) || (step === 5 && (!plan?.plan_id || !$('confirm').checked));
  $('back').disabled = value;
  $('recheck').disabled = value;
}

function translate() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(element => { element.textContent = tr(element.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(element => { element.placeholder = tr(element.dataset.i18nPlaceholder); });
  $('mode').textContent = tr(bootstrap?.demo ? 'simulation' : 'localBadge');
  if (graphSnapshot) displayGraph(graphSnapshot);
  if (bootstrap) {
    renderSteps();
    renderServices();
    updateConditional();
    updatePlatformInfo();
    updatePlaces();
    refreshProfileEstimates();
    renderResumeControls();
    if (plan) renderReview();
    if (reportData) renderReport(reportData);
    if (lastProgress) renderProgress(lastProgress);
    updateButtons();
  }
}

function renderSteps() {
  $('steps').replaceChildren();
  ['services','folders','vpn','quality','remote','review','installation'].forEach((key, index) => {
    const item = E('li', undefined, index === step ? 'current' : index < step ? 'completed' : '');
    if (index === step) item.setAttribute('aria-current', 'step');
    item.append(E('span', index < step ? '✓' : String(index + 1).padStart(2, '0'), 'step-number'), E('span', tr(key), 'step-label'));
    $('steps').append(item);
  });
  document.querySelectorAll('.step-panel .eyebrow').forEach((el, index) => { el.textContent = `${lang === 'fr' ? 'ÉTAPE' : 'STEP'} ${String(index + 1).padStart(2,'0')} / 07`; });
}

function updateButtons() {
  $('back').hidden = step === 0 || step === 6;
  $('footer').hidden = step === 6;
  $('next').textContent = step === 5 ? tr(bootstrap.demo ? 'simulate' : 'install') : tr('next');
  $('remember').closest('label').hidden = bootstrap.demo;
  setBusy(busy);
}

function showStep(index) {
  step = index;
  document.querySelectorAll('.step-panel').forEach(element => { element.hidden = Number(element.dataset.step) !== index; });
  error('');
  renderSteps();
  updateConditional();
  updateButtons();
  const panel = document.querySelector(`.step-panel[data-step="${index}"]`);
  panel.insertBefore($('wiring-graph'), panel.children[3] || null);
  $('wiring-graph').hidden = index === 4;
  if (index < 4) scheduleGraph();
  if (index === 3 && !templatesLoaded && !$('quality-controls').hidden) loadTemplates();
  if (index === 4) globalThis.PlugArrRemote?.refresh(effective);
  document.querySelector(`.step-panel[data-step="${index}"] h1`)?.focus({preventScroll:true});
}

function profileEstimate(service, name) {
  const id = (name || '').toLowerCase();
  if (!id) return null;
  let film = '4–15 GB', episode = '1.5–6 GB', quality = '1080p WEB / Blu-ray';
  const is2160 = id.includes('2160p') || id.includes('uhd') || /^sqp-[2-5]/.test(id);
  const isRemux = id.includes('remux');
  if (is2160 && isRemux) { film = '35–100 GB'; episode = '13–38 GB'; quality = '4K Remux / WEB'; }
  else if (is2160) { film = '12–40 GB'; episode = '5–15 GB'; quality = '4K WEB / Blu-ray'; }
  else if (isRemux) { film = '15–40 GB'; episode = '6–15 GB'; quality = '1080p Remux / WEB'; }
  if (lang === 'fr') { film = film.replace('GB', 'Go'); episode = episode.replace('GB', 'Go'); }
  return {quality, size:service === 'radarr' ? `${film} / ${tr('movie2h')}` : `${episode} / ${tr('episode45')}`};
}

function profileOption(service, name) {
  const option = new Option(name || tr('defaultProfile'), name);
  option.dataset.profileName = name;
  const estimate = profileEstimate(service, name);
  if (estimate) option.textContent = `${name} — ${estimate.size}`;
  return option;
}

function refreshProfileEstimate(service) {
  const select = $('quality-' + service), detail = $('quality-size-' + service);
  if (!select || !detail) return;
  for (const option of select.options) {
    const name = option.dataset.profileName;
    if (name !== undefined) {
      const estimate = profileEstimate(service, name);
      option.textContent = estimate ? `${name} — ${estimate.size}` : tr('defaultProfile');
    }
  }
  const estimate = profileEstimate(service, select.value);
  detail.textContent = estimate ? `${tr('sizeEstimate')} : ${estimate.size} · ${estimate.quality}` : tr('sizeDisclaimer');
}
function refreshProfileEstimates() { for (const service of ['sonarr','radarr']) refreshProfileEstimate(service); }

function renderServices() {
  const target = $('services');
  target.replaceChildren();
  for (const category of ['arr','download','media','ui']) {
    const list = bootstrap.catalog.filter(service => service.category === category);
    if (!list.length) continue;
    target.append(E('h2', tr(category), 'category-title'));
    const grid = E('div', undefined, 'service-grid');
    for (const service of list) {
      const label = E('label', undefined, 'service-card');
      const icon = bootstrap.icons[service.id];
      if (icon) {
        const image = E('img'); image.src = icon; image.alt = ''; image.width = 38; image.height = 38; label.append(image);
      } else label.append(E('span', service.name.slice(0, 1), 'initial'));
      label.append(E('span', service.name, 'service-name'));
      const input = E('input'); input.type = 'checkbox'; input.value = service.id; input.checked = form.services.includes(service.id); input.setAttribute('aria-label', service.name);
      input.addEventListener('change', async () => {
        form.services = [...target.querySelectorAll('input:checked')].map(element => element.value);
        plan = null;
        await refreshSelection();
        updateConditional();
        scheduleGraph();
      });
      label.append(input, E('p', service.notes));
      if (service.experimental) label.append(E('p', service.experimental, 'experimental'));
      grid.append(label);
    }
    target.append(grid);
  }
  updateSelection();
}

function updateSelection() {
  $('selection-count').textContent = `${form.services.length} ${tr('selected')}`;
  const dependencies = Math.max(0, (selectionMeta.effective_count || effective.length) - form.services.length);
  $('dependency-count').textContent = `${dependencies} ${tr('dependencies')} · ${selectionMeta.planned_links || 0} ${tr('plannedLinks')}`;
}

async function refreshSelection() {
  const revision = ++selectionRequest;
  const data = await api('/api/selection', {services:form.services});
  if (revision !== selectionRequest) return;
  selectionMeta = data;
  effective = data.services;
  updateSelection();
}

function selectedPlaces() {
  return [...$('vpn-places').querySelectorAll('input:checked')].map(element => element.value);
}

function readVpnFields() {
  const provider = bootstrap.providers[$('vpn-provider').value];
  const countries = provider?.choices?.length ? selectedPlaces().join(',') : $('vpn-manual-countries').value.trim();
  return {
    enabled:$('vpn-enabled').checked,
    provider:$('vpn-provider').value,
    vpn_type:$('vpn-type').value,
    wireguard_private_key:$('vpn-key').value,
    wireguard_addresses:$('vpn-addresses').value,
    openvpn_user:$('vpn-user').value,
    openvpn_password:$('vpn-password').value,
    protect_sabnzbd:document.querySelector('input[name="sab-route"]:checked')?.value === 'vpn',
    countries,
  };
}

function readFields() {
  form.remote_access = globalThis.PlugArrRemote?.read(effective) || {mode:'local',domain:'',services:[]};
  for (const id of ['platform','project_name','data_root','config_root','username','host','timezone','language']) form[id] = $(id).value;
  form.ui_language = lang;
  form.vpn = readVpnFields();
  if (!effective.includes('sabnzbd')) form.vpn.protect_sabnzbd = false;
  form.qbittorrent_ui = effective.includes('qbittorrent')
    ? (document.querySelector('input[name="qbittorrent-ui"]:checked')?.value || '')
    : '';
  form.veille_enabled = $('veille-enabled').checked;
  form.veille_port = Number($('veille-port').value) || 7374;
  form.client_prefere = competingClients().length
    ? (document.querySelector('input[name="preferred-client"]:checked')?.value || '')
    : '';
  if (!effective.some(service => bootstrap.download_clients.includes(service))) form.vpn.enabled = false;
  form.recyclarr_templates = {};
  if (effective.includes('recyclarr')) {
    for (const service of ['sonarr','radarr']) {
      const select = $('quality-' + service);
      if (effective.includes(service) && select?.value) form.recyclarr_templates[service] = select.value;
    }
  }
  const resume = document.querySelector('input[name="resume"]:checked');
  if (bootstrap.existing && resume) form.reprendre = resume.value === 'yes';
  const reset = document.querySelector('input[name="reset"]:checked');
  form.reset_config = Boolean(reset && reset.value === 'delete');
}

function updatePlatformInfo() {
  const profile = bootstrap.profiles[$('platform').value];
  if (!profile) return;
  $('ids-summary').textContent = `${profile.puid}:${profile.pgid}`;
  $('ids-detail').textContent = profile.ids_source + (profile.ids_certain ? '' : ' · ' + tr('unavailable'));
}

function fillFields() {
  for (const id of ['platform','project_name','data_root','config_root','username','host','timezone','language']) $(id).value = form[id];
  $('vpn-provider').replaceChildren(...Object.entries(bootstrap.providers).map(([provider, details]) => new Option(details.port_forward ? `${provider} · ${tr('portForward')}` : provider, provider)));
  if (![...$('vpn-provider').options].some(option => option.value === form.vpn.provider)) form.vpn.provider = Object.keys(bootstrap.providers)[0] || '';
  $('vpn-enabled').checked = form.vpn.enabled;
  const sabRoute = document.querySelector(`input[name="sab-route"][value="${form.vpn.protect_sabnzbd ? 'vpn' : 'direct'}"]`);
  if (sabRoute) sabRoute.checked = true;
  const qbUi = document.querySelector(`input[name="qbittorrent-ui"][value="${form.qbittorrent_ui || ''}"]`);
  if (qbUi) qbUi.checked = true;
  $('veille-enabled').checked = !!form.veille_enabled;
  $('veille-port').value = form.veille_port || 7374;
  $('vpn-provider').value = form.vpn.provider;
  $('vpn-type').value = form.vpn.vpn_type;
  $('vpn-key').value = form.vpn.wireguard_private_key;
  $('vpn-addresses').value = form.vpn.wireguard_addresses;
  $('vpn-user').value = form.vpn.openvpn_user;
  $('vpn-password').value = form.vpn.openvpn_password;
  $('project-dir').textContent = bootstrap.project_dir;
  $('backup-source').value = bootstrap.backup.source || bootstrap.project_dir;
  $('backup-destination').value = bootstrap.backup.destination || `${bootstrap.project_dir}/plugarr-backup.zip`;
  $('vpn-preserved').hidden = !bootstrap.existing || !bootstrap.form.vpn.enabled;
  for (const service of ['sonarr','radarr']) {
    const label = E('label'); label.id = 'quality-label-' + service; label.append(E('span', service === 'sonarr' ? 'Sonarr' : 'Radarr'));
    const select = E('select'); select.id = 'quality-' + service; select.append(profileOption(service, ''));
    const existing = form.recyclarr_templates[service];
    if (existing) { select.append(profileOption(service, existing)); select.value = existing; }
    const detail = E('small', tr('sizeDisclaimer'), 'profile-size'); detail.id = 'quality-size-' + service;
    select.addEventListener('change', () => refreshProfileEstimate(service));
    label.append(select, detail); $('quality-fields').append(label); refreshProfileEstimate(service);
  }
  updatePlatformInfo();
  updatePlaces();
  renderResumeControls();
}

function updatePlaceSummary() {
  const provider = bootstrap.providers[$('vpn-provider').value];
  const count = provider?.choices?.length ? selectedPlaces().length : ($('vpn-manual-countries').value.trim() ? 1 : 0);
  $('vpn-place-summary').textContent = count ? `${count} ${tr('placesSelected')}` : tr('noLocation');
}

function filterPlaces() {
  const query = $('vpn-place-search').value.trim().toLocaleLowerCase(lang);
  for (const label of $('vpn-places').children) label.hidden = Boolean(query) && !label.textContent.toLocaleLowerCase(lang).includes(query);
}

function updatePlaces(reset = false) {
  const provider = bootstrap.providers[$('vpn-provider').value];
  const target = $('vpn-places');
  const previous = reset ? [] : (target.children.length ? selectedPlaces() : String(form.vpn.countries || '').split(',').map(value => value.trim()).filter(Boolean));
  target.replaceChildren();
  const choices = provider?.choices || [];
  for (const place of choices) {
    const label = E('label', undefined, 'place-choice');
    const input = E('input'); input.type = 'checkbox'; input.value = place; input.checked = previous.includes(place); input.addEventListener('change', updatePlaceSummary);
    label.append(input, E('span', place)); target.append(label);
  }
  $('vpn-place-search').hidden = !choices.length;
  target.hidden = !choices.length;
  $('vpn-manual-countries').hidden = Boolean(choices.length);
  if (!choices.length && !reset) $('vpn-manual-countries').value = form.vpn.countries || '';
  if (reset) $('vpn-manual-countries').value = '';
  $('places-label').textContent = lang === 'fr' && provider?.label ? provider.label : tr('location');
  $('vpn-provider-note').textContent = provider ? `${provider.port_forward ? tr('portForwardReady') : tr('noPortForward')} · Gluetun ${provider.version} · ${choices.length}/${provider.total} ${tr('locations')}` : '';
  $('vpn-place-search').value = '';
  updatePlaceSummary();
}

// Clients qui se disputent un meme protocole : c'est la seule situation ou
// les *arr alterneraient entre eux. La regle vit cote Python
// (`downloadclients.concurrents`) ; seul le regroupement est refait ici, sur
// les donnees fournies par le serveur.
function competingClients() {
  const groups = {};
  for (const service of bootstrap.download_order || []) {
    if (effective.includes(service)) (groups[bootstrap.client_protocols[service]] ??= []).push(service);
  }
  return Object.values(groups).filter(group => group.length > 1).flat();
}

function renderPreferred() {
  const competing = competingClients();
  $('preferred-client').hidden = competing.length === 0;
  if (!competing.length) return;
  if (!competing.includes(form.client_prefere)) form.client_prefere = competing[0];
  $('preferred-options').replaceChildren(...competing.map(service => {
    const input = E('input');
    input.type = 'radio';
    input.name = 'preferred-client';
    input.value = service;
    input.checked = service === form.client_prefere;
    input.addEventListener('change', () => { form.client_prefere = service; scheduleGraph(); });
    const label = E('label');
    label.append(input, E('span', bootstrap.catalog.find(entry => entry.id === service)?.name || service));
    return label;
  }));
}

function updateConditional() {
  const hasDownload = effective.some(service => bootstrap.download_clients.includes(service));
  const hasTorrent = effective.some(service => bootstrap.torrent_clients.includes(service));
  const hasSabnzbd = effective.includes('sabnzbd');
  $('no-torrent').hidden = hasDownload;
  $('vpn-controls').hidden = !hasDownload;
  $('sab-route').hidden = !hasSabnzbd;
  $('qbittorrent-ui').hidden = !effective.includes('qbittorrent');
  renderPreferred();
  $('vpn-fields').hidden = !$('vpn-enabled').checked;
  $('vpn-warning').hidden = !hasTorrent || $('vpn-enabled').checked;
  $('wireguard-fields').hidden = $('vpn-type').value !== 'wireguard';
  $('openvpn-fields').hidden = $('vpn-type').value !== 'openvpn';
  const hasQuality = effective.includes('recyclarr') && effective.some(service => ['sonarr','radarr'].includes(service));
  $('no-quality').hidden = hasQuality;
  $('quality-controls').hidden = !hasQuality;
  for (const service of ['sonarr','radarr']) if ($('quality-label-' + service)) $('quality-label-' + service).hidden = !effective.includes(service);
}

function renderResumeControls() {
  $('resume-box').hidden = !bootstrap.existing;
  if (!bootstrap.existing) return;
  $('resume-origin').textContent = `${tr('resumeOrigin')} : ${bootstrap.existing_project_dir}`;
  const choice = document.querySelector(`input[name="resume"][value="${form.reprendre ? 'yes' : 'no'}"]`);
  if (choice) choice.checked = true;
}

function summaryBox(label, value) {
  const box = E('div', undefined, 'summary-box');
  box.append(E('span', label), E('strong', String(value)));
  return box;
}

function renderReview() {
  const target = $('review');
  target.replaceChildren();
  const grid = E('div', undefined, 'summary-grid');
  grid.append(summaryBox(tr('remote'), plan.remote_access?.mode === 'https' ? `HTTPS · ${plan.remote_access.domain}` : plan.remote_access?.mode === 'tailscale' ? 'Tailscale' : 'Local'));
  for (const [label, value] of [
    [tr('projectName'), plan.project_name], [tr('projectPath'), plan.project_dir], [tr('address'), plan.host], [tr('vpn'), tr(plan.vpn ? 'vpnOn' : 'vpnOff')],
    ...(plan.sabnzbd_route ? [[tr('sabRoute'), tr(plan.sabnzbd_route === 'vpn' ? 'sabVpnShort' : 'sabDirectShort')]] : []),
    ...(plan.qbittorrent_ui ? [[tr('qbUiShort'), tr('qbUiVue')]] : []),
    ...(plan.veille_enabled ? [[tr('veilleShort'), `${tr('veilleOn')} · ${plan.veille_port}`]] : []),
    ...(plan.client_prefere ? [[tr('preferredShort'), bootstrap.catalog.find(entry => entry.id === plan.client_prefere)?.name || plan.client_prefere]] : []),
    [tr('dataRoot'), plan.data_root], [tr('configRoot'), plan.config_root], [`${tr('puid')}:${tr('pgid')}`, `${plan.puid}:${plan.pgid}`], [`${tr('umask')} / TZ`, `${plan.umask} · ${plan.timezone}`],
  ]) grid.append(summaryBox(label, value));
  target.append(grid, E('p', `${plan.planned_links} ${tr('plannedLinks')}`, 'metric-line'));
  if (plan.resume.enabled) {
    const resumed = E('div', undefined, 'notice');
    resumed.append(E('strong', `${tr('resumeOrigin')} : ${plan.resume.from}`));
    if (plan.resume.settings.length) resumed.append(E('p', `${tr('resumedSettings')} : ${plan.resume.settings.join(', ')}`));
    if (plan.resume.services.length) resumed.append(E('p', `${tr('resumedServices')} : ${plan.resume.services.join(', ')}`));
    target.append(resumed);
  } else if (bootstrap.existing) target.append(E('p', tr('freshInstall'), 'notice'));
  for (const service of plan.services) {
    const row = E('div', undefined, 'review-service'), left = E('div');
    left.append(E('strong', service.name), E('small', service.image));
    row.append(left, E('code', service.url || (service.port ? ':' + service.port : '—')));
    target.append(row);
  }
  for (const [service, name] of Object.entries(plan.recyclarr_templates)) target.append(E('p', `${tr('profile')} ${service} : ${name}`, 'muted'));
  for (const warning of plan.warnings) target.append(E('p', warning, 'notice warning'));
  if (plan.demo) target.append(E('p', tr('demoCheck'), 'notice demo'));
  const checks = E('ul', undefined, 'checks');
  for (const check of plan.checks) {
    const item = E('li', undefined, 'check');
    item.append(E('span', check.ok ? '✓' : check.blocking ? '×' : '!', check.ok ? 'ok' : 'fail'));
    const detail = E('div'); detail.append(E('strong', check.name), E('small', check.detail)); item.append(detail); checks.append(item);
  }
  target.append(checks, E('p', tr(plan.blocked ? 'blocked' : 'ready'), plan.blocked ? 'notice error' : 'muted'));
  $('reset-box').hidden = !plan.reset_candidates.length;
  if (plan.reset_candidates.length) {
    const locations = (plan.reset_locations || []).join(' · ');
    $('reset-detail').textContent = `${tr('resetCandidates')} : ${plan.reset_candidates.join(', ')}${locations ? ` — ${locations}` : ''}. ${tr(plan.reset_requested ? 'resetEnabled' : 'resetDisabled')}`;
    const reset = document.querySelector(`input[name="reset"][value="${form.reset_config ? 'delete' : 'keep'}"]`);
    if (reset) reset.checked = true;
  }
  $('confirm-label').hidden = plan.blocked;
}

async function validate() {
  readFields();
  plan = null;
  $('confirm').checked = false;
  setBusy(true);
  $('review').replaceChildren(E('p', tr('checking'), 'notice'));
  try {
    plan = await api('/api/validate', form);
    displayGraph({graph:plan.graph, graph_results:{}, status:'idle', demo:bootstrap.demo, deployed:false});
    renderReview();
  } catch (failure) {
    $('review').replaceChildren();
    error(failure.message);
  } finally { setBusy(false); }
}

async function checkStartup() {
  $('startup-refresh').disabled = true;
  $('startup-mark').textContent = '…';
  $('startup-mark').className = 'status-mark pending';
  $('startup-detail').textContent = tr('dockerChecking');
  try {
    const data = await api('/api/startup');
    startupReady = data.ok;
    $('startup-mark').textContent = data.ok ? '✓' : '×';
    $('startup-mark').className = 'status-mark ' + (data.ok ? 'ok-mark' : 'fail-mark');
    const details = data.checks.map(check => `${check.name} : ${check.detail}`).join(' · ');
    $('startup-detail').textContent = `${tr(data.ok ? 'dockerReady' : 'dockerBlocked')} ${details}`;
  } catch (failure) {
    startupReady = false;
    $('startup-mark').textContent = '×';
    $('startup-mark').className = 'status-mark fail-mark';
    $('startup-detail').textContent = failure.message;
  } finally {
    $('startup-refresh').disabled = false;
    updateButtons();
  }
}

async function checkPaths() {
  $('path-check').disabled = true;
  $('path-status').textContent = tr('checkingAction');
  try {
    const result = await api('/api/path-check', {platform:$('platform').value, data_root:$('data_root').value});
    $('path-status').textContent = `${result.ok ? '✓' : '!'} ${tr(result.ok ? 'pathOk' : 'pathFailed')} ${result.detail}${result.warning ? ' · ' + result.warning : ''}`;
    $('ids-summary').textContent = `${result.puid}:${result.pgid}`;
    $('ids-detail').textContent = result.ids_source + (result.ids_certain ? '' : ' · ' + tr('unavailable'));
  } catch (failure) { $('path-status').textContent = '× ' + failure.message; }
  finally { $('path-check').disabled = false; }
}

async function createBackup() {
  $('backup-run').disabled = true;
  $('backup-status').textContent = tr('backupWorking');
  try {
    const result = await api('/api/backup', {source:$('backup-source').value, destination:$('backup-destination').value, live:$('backup-live').checked});
    $('backup-status').textContent = `✓ ${tr('backupDone')} : ${result.archive} · ${result.files} fichiers · ${result.size_mb} Mo${result.stopped ? ' · conteneurs arrêtés puis relancés' : ''}`;
  } catch (failure) { $('backup-status').textContent = '× ' + failure.message; }
  finally { $('backup-run').disabled = false; }
}

function clearRestoreInspection() {
  restoreInspection = null;
  $('restore-summary').hidden = true;
  $('restore-confirm-label').hidden = true;
  $('restore-confirm').checked = false;
  $('restore-run').hidden = true;
  $('restore-run').disabled = true;
}

async function inspectRestore() {
  clearRestoreInspection();
  $('restore-inspect').disabled = true;
  $('restore-status').textContent = tr('restoreReading');
  try {
    const result = await api('/api/restore/inspect', {archive:$('restore-archive').value});
    restoreInspection = result.inspection_id;
    const manifest = result.manifest;
    const summary = $('restore-summary');
    summary.replaceChildren(
      E('strong', `${manifest.project_name} · ${manifest.date || '—'}`),
      E('span', `${(manifest.services || []).length} ${tr('servicesInArchive')} · ${(manifest.volumes || []).length} volumes`),
      E('code', manifest.config_root || '—'),
    );
    if (manifest.a_chaud) summary.append(E('span', tr('hotBackup'), 'warning-text'));
    summary.hidden = false;
    $('restore-confirm-label').hidden = false;
    $('restore-run').hidden = false;
    $('restore-status').textContent = '';
  } catch (failure) { $('restore-status').textContent = '× ' + failure.message; }
  finally { $('restore-inspect').disabled = false; }
}

async function restoreBackup() {
  if (!restoreInspection || !$('restore-confirm').checked) return;
  $('restore-run').disabled = true;
  $('restore-status').textContent = tr('restoreWorking');
  try {
    await api('/api/restore', {archive:$('restore-archive').value, target:$('restore-target').value, inspection_id:restoreInspection, confirm:true});
    $('restore-status').textContent = '✓ ' + tr('restoreDone');
    setTimeout(() => location.reload(), 500);
  } catch (failure) {
    $('restore-status').textContent = '× ' + failure.message;
    clearRestoreInspection();
  }
}

async function testVpn() {
  $('vpn-test').disabled = true;
  $('vpn-test-status').textContent = tr('tunnelWorking');
  try {
    const result = await api('/api/vpn-test', {vpn:readVpnFields()});
    $('vpn-test-status').textContent = `${result.ok ? '✓' : '×'} ${tr(result.ok ? 'tunnelSuccess' : 'tunnelFailure')} ${result.detail}`;
  } catch (failure) { $('vpn-test-status').textContent = '× ' + failure.message; }
  finally { $('vpn-test').disabled = false; }
}

function renderReport(report) {
  reportData = report;
  globalThis.PlugArrRemote?.report(report);
  const rows = report.services.map(service => {
    const row = E('tr');
    row.append(E('th', service.name));
    const urlCell = E('td');
    if (service.url) { const link = E('a', service.url); link.href = service.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; urlCell.append(link); }
    else urlCell.textContent = '—';
    row.append(urlCell);
    for (const value of [service.username, service.password, service.api_key]) { const cell = E('td'); cell.append(E('code', value)); row.append(cell); }
    return row;
  });
  $('report-services').replaceChildren(...rows);
  $('env-path').textContent = `${tr('envFile')} : ${report.env_path}`;
  $('next-steps').replaceChildren(...report.next_steps.map(item => E('li', item)));
}

function renderConfigured(names) {
  $('configured-indexers').replaceChildren(...names.map(name => E('span', name, 'chip')));
}

function renderIndexerOverview(overview) {
  $('indexer-panel').hidden = !overview.available;
  if (!overview.available) return;
  $('indexer-overview').textContent = `${overview.count} ${tr('indexersAvailable')}. ${overview.configured.length ? `${tr('configured')} : ${overview.configured.join(', ')}` : tr('noneConfigured')}`;
  renderConfigured(overview.configured);
}

function indexerCard(result) {
  const card = E('article', undefined, 'indexer-card');
  const heading = E('div', undefined, 'indexer-heading');
  heading.append(E('strong', result.name), E('span', `${result.protocol} · ${result.privacy}`, 'chip'));
  card.append(heading);
  if (result.description) card.append(E('p', result.description, 'muted'));
  if (result.mirrors.length) card.append(E('p', `${tr('mirrors')} : ${result.mirrors.join(' · ')}`, 'muted wrap-anywhere'));
  const fields = E('div', undefined, 'indexer-fields');
  for (const field of result.fields) {
    const label = E('label'); label.append(E('span', field.label));
    let input;
    if (field.name === 'baseUrl' && result.mirrors.length > 1) {
      input = E('select');
      input.append(...result.mirrors.map(url => new Option(url, url)));
      if (field.prefill) input.value = field.prefill;
    } else {
      input = E('input'); input.type = field.secret ? 'password' : 'text'; input.value = field.prefill || ''; input.autocomplete = 'off';
    }
    input.dataset.field = field.name;
    label.append(input); fields.append(label);
  }
  const add = E('button', tr('addIndexer'), 'secondary'); add.type = 'button';
  add.addEventListener('click', async () => {
    add.disabled = true; $('indexer-status').textContent = tr('addingIndexer');
    const values = Object.fromEntries([...fields.querySelectorAll('[data-field]')].map(input => [input.dataset.field, input.value]));
    try {
      const response = await api('/api/indexers/add', {key:result.key, values});
      $('indexer-status').textContent = `${response.ok ? '✓' : '×'} ${response.message || tr(response.ok ? 'indexerAdded' : 'unavailable')}`;
      renderConfigured(response.configured || []);
    } catch (failure) { $('indexer-status').textContent = '× ' + failure.message; }
    finally { add.disabled = false; }
  });
  card.append(fields, add);
  return card;
}

async function searchIndexers() {
  if (!$('indexer-query').reportValidity()) return;
  $('indexer-search').disabled = true;
  $('indexer-status').textContent = tr('checkingAction');
  try {
    const response = await api('/api/indexers/search', {query:$('indexer-query').value});
    $('indexer-results').replaceChildren(...(response.results.length ? response.results.map(indexerCard) : [E('p', tr('noIndexerResult'), 'notice')]));
    $('indexer-status').textContent = '';
  } catch (failure) { $('indexer-status').textContent = '× ' + failure.message; }
  finally { $('indexer-search').disabled = false; }
}

const BACKUP_SOURCES = {plugarr:'backupSourcePlugarr', prowlarr:'backupSourceProwlarr', base:'backupSourceBase'};
const BACKUP_STATUSES = {importable:'backupStatusImportable', configure:'backupStatusConfigured', inconnu:'backupStatusUnknown'};

function backupRow(indexer) {
  const row = E('label');
  const box = E('input'); box.type = 'checkbox';
  box.disabled = !indexer.key; box.checked = Boolean(indexer.key);
  if (indexer.key) box.dataset.key = indexer.key; else row.classList.add('unavailable');
  box.dataset.name = indexer.name;
  const status = E('span', tr(BACKUP_STATUSES[indexer.status] || 'unavailable'), 'chip');
  row.append(box, E('strong', indexer.name), E('small', indexer.definition + (indexer.enabled ? '' : ` · ${tr('backupDisabled')}`)), status);
  return row;
}

async function inspectIndexerBackup() {
  const file = $('indexer-backup-file').files[0];
  $('indexer-backup-list').replaceChildren();
  $('indexer-backup-import').hidden = true;
  if (!file) { $('indexer-backup-status').textContent = tr('backupChooseFile'); return; }
  $('indexer-backup-inspect').disabled = true;
  $('indexer-backup-status').textContent = tr('backupUploading');
  try {
    const response = await api('/api/indexers/backup', file);
    const importable = response.indexers.filter(indexer => indexer.key).length;
    $('indexer-backup-list').replaceChildren(...response.indexers.map(backupRow));
    $('indexer-backup-import').hidden = importable === 0;
    const ignored = Object.entries(response.ignored || {}).filter(([, count]) => count > 0).map(([name, count]) => `${count} ${tr('backupIgnored' + name)}`);
    $('indexer-backup-status').textContent = response.indexers.length
      ? `${tr(BACKUP_SOURCES[response.source])} : ${response.indexers.length} ${tr('backupFound')}, ${importable} ${tr('backupImportable')}.${ignored.length ? ` ${tr('backupIgnored')} : ${ignored.join(', ')}.` : ''}`
      : tr('backupNone');
  } catch (failure) { $('indexer-backup-status').textContent = '× ' + failure.message; }
  finally { $('indexer-backup-inspect').disabled = false; }
}

async function importIndexerBackup() {
  const boxes = [...$('indexer-backup-list').querySelectorAll('input[data-key]:checked')];
  if (!boxes.length) { $('indexer-backup-status').textContent = tr('backupSelectNone'); return; }
  $('indexer-backup-import').disabled = true; $('indexer-backup-inspect').disabled = true;
  const list = E('ul', undefined, 'backup-result');
  // Un indexeur a la fois : Prowlarr contacte chacun pour le valider, et un
  // tracker lent ne doit pas masquer l'avancement des autres.
  for (const [index, box] of boxes.entries()) {
    $('indexer-backup-status').textContent = `${tr('backupImporting')} ${index + 1}/${boxes.length} : ${box.dataset.name}…`;
    let line;
    try {
      const response = await api('/api/indexers/backup/import', {key:box.dataset.key});
      line = `${response.ok ? '✓' : '×'} ${response.name} : ${response.message}${response.warnings.length ? ` (${response.warnings.join(' ; ')})` : ''}`;
      if (response.ok) {
        const row = box.closest('label');
        box.checked = false; box.disabled = true; delete box.dataset.key;
        row.classList.add('unavailable'); row.querySelector('.chip').textContent = tr('backupStatusConfigured');
      }
      renderConfigured(response.configured || []);
    } catch (failure) { line = `× ${box.dataset.name} : ${failure.message}`; }
    list.append(E('li', line));
  }
  $('indexer-backup-status').replaceChildren(E('span', `${tr('backupDone')} :`), list);
  $('indexer-backup-import').hidden = !$('indexer-backup-list').querySelector('input[data-key]');
  $('indexer-backup-import').disabled = false; $('indexer-backup-inspect').disabled = false;
}

async function loadPostInstall() {
  $('post-install').hidden = false;
  $('env-path').textContent = tr('reportLoading');
  const [report, overview] = await Promise.all([api('/api/report'), api('/api/indexers')]);
  renderReport(report);
  renderIndexerOverview(overview);
  $('access-page').hidden = false;
  $('download-access').hidden = false;
  $('finish').hidden = false;
}

function renderProgress(data) {
  lastProgress = data;
  displayGraph(data);
  const complete = ['done','partial','error'].includes(data.status);
  installed = data.status === 'running' || complete;
  $('progress-state').textContent = tr(data.demo && data.status === 'done' ? 'demoDone' : data.status);
  $('progress-state').className = 'progress-state ' + (data.status === 'running' ? 'running' : '');
  $('progress-title').textContent = tr(data.demo && data.status === 'done' ? 'demoDone' : complete ? data.status : 'progressTitle');
  if (data.demo && complete) $('progress-description').textContent = tr('notInstalled');
  const recent = data.events.slice(-10);
  $('event-list').replaceChildren(...recent.map(event => {
    const item = E('li'); item.append(E('b', event.started ? '…' : event.ok ? '✓' : '×', event.started ? 'pending' : event.ok ? 'ok' : 'fail'));
    const text = E('div'); text.append(E('span', event.phase), E('small', event.message)); item.append(text); return item;
  }));
  $('logs').textContent = data.events.map(event => `${event.started ? 'EN COURS' : event.ok ? 'OK' : 'ERREUR'} · ${event.phase} · ${event.message}`).join('\n');
  $('admin').hidden = !['done','partial'].includes(data.status);
  $('retry').hidden = data.status !== 'error';
  $('tui').hidden = true;
  if (['done','partial'].includes(data.status) && !postInstallLoaded) {
    postInstallLoaded = true;
    loadPostInstall().catch(failure => { postInstallLoaded = false; error(failure.message); });
  }
  if (data.demo && data.status === 'done' && !demoAdminOpened) { demoAdminOpened = true; openAdmin(); }
  return complete;
}

async function poll() {
  liveController?.abort();
  liveController = new AbortController();
  const controller = liveController;
  try {
    const response = await fetch('/api/events', {headers:{Authorization:'Bearer ' + token}, signal:controller.signal});
    if (!response.ok || !response.body) throw new Error('stream');
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      buffer += decoder.decode(part.value, {stream:true});
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const message = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        if (!message.startsWith('data: ')) continue;
        const data = JSON.parse(message.slice(6)); error('');
        if (renderProgress(data)) { await reader.cancel(); return; }
      }
    }
  } catch (failure) {
    if (failure.name === 'AbortError') return;
    $('progress-state').textContent = tr('progressError');
    $('graph-status').textContent = GRAPH_LABELS[lang].disconnected;
    $('wiring-graph').classList.add('disconnected');
  }
  if (liveController === controller) polling = setTimeout(poll, 750);
}

async function loadTemplates() {
  if ($('load-templates').disabled) return;
  $('load-templates').disabled = true;
  $('template-status').textContent = tr('checkingTemplates');
  try {
    const data = await api('/api/templates');
    if (data.problem) throw new Error(tr('noTemplates'));
    for (const service of ['sonarr','radarr']) {
      const select = $('quality-' + service), old = select.value;
      select.replaceChildren(profileOption(service, ''), ...(data.names[service] || []).map(name => profileOption(service, name)));
      if (old && !data.names[service]?.includes(old)) select.append(profileOption(service, old));
      select.value = old; refreshProfileEstimate(service);
    }
    templatesLoaded = true;
    const counts = ['sonarr','radarr'].filter(service => effective.includes(service)).map(service => service.charAt(0).toUpperCase() + service.slice(1) + ' : ' + (data.names[service] || []).length).join(' · ');
    $('template-status').textContent = tr('templatesReady') + ' ' + counts + (data.bundled ? ' — ' + tr('bundledProfiles') : '');
  } catch (failure) { $('template-status').textContent = failure.message; }
  finally { $('load-templates').disabled = false; }
}

async function openAdmin() {
  if (adminOpening) return;
  adminOpening = true;
  let page = null;
  try {
    page = window.open('about:blank', '_blank');
    if (page) { page.opener = null; page.document.title = 'PlugArr — Administration'; page.document.body.textContent = tr('adminWaiting'); }
    adminUrl = adminUrl || (await api('/api/admin', {})).url;
    $('admin-link').href = adminUrl; $('admin-link').hidden = false;
    if (page && !page.closed) { page.location.replace(adminUrl); $('admin-notice').textContent = tr('adminOpened'); }
    else $('admin-notice').textContent = tr('adminBlocked');
  } catch (failure) {
    if (page && !page.closed) page.close();
    error(failure.message);
  } finally { adminOpening = false; }
}

async function openAccessPage() {
  const page = window.open('about:blank', '_blank');
  if (page) { page.opener = null; page.document.title = 'PlugArr — Accès'; page.document.body.textContent = tr('accessOpening'); }
  try {
    const html = await apiText('/api/access');
    const url = URL.createObjectURL(new Blob([html], {type:'text/html'}));
    if (!page || page.closed) { URL.revokeObjectURL(url); throw new Error(tr('popupBlocked')); }
    page.location.replace(url);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (failure) {
    if (page && !page.closed) page.close();
    error(failure.message);
  }
}

async function downloadAccessPage() {
  const button = $('download-access');
  button.disabled = true;
  $('admin-notice').textContent = tr('accessDownloading');
  try {
    const html = await apiText('/api/access');
    const url = URL.createObjectURL(new Blob([html], {type:'text/html'}));
    const link = E('a');
    link.href = url;
    link.download = 'acces-plugarr.html';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('admin-notice').textContent = tr('accessDownloaded');
  } catch (failure) {
    error(failure.message);
    $('admin-notice').textContent = '';
  } finally { button.disabled = false; }
}

async function closeWizard() {
  try {
    await api('/api/close', {});
    $('wizard').hidden = true;
    $('loading').hidden = false;
    $('loading').textContent = tr('closed');
  } catch (failure) { error(failure.message); }
}

$('wizard').noValidate = true;
$('wizard').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  error('');
  try {
    if (step === 0) {
      if (!startupReady) throw new Error(tr('dockerRequired'));
      if (!form.services.length) throw new Error(tr('noSelection'));
      setBusy(true); await refreshSelection(); setBusy(false);
    }
    if (step === 1) {
      for (const input of document.querySelectorAll('[data-step="1"] input, [data-step="1"] select')) if (!input.reportValidity()) return;
    }
    if (step < 5) {
      if (step === 4 && globalThis.PlugArrRemote && !globalThis.PlugArrRemote.valid()) return;
      readFields(); showStep(step + 1); if (step === 5) await validate(); return;
    }
    if (step === 5 && plan?.plan_id && $('confirm').checked) {
      setBusy(true);
      if ($('remember').checked && !bootstrap.demo) await api('/api/preference', {interface:'web'});
      await api('/api/install', {plan_id:plan.plan_id, confirm:true});
      installed = true; showStep(6); poll();
    }
  } catch (failure) { error(failure.message); }
  finally { setBusy(false); }
});

$('back').addEventListener('click', () => { if (!busy) { readFields(); plan = null; showStep(Math.max(0, step - 1)); } });
$('recheck').addEventListener('click', validate);
$('confirm').addEventListener('change', () => setBusy(busy));
$('language').addEventListener('change', scheduleGraph);
$('vpn-enabled').addEventListener('change', scheduleGraph);
$('platform').addEventListener('change', () => {
  if (!bootstrap.existing || !form.reprendre) {
    const defaults = bootstrap.profiles[$('platform').value];
    $('data_root').value = defaults.data_root; $('config_root').value = defaults.config_root;
  }
  updatePlatformInfo();
});
for (const id of ['vpn-enabled','vpn-type']) $(id).addEventListener('change', updateConditional);
for (const choice of document.querySelectorAll('input[name="sab-route"]')) choice.addEventListener('change', event => {
  if (event.target.value === 'vpn') $('vpn-enabled').checked = true;
  updateConditional(); scheduleGraph();
});
$('vpn-enabled').addEventListener('change', () => {
  if ($('vpn-enabled').checked && effective.includes('sabnzbd') && !effective.some(service => bootstrap.torrent_clients.includes(service))) {
    const tunnel = document.querySelector('input[name="sab-route"][value="vpn"]');
    if (tunnel) tunnel.checked = true;
  } else if (!$('vpn-enabled').checked) {
    const direct = document.querySelector('input[name="sab-route"][value="direct"]');
    if (direct) direct.checked = true;
  }
});
$('vpn-provider').addEventListener('change', () => { form.vpn.countries = ''; updatePlaces(true); });
$('vpn-place-search').addEventListener('input', filterPlaces);
$('vpn-manual-countries').addEventListener('input', updatePlaceSummary);
$('ui-language').addEventListener('change', () => { lang = $('ui-language').value; translate(); });
$('load-templates').addEventListener('click', loadTemplates);
$('startup-refresh').addEventListener('click', checkStartup);
$('path-check').addEventListener('click', checkPaths);
$('backup-run').addEventListener('click', createBackup);
$('restore-inspect').addEventListener('click', inspectRestore);
$('restore-run').addEventListener('click', restoreBackup);
$('restore-confirm').addEventListener('change', () => { $('restore-run').disabled = !$('restore-confirm').checked; });
for (const id of ['restore-archive','restore-target']) $(id).addEventListener('input', clearRestoreInspection);
$('vpn-test').addEventListener('click', testVpn);
$('indexer-search').addEventListener('click', searchIndexers);
$('indexer-backup-inspect').addEventListener('click', inspectIndexerBackup);
$('indexer-backup-import').addEventListener('click', importIndexerBackup);
$('indexer-query').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); searchIndexers(); } });
$('admin').addEventListener('click', openAdmin);
$('access-page').addEventListener('click', openAccessPage);
$('download-access').addEventListener('click', downloadAccessPage);
$('finish').addEventListener('click', closeWizard);
$('close-wizard').addEventListener('click', closeWizard);
$('retry').addEventListener('click', async () => { try { await api('/api/reload', {}); installed = false; location.reload(); } catch (failure) { error(failure.message); } });
$('tui').addEventListener('click', async () => { try { await api('/api/tui', {}); $('wizard').hidden = true; $('loading').hidden = false; $('loading').textContent = tr('switched'); $('tui').hidden = true; } catch (failure) { error(failure.message); } });
for (const choice of document.querySelectorAll('input[name="resume"]')) choice.addEventListener('change', async event => { form.reprendre = event.target.value === 'yes'; form.reset_config = false; await validate(); });
for (const choice of document.querySelectorAll('input[name="reset"]')) choice.addEventListener('change', async event => { form.reset_config = event.target.value === 'delete'; await validate(); });
window.addEventListener('beforeunload', event => { if (installed && lastProgress?.status === 'running') { event.preventDefault(); event.returnValue = ''; } });

async function boot() {
  try {
    if (!token) throw new Error(tr('sessionMissing'));
    bootstrap = await api('/api/bootstrap');
    form = structuredClone(bootstrap.form);
    globalThis.PlugArrRemote?.init(bootstrap, form, api, renderReport, () => lang);
    lang = form.ui_language;
    $('ui-language').value = lang;
    $('version').textContent = `v${bootstrap.version}`;
    $('demo-banner').hidden = !bootstrap.demo;
    $('existing-banner').hidden = !bootstrap.existing;
    $('tui').hidden = !bootstrap.can_tui;
    if (bootstrap.icons.plugarr) { $('brand-icon').src = bootstrap.icons.plugarr; $('brand-icon').hidden = false; }
    fillFields();
    await refreshSelection();
    translate();
    $('loading').hidden = true;
    $('wizard').hidden = false;
    showStep(0);
    const progress = await api('/api/progress');
    if (progress.status !== 'idle') {
      startupReady = true;
      showStep(6);
      if (!renderProgress(progress)) poll();
    } else await checkStartup();
  } catch (failure) {
    $('loading').hidden = true;
    error(failure.message);
  }
}

boot();
