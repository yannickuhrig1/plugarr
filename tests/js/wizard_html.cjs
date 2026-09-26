// Deux pannes que seul un vrai navigateur montrait, et qu'aucun test Python
// n'atteignait : le HTML de l'assistant est interprete par le moteur JS, pas
// par Python.
//
//  1. `pattern="[a-z0-9][a-z0-9_-]*"` : Chrome compile desormais l'attribut
//     `pattern` avec le drapeau `v`, qui REFUSE un tiret litteral non echappe
//     dans une classe. L'attribut etait rejete en silence — la console disait
//     « Invalid regular expression » et le champ acceptait « Ma Pile ! ».
//  2. Les cles de `data-i18n-placeholder` n'etaient semees que dans EN. En
//     francais, tr() retombait sur la CLE et le champ affichait
//     « locationSearch ».
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('src/plugarr/web/wizard.html', 'utf8');
const source = fs.readFileSync('src/plugarr/web/wizard.js', 'utf8');

const patterns = [...html.matchAll(/pattern="([^"]+)"/g)].map(m => m[1]);
assert.ok(patterns.length, 'aucun attribut pattern trouve : le test ne verifie plus rien');
for (const pattern of patterns) {
  // Exactement ce que fait le navigateur pour un attribut `pattern`.
  assert.doesNotThrow(
    () => new RegExp(`^(?:${pattern})$`, 'v'),
    `pattern refuse par le navigateur, donc ignore : ${pattern}`,
  );
}
assert.equal(new RegExp(`^(?:${patterns[0]})$`, 'v').test('Ma Pile !'), false);

const placeholders = [...html.matchAll(/data-i18n-placeholder="([^"]+)"[^>]*?placeholder="([^"]+)"/g)];
assert.ok(placeholders.length, 'aucun placeholder traduit trouve');

const prelude = source.slice(source.indexOf('const EN = {'), source.indexOf('let lang = '));
const elements = placeholders.map(([, key, texte]) => ({
  dataset: {i18nPlaceholder: key},
  placeholder: texte,
}));
const context = {
  document: {
    querySelectorAll: selector =>
      selector === '[data-i18n-placeholder]' ? elements : [],
  },
};
vm.createContext(context);
vm.runInContext(prelude, context);
vm.runInContext("const tr = key => (lang === 'en' ? EN : FR)[key] || FR[key] || key;", context);
for (const [, key, texte] of placeholders) {
  vm.runInContext("lang = 'fr';", context);
  assert.equal(vm.runInContext(`tr(${JSON.stringify(key)})`, context), texte,
    `placeholder francais absent pour ${key}`);
  vm.runInContext("lang = 'en';", context);
  assert.notEqual(vm.runInContext(`tr(${JSON.stringify(key)})`, context), key,
    `placeholder anglais absent pour ${key}`);
}

vm.runInContext("lang = 'fr';", context);
assert.equal(vm.runInContext("tr('sshRemoteBadge')", context), 'SSH DISTANT',
  'le badge SSH distant doit etre traduit en francais');

// Une installation distante doit ignorer les choix de reprise et de nettoyage
// de l'installation locale, meme si leurs boutons radio restent coches dans le
// DOM. C'etait ce qui empechait /api/validate de fournir un plan_id.
const fieldsSource = source.slice(
  source.indexOf('function readVpnFields()'),
  source.indexOf('function updatePlatformInfo()'),
);
const values = Object.fromEntries([
  'platform','project_name','data_root','config_root','username','host',
  'timezone','language','vpn-provider','vpn-type','vpn-key','vpn-addresses',
  'vpn-user','vpn-password','vpn-manual-countries',
].map(id => [id, {value:''}]));
Object.assign(values, {
  'project-dir': {textContent:'/srv/plugarr'},
  'remote-replace': {checked:false},
  'vpn-enabled': {checked:false},
  'veille-enabled': {checked:false},
  'veille-port': {value:'7374'},
  'veille-docker': {checked:false},
  'console-enabled': {checked:false},
  'console-port': {value:'7373'},
});
const fieldsContext = {
  form:{}, remoteProbe:{connection_id:'remote-1', fingerprint:'SHA256:test'}, remoteExisting:null,
  bootstrap:{providers:{'':{choices:[]}}, existing:true, download_clients:[]},
  effective:[], lang:'fr', competingClients:()=>[], selectedPlaces:()=>[],
  $:id => values[id],
  document:{querySelector:selector => {
    if (selector === 'input[name="install-target"]:checked') return {value:'ssh'};
    if (selector === 'input[name="resume"]:checked') return {value:'yes'};
    if (selector === 'input[name="reset"]:checked') return {value:'delete'};
    if (selector === 'input[name="sab-route"]:checked') return {value:'direct'};
    return null;
  }},
  PlugArrRemote:{read:()=>({mode:'local',domain:'',services:[]})},
};
vm.createContext(fieldsContext);
vm.runInContext(fieldsSource, fieldsContext);
vm.runInContext('readFields()', fieldsContext);
assert.equal(fieldsContext.form.install_target, 'ssh');
assert.equal(fieldsContext.form.reprendre, false,
  'la reprise locale ne doit jamais partir dans une validation SSH');
assert.equal(fieldsContext.form.reset_config, true,
  'le nettoyage distant demande reste dans la validation SSH');
assert.equal(fieldsContext.form.remote_replace, false,
  'le remplacement distant doit demander une confirmation separee');
// Second passage reel du 25/09/2026 : la pile trouvee SUR LE SERVEUR se reprend.
vm.runInContext("remoteExisting = {services:[]}; readFields()", fieldsContext);
assert.equal(fieldsContext.form.reprendre, true,
  'une pile PlugArr trouvee sur le serveur doit etre reprise');
vm.runInContext('remoteExisting = null', fieldsContext);
values['remote-replace'].checked = true;
vm.runInContext('readFields()', fieldsContext);
assert.equal(fieldsContext.form.remote_replace, true,
  'la confirmation de remplacement distant doit etre transmise');

// Essai reel du 25/09/2026 : apres un echec, le bouton de relance etait dans
// #post-install, qui reste cache tant que l'installation n'a pas abouti.
{
  const retry = html.indexOf('id="retry"');
  const post = html.indexOf('<div id="post-install"');
  assert.ok(retry > 0 && post > 0, 'bouton retry ou bloc post-install introuvable');
  assert.ok(retry < post, 'le bouton de relance ne doit pas etre dans #post-install, cache en cas d echec');
}
// Et le statut SSH affichait la cle brute « sshReady ».
for (const cle of ['sshReady', 'sshPrivateHost']) {
  vm.runInContext("lang = 'fr';", context);
  assert.notEqual(vm.runInContext(`tr(${JSON.stringify(cle)})`, context), cle, `${cle} absent en francais`);
  vm.runInContext("lang = 'en';", context);
  assert.notEqual(vm.runInContext(`tr(${JSON.stringify(cle)})`, context), cle, `${cle} absent en anglais`);
}
assert.ok(source.includes("result.suggested_host || sshHost"),
  "l'adresse de la machine doit reprendre celle proposee par le test SSH");
console.log('Retry visible after failure, SSH status translated, suggested host used: OK');
