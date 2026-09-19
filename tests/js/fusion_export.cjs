// Fusion avec la sauvegarde de l'utilisateur : donnees fictives uniquement.
// Le flux Java de reference est ecrit par un vrai ObjectOutputStream
// (tests/fixtures/java_hashmap_references.bin) : references partagees comprises.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodeCrypto=require('node:crypto'),zlib=require('node:zlib');
const context={URL,Date,TextEncoder,TextDecoder,Blob,Response,CompressionStream,DecompressionStream,crypto:globalThis.crypto,
  Math,JSON,Map,Set,BigInt,DataView,Uint8Array,ArrayBuffer,Error,Object,Number,String,Array};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js','utf8'),context);
const R=context.PlugArrRemote;
const plain=value=>JSON.parse(JSON.stringify(value,(k,v)=>typeof v==='bigint'?`${v}n`:v));
const entries=map=>plain(Object.fromEntries(map));

// -- lecteur Java sur un flux ecrit par Java ------------------------------------
const fixture=new Uint8Array(fs.readFileSync('tests/fixtures/java_hashmap_references.bin'));
const lu=R.readJavaPreferences(fixture);
assert.equal(lu.get('texte'),'valeur partagee');
assert.equal(lu.get('texte_bis'),'valeur partagee','reference vers une chaine deja lue');
assert.equal(lu.get('vrai'),true);assert.equal(lu.get('vrai_bis'),true,'reference vers Boolean.TRUE');
assert.equal(lu.get('faux'),false);
assert.deepEqual(plain(lu.get('entier')),{t:'I',v:-42});
assert.deepEqual(plain(lu.get('long')),{t:'J',v:'1789575962414n'});
assert.deepEqual(plain(lu.get('flottant')),{t:'F',v:1.5});
assert.deepEqual(plain(lu.get('double')),{t:'D',v:2.25});
assert.equal(lu.get('accents'),String.fromCharCode(0xe9,0,0xd83d,0xde00));
assert.equal(lu.get('vide'),'');
// Reecriture puis relecture : memes cles, memes valeurs, memes types.
assert.deepEqual(entries(R.readJavaPreferences(R.javaPreferences(Object.fromEntries(lu)))),entries(lu));
// Ce qui n'est pas compris est refuse, jamais reecrit au hasard.
assert.throws(()=>R.readJavaPreferences(new Uint8Array([1,2,3,4])));
assert.throws(()=>R.readJavaPreferences(fixture.slice(0,fixture.length-3)));

// -- nzb360 : fusion ---------------------------------------------------------------
const services=[
  {id:'sonarr',name:'Sonarr',local_url:'http://192.0.2.5:8989',remote_url:'https://sonarr.example.test',api_key:'CLE-PLUGARR'},
  {id:'radarr',name:'Radarr',local_url:'http://192.0.2.5:7878',remote_url:'https://radarr.example.test',api_key:'CLE-PLUGARR'},
  {id:'qbittorrent',name:'qBittorrent',local_url:'http://192.0.2.5:8080',remote_url:'https://qb.example.test',username:'essai',password:'MDP-PLUGARR'},
];
const data={services,demo:false};
const utilisateur={version:'24.4.1',nzbdrone_server_enabled_preference:true,
  nzbdrone_server_primary_connectionstring_preference:'https://seedbox.example.test/sonarr',nzbdrone_apikey_preference:'CLE-UTILISATEUR',
  radarr_server_enabled_preference:false,radarr_server_primary_connectionstring_preference:'',
  tautulli_server_enabled_preference:true,tautulli_apikey_preference:'CLE-TAUTULLI',radarrQualitySelectionInt:{t:'I',v:1}};
const licence={version:'24.4.1',licensing_stored_ispro:true,app_update_check:{t:'J',v:1789575962414n}};
const sauvegarde=R.zipStored([['com.kevinforeman.nzb360_preferences.xml',R.javaPreferences(utilisateur)],
  ['nzb360prefs.xml',R.javaPreferences(licence)],['servers.xml',R.javaPreferences({})]]);
(async()=>{
  const base=await R.inspectNzb360Backup(sauvegarde);
  assert.deepEqual(plain(base.configured),[{id:'sonarr',url:'https://seedbox.example.test/sonarr',enabled:true}],
    'un Radarr sans adresse ne compte pas comme present');
  const fusion=R.mergeNzb360(base,data,'remote','Maison');
  assert.deepEqual([...fusion.added],['radarr','qbittorrent']);assert.deepEqual([...fusion.kept],['sonarr']);
  const apres=await R.inspectNzb360Backup(fusion.bytes);
  const prefs=apres.preferences;
  assert.equal(prefs.get('nzbdrone_apikey_preference'),'CLE-UTILISATEUR','Sonarr de l utilisateur garde par defaut');
  assert.equal(prefs.get('nzbdrone_server_primary_connectionstring_preference'),'https://seedbox.example.test/sonarr');
  assert.equal(prefs.has('nzbdrone_localconnectionswitch_preference'),false);
  assert.equal(prefs.get('radarr_server_primary_connectionstring_preference'),'https://radarr.example.test');
  assert.equal(prefs.get('radarr_localconnectionswitch_preference'),true);
  assert.equal(prefs.get('torrent_client_preference'),'qbittorrent');
  assert.equal(prefs.get('tautulli_apikey_preference'),'CLE-TAUTULLI','service hors PlugArr garde');
  assert.deepEqual(plain(prefs.get('radarrQualitySelectionInt')),{t:'I',v:1});
  assert.deepEqual(apres.files.map(([n])=>n),base.files.map(([n])=>n));
  assert.deepEqual([...apres.files[1][1]],[...base.files[1][1]],'licence recopiee a l octet pres');
  assert.equal(fusion.switching,2);
  const remplace=R.mergeNzb360(base,data,'remote','Maison',['sonarr']);
  assert.deepEqual([...remplace.replaced],['sonarr']);
  const prefsRemplace=(await R.inspectNzb360Backup(remplace.bytes)).preferences;
  assert.equal(prefsRemplace.get('nzbdrone_apikey_preference'),'CLE-PLUGARR');
  assert.equal(prefsRemplace.get('tautulli_apikey_preference'),'CLE-TAUTULLI');
  await assert.rejects(()=>R.inspectNzb360Backup(R.zipStored([['autre.txt',new Uint8Array([1])]])));

  // -- qbRemote : fusion -------------------------------------------------------------
  const serveurs=[{id:4,name:'Seedbox',host:'seedbox.example.test',password:'MDP-UTILISATEUR'},{id:5,name:'Maison',host:'192.0.2.9'}];
  const reglages=JSON.stringify({key_dark_mode:true});
  const chiffree=await R.zipAes([['manifest.json','{"version":1}'],['setting.json',reglages],['servers.json',JSON.stringify(serveurs)],
    ['search_history.json','[]']],'secret');
  await assert.rejects(()=>R.mergeQbRemote(chiffree,'faux',data,'local'),e=>e instanceof R.ZipPasswordError);
  await assert.rejects(()=>R.mergeQbRemote(chiffree,'',data,'local'),e=>e instanceof R.ZipPasswordError);
  const qb=await R.mergeQbRemote(chiffree,'secret',data,'remote','Maison');
  assert.equal(qb.kept,2);assert.equal(qb.updated,false);
  const relu=readAesZip(qb.bytes,'secret');
  assert.deepEqual(Object.keys(relu),['manifest.json','setting.json','servers.json','search_history.json']);
  assert.equal(relu['setting.json'],reglages,'preferences recopiees');
  const liste=JSON.parse(relu['servers.json']);
  assert.deepEqual(liste.slice(0,2),serveurs,'serveurs de l utilisateur intacts');
  assert.equal(liste[2].name,'PlugArr');assert.equal(liste[2].id,6);assert.equal(liste[2].localSsid,'Maison');
  // Deuxieme passage : PlugArr est mis a jour, pas duplique.
  const encore=await R.mergeQbRemote(qb.bytes,'secret',data,'local');
  assert.equal(encore.updated,true);
  const liste2=JSON.parse(readAesZip(encore.bytes,'secret')['servers.json']);
  assert.equal(liste2.length,3);assert.equal(liste2[2].id,6);assert.equal(liste2[2].scheme,'http');
  // Sauvegarde sans mot de passe : relue telle quelle, rendue chiffree.
  const enClair=R.zipStored([['servers.json',new TextEncoder().encode(JSON.stringify(serveurs))]]);
  const depuisClair=await R.mergeQbRemote(enClair,'nouveau',data,'local');
  assert.deepEqual(Object.keys(readAesZip(depuisClair.bytes,'nouveau')),['manifest.json','servers.json']);
  console.log('fusion : flux Java de reference, nzb360 (garde, ajoute, remplace) et qbRemote (chiffre, en clair, mise a jour) OK');
})().catch(error=>{console.error(error);process.exit(1);});

// Dechiffreur WinZip AES independant de remote.js (node:crypto).
function readAesZip(bytes,password){
  const buf=Buffer.from(bytes),files={};let i=0;
  while(buf.readUInt32LE(i)===0x04034b50){
    const size=buf.readUInt32LE(i+18),nameLength=buf.readUInt16LE(i+26),extraLength=buf.readUInt16LE(i+28);
    const name=buf.subarray(i+30,i+30+nameLength).toString('utf8');
    const data=buf.subarray(i+30+nameLength+extraLength,i+30+nameLength+extraLength+size);
    const keys=nodeCrypto.pbkdf2Sync(password,data.subarray(0,16),1000,66,'sha1');
    assert.deepEqual(data.subarray(16,18),keys.subarray(64,66));
    const cipher=data.subarray(18,data.length-10),out=Buffer.alloc(cipher.length);
    for(let start=0,block=1;start<cipher.length;start+=16,block++){
      const counter=Buffer.alloc(16);counter.writeUInt32LE(block,0);
      const ecb=nodeCrypto.createCipheriv('aes-256-ecb',keys.subarray(0,32),null);ecb.setAutoPadding(false);
      const stream=Buffer.concat([ecb.update(counter),ecb.final()]);
      for(let j=0;j<16&&start+j<cipher.length;j++)out[start+j]=cipher[start+j]^stream[j];
    }
    files[name]=zlib.inflateRawSync(out).toString('utf8');
    i+=30+nameLength+extraLength+size;
  }
  return files;
}
