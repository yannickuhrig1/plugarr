// Pure schema/credential mapping checks. No user export or real secrets used.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={URL,Date};vm.createContext(context);
vm.runInContext(fs.readFileSync('src/plugarr/web/remote.js','utf8'),context);
const build=(data,network='local')=>JSON.parse(JSON.stringify(context.PlugArrRemote.buildArrControlExport(data,network,1700000000000)));
const services=['sonarr','radarr','prowlarr','seerr','qbittorrent','unsupported'].map(id=>({id,name:id,local_url:`http://192.0.2.1:8989/${id}`,remote_url:['sonarr','radarr','qbittorrent'].includes(id)?`https://${id}.example.test`:'',api_key:'TEST-KEY',username:'test-user',password:'TEST-PASSWORD'}));
const data={services,demo:false,remote:{auth_url:'SECRET-NOT-FOR-EXPORT'}};
const local=build(data);
assert.deepEqual(Object.keys(local.payload).sort(),['exportedAt','server','services','version']);
assert.equal(local.payload.version,1);assert.equal(local.payload.exportedAt,1700000000000);
assert.equal(local.payload.services.length,5);assert.deepEqual(local.omitted,[]);
for(const service of local.payload.services){
  assert.equal(service.url,service.config.fields.localUrl);
  assert.equal(service.config.remoteAccess,false);assert.equal(service.config.remoteUrl,'');
  assert.equal(service.config.networkMode,'auto');assert.equal(service.config.headerType,'custom');
  assert.deepEqual(service.config.headers,[]);
  assert.deepEqual(Object.keys(service).sort(),['apiKey','categoryId','config','name','serviceId','url']);
  if(service.serviceId==='qbittorrent'){
    assert.equal(service.categoryId,'downloads');assert.equal(service.apiKey,null);
    assert.equal(service.config.fields.password,'TEST-PASSWORD');assert.equal(service.config.fields.username,'test-user');
    assert.equal(service.config.fields.apiKey,undefined);
  }else{assert.equal(service.apiKey,'TEST-KEY');assert.equal(service.config.fields.apiKey,'TEST-KEY');assert.equal(service.config.fields.password,undefined);}
}
assert.equal(local.payload.services.find(s=>s.serviceId==='seerr').categoryId,'requests');
assert.equal(local.payload.services.find(s=>s.serviceId==='prowlarr').categoryId,'indexers');
assert.ok(!JSON.stringify(local).includes('SECRET-NOT-FOR-EXPORT'));
const remote=build(data,'remote');assert.equal(remote.payload.services.length,3);
assert.deepEqual(remote.omitted,['prowlarr','seerr']);
assert.ok(remote.payload.services.every(s=>s.url.startsWith('https://')&&s.config.fields.localUrl===s.url));
assert.ok(build({...data,demo:true}).payload.server.includes('DEMO'));
for(const address of ['javascript:alert(1)','file:///secret','https://user:password@example.test','']){
  assert.equal(build({services:[{...services[0],local_url:address}]}).payload.services.length,0);
}
for(const credentials of [{api_key:''},{api_key:'-'},{api_key:null}])assert.equal(build({services:[{...services[0],...credentials}]}).payload.services.length,0);
assert.equal(build({services:[{...services[4],password:'-'}]}).payload.services.length,0);
assert.throws(()=>build(data,'invalid'));
assert.deepEqual(build({services:[]}).payload.services,[]);
console.log('Arr Control: v1 schema, five mappings, fixed local/remote profiles, exclusions and secret isolation OK');
