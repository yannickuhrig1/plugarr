// Integrated wizard smoke test. Only --demo is launched; no Docker/network changes.
const {chromium, expect} = require('playwright/test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

async function scenario(browser, mode, root) {
  const project = path.join(root, mode);
  fs.mkdirSync(project, {recursive:true});
  const exe = process.env.PLUGARR_TEST_EXE;
  const program = exe || path.resolve('build/share-0ae7d00-20260915/env/Scripts/python.exe');
  const args = [...(exe ? [] : ['-m','plugarr']), 'web','--demo','--no-open','--port','0','--project-dir',project];
  const child = spawn(program,args,{env:{...process.env,PYTHONPATH:path.resolve('src'),PYTHONUNBUFFERED:'1',PLUGARR_NO_SELF_UPDATE:'1'},windowsHide:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  try {
    const url = await new Promise((resolve,reject)=>{
      let output=''; const timer=setTimeout(()=>reject(new Error('Demo server startup timed out')),30000);
      child.stdout.on('data',chunk=>{output+=chunk.toString();const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#token=[\w-]+/);if(m){clearTimeout(timer);resolve(m[0]);}});
      child.on('exit',code=>{clearTimeout(timer);reject(new Error(`Demo exited: ${code}`));});
      child.on('error',reject);
    });
    const page=await context.newPage(), errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);
    await expect(page.locator('#next')).toBeEnabled({timeout:30000});
    const serviceIds=await page.locator('.service-card input').evaluateAll(nodes=>nodes.map(n=>n.value));
    for (const id of serviceIds) {
      const input=page.locator(`.service-card input[value="${id}"]`);
      const desired=['sonarr','radarr','qbittorrent','prowlarr','seerr'].includes(id);
      if(await input.isChecked()!==desired){
        const response=page.waitForResponse(r=>r.url().endsWith('/api/selection')&&r.request().method()==='POST');
        await input.setChecked(desired);await response;
      }
    }
    assert.deepEqual((await page.locator('.service-card input:checked').evaluateAll(nodes=>nodes.map(n=>n.value))).sort(),['prowlarr','qbittorrent','radarr','seerr','sonarr']);
    const next=()=>page.locator('#next').click();
    await next(); await expect(page.locator('[data-step="1"]')).toBeVisible();
    await next(); await expect(page.locator('[data-step="2"]')).toBeVisible();
    await page.locator('#vpn-enabled').uncheck();
    await next(); await expect(page.locator('[data-step="3"]')).toBeVisible();
    await next(); await expect(page.locator('[data-step="4"]')).toBeVisible();
    await page.locator(`[name="remote-mode"][value="${mode}"]`).check();
    if(mode==='https') {
      await page.fill('#remote-domain','https://bad.example/path');
      await next(); await expect(page.locator('[data-step="4"]')).toBeVisible();
      await page.fill('#remote-domain','maison.example');
      assert.equal(await page.locator('#remote-services input:checked').count(),3);
      await page.screenshot({path:path.join(root,'acces-distant.png'),fullPage:true});
    }
    await next(); await expect(page.locator('[data-step="5"]')).toBeVisible();
    await page.locator('#confirm').check();
    await expect(page.locator('#next')).toBeEnabled({timeout:20000});
    await next(); await expect(page.locator('#post-install')).toBeVisible({timeout:45000});
    if(mode!=='local') {
      await expect(page.locator('#remote-activate')).toBeDisabled();
      await page.locator('#remote-confirm').check();
      await page.locator('#remote-activate').click();
      await expect(page.locator('#remote-status')).toContainText('Simulation : aucune passerelle',{timeout:15000});
      await page.selectOption('#mobile-network','remote');
    } else await expect(page.locator('#remote-result')).toBeHidden();
    await page.selectOption('#mobile-client','qbremote');
    assert.equal(await page.locator('#mobile-service').inputValue(),'qbittorrent');
    await expect(page.locator('#mobile-fields input[aria-label="Port"]')).toHaveValue(mode==='https'?'443':'8080');
    await expect(page.locator('#mobile-fields input[type="password"]')).toHaveCount(1);
    const checkArrExport=async(target,suffix)=>{
      await target.selectOption('#mobile-client','arrcontrol');
      await expect(target.locator('#arr-export')).toBeVisible();
      await target.selectOption('#arr-export-network','remote');
      if(mode==='local')await expect(target.locator('#arr-export-download')).toBeDisabled();
      for(const network of mode==='local'?['local']:['local','remote']){
        await target.selectOption('#arr-export-network',network);
        const pending=target.waitForEvent('download');await target.locator('#arr-export-download').click();
        const exportFile=await pending, exportPath=path.join(project,`${suffix}-${network}.json`);
        assert.match(exportFile.suggestedFilename(),/^plugarr-demo-arr-control-/);
        await exportFile.saveAs(exportPath);
        const data=JSON.parse(fs.readFileSync(exportPath,'utf8'));
        assert.equal(data.version,1);assert.ok(data.server.includes('DEMO'));
        // Demo never runs Seerr onboarding, so its API key is unavailable.
        assert.equal(data.services.length,network==='local'?4:3);
        await expect(target.locator('#arr-export-notice')).toContainText('Seerr');
        const qb=data.services.find(s=>s.serviceId==='qbittorrent');
        assert.ok(qb.config.fields.password);assert.equal(qb.apiKey,null);
        assert.equal(qb.url,qb.config.fields.localUrl);
        assert.equal(new URL(qb.url).protocol,network==='remote'&&mode==='https'?'https:':'http:');
        if(network==='remote'&&mode==='tailscale')assert.equal(new URL(qb.url).hostname,'100.101.102.103');
      }
    };
    await checkArrExport(page,'wizard');
    const checkNzbExport=async(target,suffix)=>{
      await target.selectOption('#mobile-client','nzb360');
      await expect(target.locator('#nzb-export')).toBeVisible();
      await target.selectOption('#nzb-export-network','remote');
      if(mode==='local'){
        await target.locator('#nzb-export-confirm').check();
        await expect(target.locator('#nzb-export-download')).toBeDisabled();
      }
      for(const network of mode==='local'?['local']:['local','remote']){
        await target.selectOption('#nzb-export-network',network);
        await expect(target.locator('#nzb-export-download')).toBeDisabled();
        await target.locator('#nzb-export-confirm').check();
        const pending=target.waitForEvent('download');await target.locator('#nzb-export-download').click();
        const file=await pending;
        assert.match(file.suggestedFilename(),/^plugarr-demo-nzb360-24\.4\.1-/);
        const destination=path.join(project,`${suffix}-nzb360-${network}.zip`);await file.saveAs(destination);
        const bytes=fs.readFileSync(destination);assert.equal(bytes.readUInt32LE(0),0x04034b50);
        assert.ok(bytes.includes(Buffer.from('com.kevinforeman.nzb360_preferences.xml')));
        assert.ok(!bytes.includes(Buffer.from('licensing_')));
      }
    };
    await checkNzbExport(page,'wizard');
    const downloadPromise=page.waitForEvent('download');
    await page.locator('#download-access').click();
    const download=await downloadPromise, destination=path.join(project,'access.html');
    await download.saveAs(destination);
    const offline=await context.newPage();offline.on('pageerror',e=>errors.push(e.message));
    await offline.goto(pathToFileURL(destination).href);
    await offline.selectOption('#mobile-client','qbremote');
    if(mode!=='local')await offline.selectOption('#mobile-network','remote');
    await expect(offline.locator('#mobile-fields input[aria-label="Port"]')).toHaveValue(mode==='https'?'443':'8080');
    await checkArrExport(offline,'offline');
    await checkNzbExport(offline,'offline');
    await offline.setViewportSize({width:390,height:844});
    assert.equal(await offline.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    if(mode==='https')await offline.screenshot({path:path.join(root,'fiche-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    await page.locator('#finish').click();
    console.log(`${mode}: wizard, activation, mobile form and offline export OK`);
  } finally {await context.close();child.kill();}
}
(async()=>{
  const root=fs.mkdtempSync(path.resolve('build/wizard-remote-e2e-'));
  const browser=await chromium.launch({headless:true});
  try {for(const mode of ['https','tailscale','local'])await scenario(browser,mode,root);console.log(`Artifacts: ${root}`);}
  finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
