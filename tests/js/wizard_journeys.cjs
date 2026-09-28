const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('src/plugarr/web/wizard.js', 'utf8');
const html = fs.readFileSync('src/plugarr/web/wizard.html', 'utf8');
assert.match(html, /id="install-journey"/);
assert.match(html, /id="dependency-details"/);

const journeys = [
  {id:'films_series', name_i18n:{fr:'Films et séries', en:'Movies and TV shows'}, services:['sonarr','radarr']},
  {id:'family', name_i18n:{fr:'Serveur familial', en:'Family server'}, services:['sonarr','seerr']},
  {id:'custom', name_i18n:{fr:'Personnalisé', en:'Custom'}, services:[]},
];
const elements = {
  'install-journey': {
    value:'films_series',
    replaceChildren(...options) { this.options = options; },
    addEventListener(_event, handler) { this.change = handler; },
  },
  services: {replaceChildren() {}, append() {}},
  'selection-count': {},
  'dependency-count': {},
  'dependency-details': {},
};
const context = {
  $: id => elements[id],
  Option: function(text, value) { this.text = text; this.value = value; },
  bootstrap:{install_journeys:journeys, catalog:[]},
  form:{services:['sonarr','radarr']},
  selectionMeta:{}, effective:[], journeyId:'films_series', plan:null, selectionRequest:0,
  pick:(variants, fallback) => variants?.fr || fallback,
  tr:key => ({selected:'applications sélectionnées', dependencies:'dépendances', plannedLinks:'liens', dependencyDetails:'Ajoutées automatiquement (prérequis) : {names}'})[key],
  api:async (_route, body) => ({services:body.services.includes('seerr') ? [...body.services, 'jellyfin'] : body.services,
    added:body.services.includes('seerr') ? [{id:'jellyfin', name_i18n:{fr:'Jellyfin', en:'Jellyfin'}}] : [], planned_links:2}),
  updateConditional() {}, scheduleGraph() {}, error(message) { throw new Error(message); },
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function renderJourneys()'), source.indexOf('function selectedPlaces()')), context);
vm.runInContext(source.slice(source.indexOf("$('install-journey').addEventListener('change'"), source.indexOf('for (const choice of document.querySelectorAll(\'input[name="resume"]\'))')), context);

(async () => {
  vm.runInContext('renderJourneys()', context);
  assert.deepEqual(elements['install-journey'].options.map(option => option.text), ['Films et séries', 'Serveur familial', 'Personnalisé']);
  await elements['install-journey'].change({target:{value:'family'}});
  assert.deepEqual(Array.from(context.form.services), ['sonarr','seerr']);
  assert.match(elements['dependency-details'].textContent, /Jellyfin/);
  await elements['install-journey'].change({target:{value:'custom'}});
  assert.deepEqual(Array.from(context.form.services), []);
  assert.equal(elements['dependency-details'].textContent, '');
  console.log('Web installation journeys, custom selection and dependency names: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
