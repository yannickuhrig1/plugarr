"""Administration adapter for the same offline SVG renderer as the wizard."""
import json
from functools import lru_cache
from pathlib import Path

WEB = Path(__file__).parent / 'web'
STYLE = '<style>' + (WEB / 'graph.css').read_text(encoding='utf-8') + '''
#connections{padding:24px;overflow:hidden}#connections #wiring-graph{margin:0}
#connections .graph-header .actions{margin-left:auto}#connections .graph-header button{font-size:14px}
#connections #map-logo{width:34px;height:34px;flex:none}
#connections .map-bottom{margin-top:24px}.map-detail{padding:20px;background:var(--bg);border:1px solid var(--line);border-radius:12px}
#connections .map-detail h3{margin:0 0 12px}.map-detail p{overflow-wrap:anywhere;line-height:1.5}.map-kicker{color:var(--muted);font-size:14px}
#connections .map-result[data-state=failed]{color:#ed637a}#connections details{margin-top:20px}
#connections .connection-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}
#connections .connection-row p{font-size:14px;color:var(--muted);margin:5px 0}#connections .connection-row button{flex-shrink:0}
#connections #wiring-graph .graph-count{color:var(--text)}
#connections .map-note{color:var(--muted);font-size:14px;line-height:1.6}
#connections #wiring-graph .graph-status,#connections #wiring-graph .graph-legend,#connections #wiring-graph .graph-state-list{color:var(--muted)}
#connections [hidden]{display:none!important}
@media(max-width:650px){#connections{padding:16px}#connections .map-detail{padding:16px}}
</style>'''

MARKUP = '''<section class="console-panel" id="connections">
<div id="wiring-graph">
<div class="graph-header"><svg id="map-logo" viewBox="0 0 40 40" aria-hidden="true"><defs><linearGradient id="map-brand-gradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f79b45"/><stop offset=".5" stop-color="#e4638a"/><stop offset="1" stop-color="#8b36c9"/></linearGradient></defs><rect x="2" y="2" width="36" height="36" rx="11" fill="url(#map-brand-gradient)"/><path d="M12 27V13h8.3c4.4 0 7.2 2.3 7.2 6.1 0 3.9-2.8 6.2-7.2 6.2h-3.6V27H12zm4.7-5.5h3.2c1.8 0 2.8-.8 2.8-2.4 0-1.5-1-2.3-2.8-2.3h-3.2v4.7z" fill="#fff"/></svg><h2>Carte des connexions</h2><div class="actions"><button id="map-reset" type="button">Tout afficher</button></div></div>
<p id="map-count" class="graph-status" role="status">Chargement de la configuration…</p>
<div class="scene" tabindex="0" role="region" aria-label="Schéma des connexions, défilement horizontal sur petit écran"><div id="graph"></div></div>
<div class="graph-legend" aria-label="Légende"><span class="done">Dernier test réussi</span><span>À vérifier</span><span class="failed">Test en échec</span><span class="running">Test en cours ou extrémité indisponible</span><span class="structural">Configuration · sans test</span></div>
<div id="map-progress" class="graph-count"></div><progress id="map-bar" class="graph-progress" max="1" value="0" aria-label="Liaisons testées"></progress>
<details><summary>État des applications</summary><ul id="map-states" class="graph-state-list"></ul></details>
</div>
<div class="map-bottom"><div id="map-detail" class="map-detail" tabindex="-1" aria-live="polite"></div><details><summary id="map-list-title">Liste des liaisons</summary><div id="connection-list"></div></details><p class="map-note">Les états des conteneurs et les résultats enregistrés sont actualisés toutes les 5 secondes. Sélectionnez un câble pour lancer un test. Un test réussi est daté ; il n’est pas relancé automatiquement. Les animations représentent les états affichés, pas un débit réseau. Le lien VPN décrit la configuration, sans certifier le tunnel.</p></div>
</section>'''


@lru_cache(maxsize=1)
def script():
    icons = json.loads((WEB.parent / 'data' / 'connection_icons.json').read_text(encoding='utf-8'))
    adapter = (WEB / 'admin-graph.js').read_text(encoding='utf-8')
    adapter = adapter.replace('__ICONS__', json.dumps(icons).replace('/', r'\/'))
    return '<script>' + (WEB / 'graph.js').read_text(encoding='utf-8') + '</script><script>' + adapter + '</script>'
