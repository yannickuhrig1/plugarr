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
