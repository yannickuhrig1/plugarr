// Generate only synthetic test data. Validate ZIP/Java serialization independently.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={URL,Date};vm.createContext(context);
vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js','utf8'),context);
const build=context.PlugArrRemote.buildNzb360Export;
const services=['sonarr','radarr','qbittorrent','prowlarr'].map(id=>({id,name:id,local_url:`http://192.0.2.5:8989/${id}`,remote_url:`https://${id}.example.test`,api_key:'TEST-API-KEY',username:'test-user',password:'TEST-é\u0000😀-password'}));
const data={services,remote:{auth_url:'DO-NOT-EXPORT'},private_license:'DO-NOT-EXPORT'};
const root=fs.mkdtempSync(path.resolve('build/nzb360-format-'));
for(const network of ['local','remote']){
  const result=build(data,network);assert.equal(result.count,3);assert.equal(result.omitted.length,0);
  assert.ok(!Buffer.from(result.bytes).includes(Buffer.from('DO-NOT-EXPORT')));
  assert.ok(!Buffer.from(result.bytes).includes(Buffer.from('licensing_')));
  fs.writeFileSync(path.join(root,`${network}.zip`),result.bytes);
}
assert.equal(build({services:[]}).count,0);
assert.equal(build({services:[{...services[0],api_key:'-'}]}).count,0);
assert.equal(build({services:[{...services[0],remote_url:''}]},'remote').count,0);
assert.equal(build({services:[{...services[2],password:''}]}).count,0);
assert.equal(build({services:[{...services[0],local_url:'javascript:alert(1)'}]}).count,0);
assert.throws(()=>build(data,'bad-network'));
assert.throws(()=>build({services:[{...services[0],api_key:'x'.repeat(65536)}]}));
// SABnzbd: no remote address managed by PlugArr, so local profile only.
const sab={id:'sabnzbd',name:'SABnzbd',local_url:'http://192.0.2.5:8085',remote_url:'',api_key:'TEST-SAB-KEY',username:'-',password:'-'};
const withSab={services:[...services,sab]};
const localSab=build(withSab,'local');assert.equal(localSab.count,4);assert.equal(localSab.switching,0);
fs.writeFileSync(path.join(root,'local-sab.zip'),localSab.bytes);
const remoteSab=build(withSab,'remote');assert.equal(remoteSab.count,3);assert.deepEqual([...remoteSab.omitted],['SABnzbd']);
assert.equal(build({services:[{...sab,api_key:'-'}]},'local').count,0);
// One file for home and away: remote primary, local address under the Wi-Fi name.
const both=build(withSab,'remote','Maison');assert.equal(both.count,3);assert.equal(both.switching,3);
fs.writeFileSync(path.join(root,'both.zip'),both.bytes);
assert.equal(build(withSab,'local','Maison').switching,0,'a local profile needs no switch');
// Lidarr, Seerr and Transmission: local profile only, like SABnzbd.
const extra=[
  {id:'lidarr',name:'Lidarr',local_url:'http://192.0.2.5:8686',remote_url:'',api_key:'TEST-LIDARR-KEY',username:'-',password:'-'},
  {id:'seerr',name:'Seerr',local_url:'http://192.0.2.5:5055',remote_url:'',api_key:'TEST-SEERR-KEY',username:'-',password:'-'},
  {id:'transmission',name:'Transmission',local_url:'http://192.0.2.5:9091',remote_url:'',api_key:'-',username:'tr-user',password:'TR-PASS'}];
const localExtra=build({services:[services[0],...extra]},'local');assert.equal(localExtra.count,4);assert.equal(localExtra.omitted.length,0);
fs.writeFileSync(path.join(root,'local-extra.zip'),localExtra.bytes);
const remoteExtra=build({services:[...services,...extra]},'remote','Maison');assert.equal(remoteExtra.count,3);
assert.deepEqual([...remoteExtra.omitted],['Lidarr','Seerr']);
// One torrent slot in nzb360: qBittorrent keeps it, Transmission is left out.
const qbFirst=build({services:[...services,...extra]},'local');assert.equal(qbFirst.count,5);
fs.writeFileSync(path.join(root,'qb-first.zip'),qbFirst.bytes);
assert.equal(build({services:[{...extra[0],api_key:'-'}]},'local').count,0);
assert.equal(build({services:[{...extra[2],password:''}]},'local').count,0);
// Separate PlugArr profile next to an existing one (servers.xml HashSet, 002.xml).
(async()=>{
  const context2={URL,Date,TextEncoder,TextDecoder,Blob,Response,CompressionStream,DecompressionStream,Math,JSON,Map,Set,BigInt,DataView,Uint8Array,ArrayBuffer,Error,Object,Number,String,Array};
  vm.createContext(context2);vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js','utf8'),context2);
  const R=context2.PlugArrRemote;
  const base=await R.inspectNzb360Backup(R.zipStored([['com.kevinforeman.nzb360_preferences.xml',R.javaPreferences({version:'24.4.1'})],
    ['nzb360prefs.xml',R.javaPreferences({version:'24.4.1'})],['servers.xml',R.javaPreferences({servers:{t:'set',v:['000Default*','001test']}})],
    ['001.xml',R.javaPreferences({})]]));
  fs.writeFileSync(path.join(root,'profile.zip'),R.mergeNzb360Profile(base,{services:[services[0],...extra]},'local').bytes);
  console.log(root);
})().catch(e=>{console.error(e);process.exit(1);});
console.log('nzb360 export: mappings, network isolation, missing credentials, oversized fields and secret exclusions, Lidarr, Seerr and Transmission OK');
