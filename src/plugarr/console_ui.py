"""Local console additions, embedded so frozen builds need no extra data files."""

from . import connection_map

STYLE = '''<style>
:root{--brand-orange:#ff9e45;--brand-pink:#ec5794;--brand-purple:#ad64e5}
*{box-sizing:border-box}body{font-size:16px}html{scroll-behavior:smooth}.wrap{max-width:1200px;min-width:0}
.card,.grid,.row,.v{min-width:0}.grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))}.mono,.url,.v{overflow-wrap:anywhere}
.brand{font-size:1.5rem;letter-spacing:-.06em;font-weight:800}.brand span{background:linear-gradient(100deg,var(--brand-orange),var(--brand-pink),var(--brand-purple));background-clip:text;-webkit-background-clip:text;color:transparent}
.console-nav{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:28px}
.console-nav a{color:var(--text);text-decoration:none;font-weight:600;font-size:14px}.console-nav .brand{margin-right:auto}
.console-panel{margin:28px 0;padding:24px;border:1px solid var(--line);border-radius:16px;background:var(--panel);scroll-margin-top:24px}
.console-panel h2{margin-top:0}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.metric{padding:18px;background:var(--bg);border:1px solid var(--line);border-radius:12px}.metric strong{display:block;font-size:1.4rem;margin-top:8px}
.console-panel button,.console-panel input,.console-panel select,.console-nav select{font:inherit;padding:10px;min-height:44px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text)}
.console-panel button{cursor:pointer}.console-panel button:hover{border-color:var(--brand-orange)}.console-panel button:disabled{opacity:.5;cursor:wait}
.console-panel label{display:inline-flex;align-items:center;gap:8px;margin:8px 16px 8px 0;flex-wrap:wrap}.console-panel input[type=number]{width:85px}
.console-panel .actions{display:flex;gap:8px;flex-wrap:wrap}.console-panel li{margin:10px 0}.console-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}
.card details{margin-top:12px}.card summary{cursor:pointer;min-height:44px;padding:10px 0;color:var(--muted)}
.check-card{border-left:3px solid var(--brand-orange);padding:14px;margin:12px 0;background:var(--bg)}
[data-theme=brand],[data-theme=dark]{color-scheme:dark;--bg:#0c1116;--panel:#151d26;--text:#f2f5f8;--muted:#9ba9b7;--line:#2a3744;--warn-bg:#2a2018;--warn-line:#ff9e45;--info-bg:#241c30;--info-line:#ad64e5}
[data-theme=light]{color-scheme:light;--bg:#f5f7fa;--panel:#fff;--text:#18232e;--muted:#536372;--line:#ced8e1;--warn-bg:#fff1e4;--warn-line:#a4510b;--info-bg:#f5ecff;--info-line:#7e3daf}
@media(max-width:650px){.summary-grid{grid-template-columns:1fr}.console-panel{padding:16px}.console-nav{gap:12px}table{display:block;overflow-x:auto}.wrap{padding:16px}#graph{min-height:230px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}

/* Palette du site et cartes d'acces lisibles aux largeurs intermediaires. */
body{background:radial-gradient(ellipse at 5% 0%,#ff9e4512,transparent 30rem),radial-gradient(ellipse at 95% 0%,#ad64e514,transparent 34rem),var(--bg)}
.card{border-radius:18px;padding:22px;box-shadow:0 12px 30px #00000010;align-self:start}
.card .title>span:last-child{min-width:0}.card .title strong{line-height:1.4}
.card .url{display:block;line-height:1.6;overflow-wrap:anywhere}.card .note{line-height:1.65}
.card .creds{padding-top:12px}.card .row{display:grid;grid-template-columns:minmax(0,1fr);gap:7px;padding:10px 0}
.card .k{white-space:nowrap;font-size:.8rem;font-weight:600}
.card .v{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-start;gap:8px;line-height:1.5}
.card .secret{display:inline-block;max-width:100%;overflow-wrap:anywhere}.card .secret .dots{white-space:nowrap}
.card :is(button.copy,button.rotate,button.act,button.upgrade){flex:0 0 auto;white-space:nowrap;word-break:normal;overflow-wrap:normal;margin:0;min-height:34px;padding:6px 10px;border-radius:8px;font-size:.78rem;line-height:1.25}
.card :is(button.copy,button.rotate,button.act){color:var(--text);background:var(--bg);border-color:var(--line)}
.card .state{gap:8px;align-items:center}.card .state .label{flex:1;min-width:0;line-height:1.5}
.card .state .upd{flex:1 0 100%;display:flex;flex-wrap:wrap;gap:8px;margin:4px 0}
.card .state .upd[hidden]{display:none}.card .state .actions{flex:1 0 100%;margin:4px 0;display:flex;flex-wrap:wrap;gap:8px}
.card .upd .tag{white-space:normal;overflow-wrap:anywhere;line-height:1.5;padding:4px 8px}
.card summary{white-space:normal;line-height:1.5}
#connections #wiring-graph{--primaire:#ad64e5;--secondaire:#ec5794;--accent:#ff9e45;--scene:#111820;--disque:#151d26;--ligne:#2a3744;--texte:#f2f5f8;--attenue:#9ba9b7}
@media(max-width:650px){body{padding:16px 0 32px}.card{padding:18px}.card :is(button.copy,button.rotate,button.act,button.upgrade){min-height:40px}}
</style>'''

ADMIN_REDESIGN = '''<style>
/* Console locale : même silhouette et même palette que l'assistant. */
[data-theme=brand]{color-scheme:dark;--bg:#0d0e16;--panel:#171821;--text:#eeedf6;--muted:#a8a7bc;--line:#30303f;--warn-bg:#2a201a;--warn-line:#f79b45;--info-bg:#211d2e;--info-line:#ad64e5}
html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;padding:0;background:radial-gradient(circle at 86% 3%,#8b36c91a,transparent 31rem),var(--bg);font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{width:100%;max-width:none;margin:0;display:grid;grid-template-columns:248px minmax(0,1100px);justify-content:center;column-gap:clamp(28px,4vw,72px);padding:0 clamp(22px,4vw,64px) 64px 0}
.wrap>:not(.console-nav){grid-column:2;min-width:0}
.console-nav{grid-column:1;grid-row:1/span 40;position:sticky;top:0;align-self:start;height:100vh;margin:0;padding:36px 24px;background:#11121b;border:0;border-right:1px solid var(--line);display:flex;flex-direction:column;align-items:stretch;gap:7px}
.console-nav .brand{margin:0 0 36px;font-size:1.9rem}.console-kicker{margin:0 0 10px;color:var(--muted);font-size:.75rem;font-weight:750;letter-spacing:.16em}.console-nav a:not(.brand){padding:12px 13px;border-radius:9px;color:var(--muted);font-size:.9rem;font-weight:550}.console-nav a:not(.brand):hover,.console-nav a:not(.brand):focus-visible{background:#8b36c91e;color:var(--text)}.console-local{margin-top:auto;color:var(--muted);font-size:.82rem;line-height:1.55}
header{padding:46px 0 8px}header h1{font-size:clamp(1.85rem,3vw,2.45rem);letter-spacing:-.04em}header p{font-size:.95rem}
h2{margin-top:34px;color:var(--muted);font-size:.78rem;letter-spacing:.14em}
.console-panel{margin:24px 0;padding:22px;border-radius:13px;background:#151620;border-color:var(--line);box-shadow:none}.console-panel h2{margin:0 0 18px;color:var(--text);font-size:1.15rem;letter-spacing:-.015em;text-transform:none}
#overview{background:linear-gradient(125deg,#211b2d,#151620 66%);border-color:#443452}.summary-grid{gap:10px}.metric{padding:16px;background:#11121b;border-color:#343241}.metric strong{margin-top:5px;font-size:1.25rem}
.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{padding:19px;border:1px solid var(--line);border-left:3px solid var(--accent);border-top-width:1px;border-radius:13px;background:#171821;box-shadow:none}.card:hover{border-color:#49465b;border-left-color:var(--accent)}.card .badge{border-radius:9px}.card .badge.app-icon{background:#11121b;border:1px solid #343544}.card .badge.app-icon img{width:30px;height:30px;object-fit:contain;display:block}.card .note{min-height:2.7em}.card details{background:#12131b;border-color:#2b2c39;padding:0 12px;margin:13px 0 0}.card summary{margin:0}.card .creds{border-top-color:var(--line)}
.card :is(button.copy,button.rotate,button.act){background:#11121b}.card button.upgrade,.console-panel button:not(:disabled):hover{border-color:#a85fd5}.banner{border-radius:9px}.banner.warn{background:#2a201a}.banner.info{background:#211d2e}
table{border-radius:12px;background:var(--panel)}th{font-size:.75rem}.note{line-height:1.65}footer{margin-top:34px}
#connections #wiring-graph{--scene:#12131b;--disque:#171821;--ligne:#30303f}
@media(max-width:980px){.wrap{grid-template-columns:210px minmax(0,1fr);column-gap:24px;padding-right:24px}.console-nav{padding:30px 16px}.grid{grid-template-columns:1fr}.summary-grid{grid-template-columns:1fr 1fr}.summary-grid .metric:last-child{grid-column:1/-1}}
@media(max-width:700px){.wrap{display:block;padding:0 18px 42px}.console-nav{position:static;height:auto;margin:0 -18px 22px;padding:16px 18px;border-right:0;border-bottom:1px solid var(--line);display:grid;grid-template-columns:1fr 1fr;gap:7px}.console-nav .brand,.console-kicker,.console-local{grid-column:1/-1}.console-nav .brand{margin-bottom:8px}.console-local{margin:8px 0 0}.console-nav a:not(.brand){padding:10px}.wrap>:not(.console-nav){grid-column:auto}header{padding-top:10px}.summary-grid{grid-template-columns:1fr}.summary-grid .metric:last-child{grid-column:auto}.console-panel{padding:17px}.grid{grid-template-columns:1fr}table{display:block;overflow-x:auto}}
</style>'''

MARKUP = '''<nav class="console-nav" aria-label="Console"><a class="brand" href="#overview">Plug<span>Arr</span></a><p class="console-kicker">ADMINISTRATION</p>
<a href="#overview">Vue d’ensemble</a><a href="#services">Services</a><a href="#connections">Connexions</a><a href="#maintenance">Maintenance</a><a href="#preferences">Paramètres</a><p class="console-local">Console locale · les identifiants restent sur cette machine.</p></nav>'''

OVERVIEW = '''<section id="overview" class="console-panel"><h2>Votre installation, en un regard</h2><div class="summary-grid"><div class="metric">Services en marche<strong id="metric-services">Non vérifiés</strong></div><div class="metric">Liaisons vérifiées<strong id="metric-connections">Non vérifiées</strong></div><div class="metric">Dernière sauvegarde<strong id="metric-backup">Aucune enregistrée</strong></div></div><div id="alerts" aria-live="polite"></div></section>'''

PANELS = connection_map.MARKUP + '''
<section class="console-panel" id="maintenance"><h2>Maintenance</h2><p>Une mise à jour de service nécessite sa recréation. La sauvegarde arrête temporairement les conteneurs pendant la copie.</p><label><input type="checkbox" id="backup-first" checked>Sauvegarder avant la mise à jour d’un service</label><div id="legacy-tools"></div><div id="guided-doctor"></div><h3>PlugArr lui-même</h3><div class="actions"><button id="check-self">Rechercher sur GitHub</button><button id="install-self" hidden>Préparer la mise à jour de l’exécutable</button></div><p id="self-status" aria-live="polite"></p><pre id="release-notes"></pre><h3>Historique des interventions</h3><p>Les 300 dernières interventions de cette console, sans identifiants.</p><ul id="history"></ul></section>
<section class="console-panel" id="preferences"><h2>Paramètres</h2><form id="schedule-form"><h3>Sauvegardes planifiées</h3><p>La console doit rester ouverte. L’heure est celle de la machine qui exécute PlugArr. Une sauvegarde manquée attend la prochaine plage prévue.</p><label><input id="schedule-enabled" type="checkbox">Activer</label><label>Tous les <input id="schedule-days" type="number" min="1" max="30" value="1" required> jours</label><label>À <input id="schedule-hour" type="number" min="0" max="23" value="3" required> heures</label><label>Conserver <input id="schedule-keep" type="number" min="1" max="90" value="7" required> archives</label><h3>Alertes dans la console</h3><p>Les services sont contrôlés pendant l’ouverture de la page. Le VPN est contrôlé lors d’un diagnostic.</p><label><input type="checkbox" id="notify-services" checked>Services</label><label><input type="checkbox" id="notify-backup" checked>Sauvegardes</label><label><input type="checkbox" id="notify-vpn" checked>VPN</label><p><button type="submit">Enregistrer les préférences</button></p><p id="settings-status" role="status"></p></form></section>'''

SCRIPT = r'''<script>
(()=>{
const $=id=>document.getElementById(id);const nativeFetch=window.fetch.bind(window);
// Extend existing update controls without duplicating their behaviour.
window.fetch=async(input,options)=>{let o=options;if(input==='/api/update'&&o&&o.body){const body=JSON.parse(o.body);body.backup_first=$('backup-first').checked;o={...o,body:JSON.stringify(body)};}let r;try{r=await nativeFetch(input,o)}catch(e){if(input==='/api/status')window.PlugArrMap.updateStatus({engine_available:false});throw e;}
if(input==='/api/status'&&r.ok)r.clone().json().then(d=>{$('metric-services').textContent=d.engine_available===false?'Docker inaccessible':d.services.filter(s=>s.up).length+' / '+d.services.length;window.PlugArrMap.updateStatus(d)}).catch(()=>window.PlugArrMap.updateStatus({engine_available:false}));
if(input==='/api/status'&&!r.ok)window.PlugArrMap.updateStatus({engine_available:false});
if(input==='/api/doctor'&&r.ok)r.clone().json().then(d=>{const box=$('guided-doctor');box.replaceChildren();d.checks.forEach(c=>{const card=document.createElement('div');card.className='check-card';const title=document.createElement('strong');title.textContent=(c.ok?'✓ ':'! ')+c.name;const detail=document.createElement('p');detail.textContent=c.detail;const next=document.createElement('p');next.textContent=c.next_step;card.append(title,detail,next);box.append(card)})}).catch(()=>{});return r;};
const api=async(path,body)=>{const r=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok||d.error)throw new Error(d.error||'Opération impossible');return d};
document.documentElement.dataset.theme='brand';
const tools=document.querySelector('.outils'),report=$('rapport-doctor');if(tools)$('legacy-tools').append(tools);if(report)$('legacy-tools').append(report);
let loadedSettings=false;
async function refresh(){try{const d=await api('maintenance');$('metric-backup').textContent=d.last_backup?new Date(d.last_backup).toLocaleString():'Aucune enregistrée';$('history').replaceChildren();d.events.slice(-30).reverse().forEach(e=>{const li=document.createElement('li');li.textContent=new Date(e.at).toLocaleString()+' · '+e.action+' '+e.service+' · '+(e.ok?'réussi':'à vérifier');$('history').append(li)});$('alerts').replaceChildren();Object.entries(d.alerts).filter(([k,v])=>v.active&&d.notifications[k.split(':')[0]]).forEach(([k,a])=>{const p=document.createElement('p');p.textContent='⚠ '+a.title;$('alerts').append(p)});if(!loadedSettings){['enabled','days','hour','keep'].forEach(k=>{const el=$('schedule-'+k);if(k==='enabled')el.checked=d.schedule[k];else el.value=d.schedule[k]});['services','backup','vpn'].forEach(k=>$('notify-'+k).checked=d.notifications[k]);loadedSettings=true}}catch(e){$('settings-status').textContent=e.message}}
$('schedule-form').onsubmit=async e=>{e.preventDefault();try{await api('maintenance',{schedule:{enabled:$('schedule-enabled').checked,days:+$('schedule-days').value,hour:+$('schedule-hour').value,keep:+$('schedule-keep').value},notifications:{services:$('notify-services').checked,backup:$('notify-backup').checked,vpn:$('notify-vpn').checked}});$('settings-status').textContent='Préférences enregistrées.'}catch(err){$('settings-status').textContent=err.message}};
const graph=()=>window.PlugArrMap.load(api,refresh);
$('check-self').onclick=async()=>{const button=$('check-self');button.disabled=true;$('self-status').textContent='Recherche…';try{const d=await api('self-update');$('self-status').textContent='Installée : '+d.current+' · GitHub : '+d.latest+(d.available?' · Mise à jour disponible.':' · À jour.');$('release-notes').textContent=d.notes;$('install-self').hidden=!(d.available&&d.verified_asset)}catch(e){$('self-status').textContent=e.message}finally{button.disabled=false}};
$('install-self').onclick=async()=>{const b=$('install-self');b.disabled=true;try{const d=await api('self-update',{});$('self-status').textContent=d.message}catch(e){$('self-status').textContent=e.message}finally{b.disabled=false}};
refresh();graph();setInterval(refresh,15000);api('status').catch(()=>{});
})();
</script>'''


def enhance(page):
    page = page.replace('<html ', '<html data-theme="brand" ', 1)
    page = page.replace('</head>', STYLE + ADMIN_REDESIGN + connection_map.STYLE + '</head>')
    page = page.replace('<div class="wrap">', '<div class="wrap">' + MARKUP, 1)
    page = page.replace('</header>', '</header>' + OVERVIEW, 1)
    page = page.replace('  <h2>Services</h2>', '  <h2 id="services">Services</h2>')
    page = page.replace('  <footer>', PANELS + '  <footer>')
    return page.replace('</body>', connection_map.script() + SCRIPT + '</body>')
