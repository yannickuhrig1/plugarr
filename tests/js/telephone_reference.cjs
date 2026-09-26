// Reference outputs of web/remote.js for tests/test_telephone.py.
// Reads a JSON request on stdin, writes a JSON answer on stdout. Bytes travel
// as base64. Only synthetic data: nothing here comes from a real installation.
const fs = require('node:fs'), vm = require('node:vm');
const context = {URL, Date, TextEncoder, TextDecoder, crypto: globalThis.crypto,
  CompressionStream, DecompressionStream, Response, Blob, Uint8Array, DataView, BigInt};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js', 'utf8'), context);
const R = context.PlugArrRemote;
const b64 = bytes => Buffer.from(bytes).toString('base64');
const unb64 = text => new Uint8Array(Buffer.from(text, 'base64'));
const plain = value => JSON.parse(JSON.stringify(value, (k, v) => (typeof v === 'bigint' ? Number(v) : Object.prototype.toString.call(v) === '[object Map]' ? Object.fromEntries(v) : v)));

(async () => {
  const request = JSON.parse(fs.readFileSync(0, 'utf8'));
  const answer = {};
  const data = request.data;
  answer.arr = ['local', 'remote'].map(network => plain(R.buildArrControlExport(data, network, 1790000000000)));
  answer.nzb = [['local', ''], ['remote', ''], ['remote', 'Maison']].map(([network, ssid]) => {
    const r = R.buildNzb360Export(data, network, ssid);
    return {bytes: b64(r.bytes), count: r.count, omitted: [...r.omitted], switching: r.switching};
  });
  answer.java = request.java.map(prefs => b64(R.javaPreferences(prefs)));
  answer.javaRead = request.java.map(prefs => plain(R.readJavaPreferences(R.javaPreferences(prefs))));
  answer.zip = b64(R.zipStored(request.zip.map(([name, text]) => [name, new TextEncoder().encode(text)])));
  answer.qr = request.qr.map(text => {const q = R.qrMatrix(text); return {version: q.version, mask: q.mask, modules: q.modules.map(row => row.map(Number).join(''))};});
  answer.qb = [['local', ''], ['remote', ''], ['remote', 'Maison']].map(([network, ssid]) => plain(R.buildQbRemoteServer(data, network, ssid)));
  // Merges into a synthetic nzb360 backup built by Python.
  const base = await R.inspectNzb360Backup(unb64(request.nzbBase));
  answer.nzbInspect = {configured: plain(base.configured), activeProfile: base.activeProfile};
  const profile = R.mergeNzb360Profile(base, data, 'local', '');
  answer.nzbProfile = {bytes: b64(profile.bytes), added: [...profile.added], profile: plain(profile.profile)};
  const merged = R.mergeNzb360(base, data, 'local', '', ['sonarr']);
  answer.nzbMerge = {bytes: b64(merged.bytes), added: [...merged.added], replaced: [...merged.replaced], kept: [...merged.kept]};
  // AES in both directions: JS reads the Python archive, Python reads the JS one.
  answer.aesRead = plain((await R.readZipFiles(unb64(request.aesFromPython), request.password)).map(([name, bytes]) => [name, new TextDecoder().decode(bytes)]));
  answer.aesFromJs = b64(await R.zipAes([['manifest.json', '{"version":1}'], ['servers.json', '[{"id":1}]']], request.password, new Date(Date.UTC(2026, 8, 26, 10, 0, 0))));
  let wrong = null;
  try {await R.readZipFiles(unb64(request.aesFromPython), 'wrong-password');} catch (e) {wrong = e instanceof R.ZipPasswordError;}
  answer.aesWrongPassword = wrong;
  process.stdout.write(JSON.stringify(answer));
})().catch(error => {console.error(error); process.exitCode = 1;});
