"""Self-contained mobile configuration forms for private HTML exports."""
import json
from pathlib import Path

from . import catalog, remote_access


def append_to(page, cfg, host, *, remote=None, demo=False):
    en = cfg.ui_language == "en"
    services = [{"id": sid, "name": catalog.get(sid).display_name,
                 "url": inst.url(host), "local_url": inst.url(host),
                 "remote_url": (remote or {}).get("urls", {}).get(sid, ""),
                 "username": inst.username or "", "password": inst.password or "", "api_key": inst.api_key or ""}
                for sid, inst in cfg.services.items() if sid in (*remote_access.SUPPORTED, "prowlarr", "seerr", "sabnzbd", "lidarr", "transmission")]
    if not services:
        return page
    remote_info = remote or remote_access.summary(cfg, demo=demo)
    data = json.dumps({"services": services, "demo": demo,
                       "remote": {k: remote_info.get(k) for k in ("mode", "status", "message")}}, ensure_ascii=True)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    title = "Set up my phone" if en else "Configurer mon téléphone"
    script = (Path(__file__).parent / "web" / "remote.js").read_text(encoding="utf-8")
    markup = f'''<section id="mobile-report" style="max-width:1000px;margin:32px auto;padding:24px">
<h2>{title}</h2><p>{"Private snapshot. Do not share this file." if en else "Copie privée de vos accès. Ne partagez pas ce fichier."}</p>
<label>{"Mobile app" if en else "Application mobile"}<select id="mobile-client"><option value="nzb360">nzb360</option><option value="qbremote">qbRemote (Android)</option><option value="other">{"Other" if en else "Autre"}</option></select></label>
<label>Application<select id="mobile-service"></select></label>
<label>{"Connection" if en else "Connexion"}<select id="mobile-network"><option value="local">Local</option><option value="remote">Remote</option></select></label>
<p id="mobile-help"></p><div id="mobile-fields"></div><p id="mobile-copy-status" role="status"></p></section>
<style>#mobile-report [hidden]{{display:none!important}}#mobile-report label{{display:grid;gap:8px;margin:12px 0}}#mobile-report select,#mobile-report input{{color:var(--text);background:var(--panel);border:1px solid var(--muted);border-radius:8px;padding:12px;min-width:0;width:100%;font:inherit}}#mobile-report .mobile-field{{display:flex;align-items:end;gap:10px;margin:14px 0}}#mobile-report .mobile-field label{{flex:1;margin:0;min-width:0}}#mobile-report button{{min-height:44px;padding:10px;cursor:pointer}}@media(max-width:600px){{#mobile-report .mobile-field{{flex-wrap:wrap}}#mobile-report .mobile-field label{{flex-basis:100%}}}}</style>
<script>{script}</script><script>PlugArrRemote.mountMobile({data});</script>'''
    return page.replace("</body>", markup + "\n</body>")
