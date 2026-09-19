// qbRemote 1.8.0 export: synthetic data only. The ZIP is read back by an
// independent WinZip AES decoder written with node:crypto, not by remote.js.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const nodeCrypto=require('node:crypto'),zlib=require('node:zlib');
const context={URL,Date,TextEncoder,Blob,Response,CompressionStream,crypto:globalThis.crypto,Math,JSON};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js','utf8'),context);
const {buildQbRemoteServer,buildQbRemoteExport}=context.PlugArrRemote;

function readAesZip(bytes,password){
  const buf=Buffer.from(bytes),entries={};
  let i=0;
  while(buf.readUInt32LE(i)===0x04034b50){
    const flags=buf.readUInt16LE(i+6),method=buf.readUInt16LE(i+8),crc=buf.readUInt32LE(i+14);
    const size=buf.readUInt32LE(i+18),plainSize=buf.readUInt32LE(i+22),nameLength=buf.readUInt16LE(i+26),extraLength=buf.readUInt16LE(i+28);
    const name=buf.subarray(i+30,i+30+nameLength).toString('utf8'),extra=buf.subarray(i+30+nameLength,i+30+nameLength+extraLength);
    assert.equal(flags,0x801);assert.equal(method,99);
    assert.equal(extra.toString('hex'),'0199070001004145030800','AE-1, AES-256, deflate as in the qbRemote sample');
    const data=buf.subarray(i+30+nameLength+extraLength,i+30+nameLength+extraLength+size);
    const salt=data.subarray(0,16),check=data.subarray(16,18),cipher=data.subarray(18,data.length-10),mac=data.subarray(data.length-10);
    const keys=nodeCrypto.pbkdf2Sync(password,salt,1000,66,'sha1');
    assert.deepEqual(check,keys.subarray(64,66),'password verifier');
    assert.deepEqual(nodeCrypto.createHmac('sha1',keys.subarray(32,64)).update(cipher).digest().subarray(0,10),mac,'HMAC');
    const plain=Buffer.alloc(cipher.length);
    for(let start=0,block=1;start<cipher.length;start+=16,block++){
      const counter=Buffer.alloc(16);counter.writeUInt32LE(block,0);
      const ecb=nodeCrypto.createCipheriv('aes-256-ecb',keys.subarray(0,32),null);ecb.setAutoPadding(false);
      const stream=Buffer.concat([ecb.update(counter),ecb.final()]);
      for(let j=0;j<16&&start+j<cipher.length;j++)plain[start+j]=cipher[start+j]^stream[j];
    }
    const text=zlib.inflateRawSync(plain);
    assert.equal(text.length,plainSize);assert.equal(zlib.crc32(text),crc,'AE-1 keeps the real CRC');
    entries[name]=JSON.parse(text.toString('utf8'));
    i+=30+nameLength+extraLength+size;
  }
  assert.equal(buf.readUInt32LE(i),0x02014b50,'central directory follows the entries');
  return entries;
}

const qb={id:'qbittorrent',name:'qBittorrent',local_url:'http://192.0.2.5:8080',remote_url:'https://qb.example.test',username:'test-user',password:'TEST-é😀-password'};
const data={services:[{id:'sonarr',name:'Sonarr',local_url:'http://192.0.2.5:8989',api_key:'TEST-KEY'},qb],demo:false,remote:{auth_url:'DO-NOT-EXPORT'}};

// Mapping, sans chiffrement.
const local=buildQbRemoteServer(data,'local');
assert.equal(local.scheme,'http');assert.equal(local.host,'192.0.2.5');assert.equal(local.port,'8080');assert.equal(local.localHost,null);
const distant=buildQbRemoteServer(data,'remote','Maison');
assert.equal(distant.scheme,'https');assert.equal(distant.host,'qb.example.test');assert.equal(distant.port,'443');
assert.equal(distant.localSsid,'Maison');assert.equal(distant.localHost,'192.0.2.5');assert.equal(distant.localPort,'8080');assert.equal(distant.localScheme,'http');
assert.equal(buildQbRemoteServer(data,'remote').localHost,null,'no Wi-Fi name, no local switch');
assert.equal(buildQbRemoteServer(data,'local','Maison').localHost,null,'a local profile needs no switch');
assert.equal(buildQbRemoteServer({services:[{...qb,password:''}]},'local'),null);
assert.equal(buildQbRemoteServer({services:[{...qb,password:'-'}]},'local'),null);
assert.equal(buildQbRemoteServer({services:[{...qb,remote_url:''}]},'remote'),null);
assert.equal(buildQbRemoteServer({services:[{...qb,local_url:'javascript:alert(1)'}]},'local'),null);
assert.equal(buildQbRemoteServer({services:[{...qb,local_url:'http://user:pw@192.0.2.5:8080'}]},'local'),null);
assert.equal(buildQbRemoteServer({services:[]},'local'),null);
assert.equal(buildQbRemoteServer({services:[qb],demo:true},'local').name,'PlugArr DEMO');
assert.throws(()=>buildQbRemoteServer(data,'bad-network'));
// Same keys as a server written by qbRemote 1.8.0 itself.
assert.deepEqual(Object.keys(local).sort(),['apiKey','apiVersion','basicAuthEnabled','basicAuthPassword','basicAuthUsername','clientIdentity',
  'customHeaders','defaultTls','host','id','localDisableAuthentication','localHost','localPath','localPort','localScheme','localSsid','localTls',
  'localTrustCertificates','macAddress','name','networkStackOverride','notifyOnComplete','password','path','port','scheme','trustCertificates',
  'username','wolBroadcastAddress','wolPort']);

(async()=>{
  const now=new Date('2026-09-18T17:22:14Z');
  const bytes=await buildQbRemoteExport(data,'remote','Maison','test',now);
  const entries=readAesZip(bytes,'test');
  assert.deepEqual(Object.keys(entries),['manifest.json','servers.json']);
  assert.deepEqual(entries['manifest.json'],{version:1,createdAt:'2026-09-18T17:22:14.000Z',appVersion:'1.8.0(73)'});
  assert.equal(entries['servers.json'].length,1);
  assert.equal(entries['servers.json'][0].password,'TEST-é😀-password');
  assert.equal(entries['servers.json'][0].localSsid,'Maison');
  assert.ok(!Buffer.from(bytes).includes(Buffer.from('TEST-')),'nothing readable without the password');
  assert.ok(!Buffer.from(bytes).includes(Buffer.from('DO-NOT-EXPORT')));
  assert.throws(()=>readAesZip(bytes,'wrong'),/password verifier|HMAC/);
  assert.equal(await buildQbRemoteExport({services:[]},'local','','test'),null);
  // Keep a copy for an external cross-check when a directory is given.
  if(process.argv[2])fs.writeFileSync(path.join(process.argv[2],'qbremote-synthetique.zip'),bytes);
  console.log('qbRemote export: mapping, Wi-Fi switch, AES-256 ZIP, CRC, HMAC and secret isolation OK');
})().catch(error=>{console.error(error);process.exit(1);});
