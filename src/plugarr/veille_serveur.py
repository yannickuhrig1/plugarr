"""Serveur de la veille : une page en LECTURE SEULE, pour un conteneur.

`plugarr veille` sert l'etat des services, les debits, la sortie du VPN et
la place libre. Il n'a AUCUNE route qui change quoi que ce soit : pas de
POST hors connexion et deconnexion, pas de socket Docker. C'est ce qui lui
permet de tourner dans un conteneur, joignable depuis un telephone, quand la
console, elle, reste sur l'hote.

Acces :

- avec le mot de passe de la console (`plugarr admin-password`), meme
  empreinte, memes sessions limitees ;
- sans mot de passe, seulement sur 127.0.0.1, avec un jeton tire au hasard
  comme `plugarr serve`. Hors de 127.0.0.1, la commande refuse de demarrer :
  la page montre l'adresse de sortie du VPN, elle ne s'expose pas sans verrou.
"""

from __future__ import annotations

import hmac
import html
import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import adminauth, veille
from .i18n import t
from .models import StackConfig

COOKIE = "plugarr_veille"
BOUCLES = ("127.0.0.1", "localhost", "::1")

_STYLE = """<style>
:root{color-scheme:dark;--bg:#0d0e16;--panel:#151620;--text:#eeedf6;--muted:#a8a7bc;--line:#30303f;--ok:#6fcf8e;--ko:#ff7a7a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.6rem;margin:8px 0 4px}h2{font-size:1.05rem;margin:28px 0 12px}
.note{color:var(--muted);font-size:.9rem}.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:10px}
.carte{padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px;min-width:0;overflow-wrap:anywhere}
.carte strong{display:block;font-size:1.15rem;margin-top:4px}.carte small{display:block;color:var(--muted)}
.etat{display:flex;align-items:center;gap:8px}.etat::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--ko);flex:none}.etat.up::before{background:var(--ok)}
meter{width:100%;height:14px}.disque{margin:12px 0}form{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
input,button{font:inherit;padding:10px;min-height:44px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--text)}button{cursor:pointer}
</style>"""

_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Veille PlugArr</title>{style}</head>
<body><main><h1>Veille PlugArr</h1><p class="note">Lecture seule : cette page ne peut rien arrêter ni modifier. Rafraîchie toutes les 5 secondes tant qu'elle est affichée.</p>
<h2>Services</h2><div id="services" class="grille"></div>
<h2>Débits</h2><div id="debits" class="grille"></div>
<h2>Sortie du VPN</h2><p id="vpn">Lecture…</p>
<h2>Disques</h2><div id="disques"></div>
<p id="etat" class="note" role="status"></p>
<form method="post" action="/logout"><button type="submit">Se déconnecter</button></form></main>
<script>
(()=>{{const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}};
const nb=(x,d)=>x.toLocaleString('fr-FR',{{minimumFractionDigits:d,maximumFractionDigits:d}});
const debit=o=>o==null?'non mesuré':o<1024?o+' o/s':o<1048576?nb(o/1024,0)+' Ko/s':nb(o/1048576,1)+' Mo/s';
const taille=o=>o>=1099511627776?nb(o/1099511627776,2)+' To':nb(o/1073741824,1)+' Go';
async function lire(){{if(document.hidden)return;try{{const r=await fetch('/api/veille',{{credentials:'same-origin'}});if(r.status===401){{location.reload();return}}const d=await r.json();
$('services').replaceChildren(...(d.services||[]).map(s=>{{const c=el('div',undefined,'carte');c.append(el('span',s.name,'etat'+(s.up?' up':'')),el('small',s.up?'répond':'ne répond pas · '+s.detail));return c}}));
$('debits').replaceChildren(...(d.debits.length?d.debits.map(c=>{{const m=el('div',undefined,'carte');m.append(c.name,el('strong',c.ok?'↓ '+debit(c.down)+(c.up==null?'':' · ↑ '+debit(c.up)):'Injoignable'),el('small',c.detail));return m}}):[el('p','Aucun client de téléchargement installé.')]));
const v=d.vpn;$('vpn').textContent=v==null?'Aucun VPN configuré : les téléchargements sortent par votre propre adresse.':v.ok?v.ip+' · '+[v.ville,v.pays].filter(Boolean).join(', ')+(v.operateur?' · '+v.operateur:''):'Non vérifiée : '+v.detail;
$('disques').replaceChildren(...d.disques.map(g=>{{const b=el('div',undefined,'disque');const m=el('meter');m.min=0;m.max=100;m.low=80;m.high=90;m.optimum=0;m.value=g.utilise_pct;const noms=g.dossiers.length>4?g.dossiers.slice(0,4).join(', ')+' et '+(g.dossiers.length-4)+' autres':g.dossiers.join(', ');b.append(el('strong',taille(g.libre)+' libres sur '+taille(g.total)+' ('+nb(g.utilise_pct,1)+' % utilisés)'),m,el('small',g.chemin+' · '+noms,'note'));return b}}));
$('etat').textContent='Relevé à '+new Date().toLocaleTimeString()}}catch(e){{$('etat').textContent='Veille indisponible : '+e.message}}}}
lire();setInterval(lire,5000);document.addEventListener('visibilitychange',lire)}})();
</script></body></html>"""

_CONNEXION = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Veille PlugArr</title>{style}</head>
<body><main><h1>Veille PlugArr</h1><p class="note">Mot de passe de la console d'administration.</p>
<form method="post" action="/login"><input type="password" name="password" autocomplete="current-password" aria-label="Mot de passe" required autofocus><button type="submit">Entrer</button></form>
<p role="alert">{erreur}</p></main></body></html>"""


class VeilleRefusee(ValueError):
    """La veille ne demarre pas : exposee sans mot de passe."""


def verifier_exposition(cfg: StackConfig, hote: str) -> None:
    if hote not in BOUCLES and not cfg.admin_password_hash:
        raise VeilleRefusee(
            t(
                "La veille ecoute sur le reseau mais aucun mot de passe n'est pose. "
                "Lancez d'abord `plugarr admin-password` sur l'hote."
            )
        )


class _Gestionnaire(BaseHTTPRequestHandler):
    cfg: StackConfig
    interne: bool
    jeton: str
    sessions: adminauth.Sessions

    server_version = "plugarr"
    sys_version = ""

    def log_message(self, *args: object) -> None:
        pass  # Ni jeton ni adresse dans un journal.

    # -- envoi ---------------------------------------------------------------

    def _envoyer(self, statut, corps: bytes, type_: str, cookie: str | None = None) -> None:
        self.send_response(statut)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie is not None:
            self.send_header(
                "Set-Cookie", f"{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/"
            )
        self.end_headers()
        self.wfile.write(corps)

    def _html(self, statut, page: str, cookie: str | None = None) -> None:
        self._envoyer(statut, page.encode("utf-8"), "text/html; charset=utf-8", cookie)

    def _connexion(
        self, statut=HTTPStatus.UNAUTHORIZED, erreur: str = "", cookie: str | None = None
    ) -> None:
        self._html(statut, _CONNEXION.format(style=_STYLE, erreur=html.escape(erreur)), cookie)

    # -- authentification ----------------------------------------------------

    def _cookie(self) -> str:
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == COOKIE:
                return valeur
        return ""

    def _autorise(self) -> bool:
        presente = self._cookie()
        if self.sessions.valid(presente):
            return True
        return bool(self.jeton) and hmac.compare_digest(presente.encode(), self.jeton.encode())

    # -- routes --------------------------------------------------------------

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            propose = (parse_qs(url.query).get("t") or [""])[0]
            if self.jeton and propose and hmac.compare_digest(propose.encode(), self.jeton.encode()):
                self._html(HTTPStatus.OK, _PAGE.format(style=_STYLE), cookie=self.jeton)
            elif self._autorise():
                self._html(HTTPStatus.OK, _PAGE.format(style=_STYLE))
            else:
                self._connexion(HTTPStatus.OK if self.cfg.admin_password_hash else HTTPStatus.UNAUTHORIZED,
                                "" if self.cfg.admin_password_hash else "Jeton absent ou invalide.")
        elif url.path == "/api/veille":
            if not self._autorise():
                self._envoyer(HTTPStatus.UNAUTHORIZED, b'{"error":"session"}', "application/json")
                return
            donnees = veille.payload(self.cfg, interne=self.interne, avec_etats=True)
            self._envoyer(HTTPStatus.OK, json.dumps(donnees).encode(), "application/json")
        else:
            self._envoyer(HTTPStatus.NOT_FOUND, b"", "text/plain")

    def do_POST(self) -> None:
        longueur = int(self.headers.get("Content-Length") or 0)
        # 4 Ko : un formulaire de connexion n'a aucune raison d'etre plus gros.
        corps = self.rfile.read(min(max(longueur, 0), 4096)).decode("utf-8", "replace")
        route = urlparse(self.path).path
        if route == "/logout":
            self.sessions.close(self._cookie())
            # Cookie vide : le navigateur oublie la session.
            self._connexion(HTTPStatus.OK, "Déconnecté.", cookie="")
            return
        if route != "/login" or not self.cfg.admin_password_hash:
            self._envoyer(HTTPStatus.NOT_FOUND, b"", "text/plain")
            return
        if self.sessions.locked_out:
            self._connexion(
                HTTPStatus.TOO_MANY_REQUESTS,
                f"Trop de tentatives. Réessayez dans {self.sessions.retry_in()} s.",
            )
            return
        propose = (parse_qs(corps).get("password") or [""])[0]
        if not adminauth.verify_password(propose, self.cfg.admin_password_hash):
            self.sessions.record_failure()
            self._connexion(HTTPStatus.UNAUTHORIZED, "Mot de passe refusé.")
            return
        self.sessions.clear_failures()
        self._html(HTTPStatus.OK, _PAGE.format(style=_STYLE), cookie=self.sessions.open())


def construire(
    cfg: StackConfig, *, hote: str, port: int, interne: bool
) -> tuple[ThreadingHTTPServer, str]:
    """Serveur pret a servir, et jeton d'acces (vide avec un mot de passe)."""
    verifier_exposition(cfg, hote)
    jeton = "" if cfg.admin_password_hash else secrets.token_urlsafe(24)
    gestionnaire = type(
        "Gestionnaire",
        (_Gestionnaire,),
        {"cfg": cfg, "interne": interne, "jeton": jeton, "sessions": adminauth.Sessions()},
    )
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    return serveur, jeton
