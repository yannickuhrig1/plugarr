"""Page d'acces generee a la fin de l'installation.

Le tableau du terminal disparait des qu'on ferme la fenetre. Cette page reste, et
evite d'avoir a retrouver quel service ecoute sur quel port.

Trois pieges traites ici :

- **Les secrets.** La page contient mots de passe et cles API. Elle est ecrite en
  chmod 600 et couverte par le .gitignore genere, et les valeurs sensibles sont
  masquees jusqu'au clic : une page qu'on montre a quelqu'un ne doit pas afficher
  une cle API d'entree.
- **`localhost` ment.** Installee sur un NAS et ouverte depuis un portable, une URL
  en localhost pointe vers le portable. On detecte l'adresse du LAN.
- **Les liens `file://` ne marchent qu'en local.** Sur un NAS ils sont morts. Le
  chemin est donc donne en texte copiable AVANT d'etre donne en lien, et la limite
  est ecrite noir sur blanc.
"""

from __future__ import annotations

import html
import json
import socket
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import __version__, catalog, i18n
from .i18n import t
from .layout import CONTAINER_PATHS
from .models import Category, StackConfig

FILENAME = "acces-plugarr.html"

#: Couleur d'accent par categorie, pour distinguer les cartes d'un coup d'oeil.
_ACCENTS = {
    Category.ARR: "#4c8dff",
    Category.DOWNLOAD: "#31c48d",
    Category.MEDIA: "#a855f7",
    Category.UI: "#f59e0b",
}


# Palette orange, rose et violet du site PlugArr, pour la console pilotee.
_BRAND_ACCENTS = {Category.ARR: "#ec5794", Category.DOWNLOAD: "#ff9e45",
                  Category.MEDIA: "#ad64e5", Category.UI: "#ff9e45"}


@lru_cache(maxsize=1)
def _application_icons() -> dict[str, str]:
    """Logos autonomes déjà utilisés par le graphe, sans requête externe."""
    path = Path(__file__).parent / "data" / "connection_icons.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _badge(spec) -> str:
    """Logo d'application, avec l'initiale comme repli vérifiable."""
    icon = _application_icons().get(spec.id)
    if icon:
        return (
            '<span class="badge app-icon">'
            f'<img src="{html.escape(icon, quote=True)}" alt="" width="30" height="30">'
            "</span>"
        )
    return f'<span class="badge">{html.escape(spec.display_name[0])}</span>'


def primary_lan_ip() -> str | None:
    """Adresse de la machine sur le reseau local.

    Le connect UDP n'envoie aucun paquet : il se contente de demander au noyau par
    quelle interface il sortirait. 192.0.2.0/24 est TEST-NET-1, jamais routee.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("192.0.2.1", 80))
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("127.") else address


def resolve_host(cfg: StackConfig) -> tuple[str, str | None]:
    """Hote a utiliser dans les liens, et note explicative eventuelle."""
    if cfg.host not in ("localhost", "127.0.0.1"):
        return cfg.host, None
    lan = primary_lan_ip()
    if lan:
        return lan, t(
            "Les liens utilisent {adresse}, l'adresse de cette machine sur le "
            "reseau local, et non localhost : la page reste donc valable depuis "
            "un autre appareil.",
            adresse=lan,
        )
    return cfg.host, t(
        "Les liens pointent vers localhost. Depuis un autre appareil, "
        "remplacez-le par l'adresse de cette machine sur le reseau."
    )


def _copiable(valeur: str) -> str:
    """Une valeur affichee en clair, avec son bouton de copie.

    L'identifiant n'est pas un secret : le masquer n'aurait pas de sens. Mais
    on le recopie autant que le mot de passe — dans un formulaire de connexion,
    juste avant lui — et il n'avait pas de bouton.

    Le meme bouton que partout ailleurs : c'est le script de la page qui
    l'anime, sur `button.copy[data-value]`.
    """
    safe = html.escape(valeur)
    return (
        f"{safe}"
        f'<button class="copy" data-value="{safe}" title="{t("Copier")}">'
        f'{t("copier")}</button>'
    )


def _secret(value: str | None, label: str) -> str:
    if not value:
        return '<span class="none">—</span>'
    safe = html.escape(value)
    return (
        f'<span class="secret" data-value="{safe}" '
        f'title="{t("Cliquer pour afficher {quoi}", quoi=label)}">'
        f"<span class=\"dots\">••••••••</span></span>"
        f'<button class="copy" data-value="{safe}" title="{t("Copier")}">'
        f'{t("copier")}</button>'
    )


#: Ce que chaque rotation sait faire, et pour qui. Un secret dont le
#: renouvellement n'a pas ete verifie contre le service n'a pas de bouton : un
#: bouton qui casse vaut moins que pas de bouton.
_ROTATIONS = {
    "password": (
        catalog.ROTATABLE_FAMILIES,
        "Tirer un nouveau mot de passe et recabler",
    ),
    # Seuls les *arr ont une cle API que plugarr choisit. Celle de Jellyfin est
    # emise par Jellyfin lui-meme, lors de son assistant de demarrage.
    "api_key": (("arr",), "Tirer une nouvelle cle API et recabler"),
}


def _bouton_rotation(spec, quoi: str, live: bool) -> str:
    """Bouton de renouvellement, sur la page PILOTEE uniquement.

    La page statique n'execute rien : un bouton mort y serait pire que pas de
    bouton du tout.
    """
    familles, infobulle = _ROTATIONS[quoi]
    if not live or spec.api_family not in familles:
        return ""
    return (
        f'<button class="rotate" data-service="{spec.id}" data-what="{quoi}" '
        f'title="{t(infobulle)}">{t("renouveler")}</button>'
    )


_CONTROLS = """        <div class="state" data-service="{sid}">
          <span class="dot" title="{etat_inconnu}"></span><span class="label">{verification}</span>
          <span class="upd" data-service="{sid}" hidden></span>
          <span class="actions">
            <button class="act" data-service="{sid}" data-action="start">{demarrer}</button>
            <button class="act" data-service="{sid}" data-action="restart">{redemarrer}</button>
            <button class="act danger" data-service="{sid}" data-action="stop">{arreter}</button>
          </span>
        </div>
"""


def _controls(sid: str) -> str:
    """Boutons d'un service, formes A L'AFFICHAGE.

    Meme raison que pour la barre d'outils : les former a l'import figerait
    leurs libelles dans la langue chargee a ce moment-la.
    """
    return _CONTROLS.format(
        sid=sid,
        etat_inconnu=t("etat inconnu"),
        verification=t("verification…"),
        demarrer=t("demarrer"),
        redemarrer=t("redemarrer"),
        arreter=t("arreter"),
    )


def _cards(cfg: StackConfig, host: str, live: bool = False) -> str:
    blocks = []
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        spec, inst = catalog.get(sid), cfg.services[sid]
        url = f"http://{host}:{inst.host_port}"
        accent = (_BRAND_ACCENTS if live else _ACCENTS).get(spec.category, "#64748b")
        rows = ""
        if inst.username:
            # L'identifiant se copie comme le reste. Il n'est pas secret, donc
            # il reste affiche en clair : c'est le BOUTON qui manquait, pas le
            # masquage. Demande a l'usage.
            rows += (
                f'<div class="row"><span class="k">{t("Identifiant")}</span>'
                f'<span class="v mono">{_copiable(inst.username)}</span></div>'
            )
        if inst.password:
            rows += (
                f'<div class="row"><span class="k">{t("Mot de passe")}</span>'
                f'<span class="v" data-secret="{spec.id}:password">'
                f'{_secret(inst.password, t("le mot de passe"))}'
                f'{_bouton_rotation(spec, "password", live)}</span></div>'
            )
        if inst.api_key:
            rows += (
                f'<div class="row"><span class="k">{t("Cle API")}</span>'
                f'<span class="v" data-secret="{spec.id}:api_key">'
                f'{_secret(inst.api_key, "la cle API")}'
                f'{_bouton_rotation(spec, "api_key", live)}</span></div>'
            )
        controls = _controls(spec.id) if live else ""
        # Un service sans port publie n'a pas d'interface a ouvrir. Recyclarr
        # tourne sur une planification. Lui donner un lien vers le port 0 offrirait
        # une carte cliquable qui n'aboutit nulle part : le lecteur en conclurait
        # que l'installation a echoue, alors qu'elle a reussi.
        if inst.has_web_ui:
            title = (
                f'<a class="title" href="{url}" target="_blank" rel="noopener">'
                f'{_badge(spec)}'
                f"<span><strong>{html.escape(spec.display_name)}</strong>"
                f'<span class="url">{html.escape(url)}</span></span></a>'
            )
        else:
            title = (
                '<div class="title headless">'
                f'{_badge(spec)}'
                f"<span><strong>{html.escape(spec.display_name)}</strong>"
                f'<span class="url">{t("tache de fond, sans interface")}</span>'
                "</span></div>"
            )
        blocks.append(
            f"""      <article class="card" style="--accent:{accent}">
        {title}
        <p class="note">{html.escape(t(spec.notes))}</p>
{controls}        <details><summary>Identifiants et clés API</summary><div class="creds">{rows}</div></details>
      </article>"""
        )
    return "\n".join(blocks)


def _ajouts(cfg: StackConfig) -> str:
    """Section « ajouter un service », sur la page pilotee uniquement.

    Une stack grandit. Jusqu'ici, ajouter Lidarr six mois apres imposait de
    relancer l'installation entiere en cochant tout — avec le risque de perdre
    les mots de passe des services qui ne stockent que des empreintes.
    """
    absents = [
        sid
        for sid in catalog.STARTUP_ORDER
        if not cfg.enabled(sid) and not catalog.get(sid).internal
    ]
    if not absents:
        return ""
    lignes = ""
    for sid in absents:
        spec = catalog.get(sid)
        # Afficher les dépendances réellement choisies par le même résolveur que
        # l'installation, y compris les alternatives (Flood choisit qBittorrent
        # si aucun client compatible n'est déjà présent).
        prerequis = [
            dep
            for dep in catalog.resolve_dependencies([sid, *cfg.services])
            if dep != sid and not cfg.enabled(dep)
        ]
        note = html.escape(t(spec.notes))
        if prerequis:
            noms = ", ".join(catalog.get(d).display_name for d in prerequis)
            note += (
                ' <span class="dim">'
                + html.escape(t("— tirera aussi {noms}", noms=noms))
                + "</span>"
            )
        lignes += (
            f'      <article class="card add" data-add="{spec.id}">\n'
            f'        <div class="title headless">{_badge(spec)}'
            f"<span><strong>{html.escape(spec.display_name)}</strong>"
            f'<span class="url">{t("pas encore installe")}</span></span></div>\n'
            f'        <p class="note">{note}</p>\n'
            f'        <div class="state"><span class="actions">'
            f'<button class="install" data-service="{spec.id}">'
            f'{t("installer et cabler")}</button>'
            f"</span></div>\n      </article>\n"
        )
    return (
        "\n  <h2>" + t("Ajouter un service") + "</h2>\n"
        + '  <p class="note">'
        + t(
            "Le service est installe puis <b>cable dans les deux sens</b> : il "
            "apprend a parler aux autres, et les autres apprennent a lui parler. "
            "Rien n'est arrete, et aucun mot de passe existant n'est touche."
        )
        + "</p>\n"
        f'  <div class="grid">\n{lignes}  </div>\n'
    )


def _has_download_client(cfg: StackConfig) -> bool:
    return any(cfg.enabled(sid) for sid in catalog.DOWNLOAD_CLIENTS)


def _paths(cfg: StackConfig) -> str:
    entries = [
        (t("Films"), f"{cfg.data_root}/media/movies", CONTAINER_PATHS["media_movies"]),
        (t("Series"), f"{cfg.data_root}/media/tv", CONTAINER_PATHS["media_tv"]),
        (
            t("Telechargements"),
            f"{cfg.data_root}/torrents",
            CONTAINER_PATHS["torrents_root"],
        ),
        (t("Configurations"), cfg.config_root, "—"),
    ]
    if cfg.enabled("lidarr"):
        entries.insert(
            2, (t("Musique"), f"{cfg.data_root}/media/music", "/data/media/music")
        )

    rows = ""
    for label, host_path, container_path in entries:
        safe = html.escape(host_path)
        link = html.escape("file:///" + host_path.lstrip("/").replace("\\", "/"))
        rows += f"""        <tr>
          <td>{html.escape(label)}</td>
          <td class="mono">{safe} <button class="copy" data-value="{safe}">{t("copier")}</button></td>
          <td class="mono dim">{html.escape(container_path)}</td>
          <td><a href="{link}">{t("ouvrir")}</a></td>
        </tr>"""
    return rows


def render(cfg: StackConfig, *, failed: int = 0, live: bool = False) -> str:
    """Rend la page.

    `live=False` produit le fichier statique ecrit apres l'installation.
    `live=True` ajoute l'etat des services et les boutons de controle ; cette
    forme n'est servie que par `plugarr serve`, qui apporte le serveur capable
    de repondre aux appels.
    """
    host, host_note = resolve_host(cfg)
    # Le format de date suit la langue : jour/mois pour le francais, mois/jour
    # pour l'anglais. Afficher « 05/09 » a un anglophone se lit « 9 mai ».
    generated = datetime.now().astimezone().strftime(t("%d/%m/%Y a %H:%M"))
    count = sum(1 for sid in catalog.STARTUP_ORDER if cfg.enabled(sid))

    banner = ""
    if failed:
        banner = (
            '<div class="banner warn"><strong>'
            + t("{nombre} lien(s) n\'ont pas pu etre etablis.", nombre=failed)
            + "</strong> "
            + t("Lancez <code>plugarr doctor</code> pour un diagnostic.")
            + "</div>"
        )
    if host_note:
        banner += f'<div class="banner info">{html.escape(host_note)}</div>'
    if not cfg.vpn_enabled and _has_download_client(cfg):
        banner += (
            '<div class="banner warn"><strong>'
            + t("Aucun VPN.")
            + "</strong> "
            + t(
                "Le trafic BitTorrent sort sur l'adresse IP publique de "
                "cette machine."
            )
            + "</div>"
        )
    if not cfg.ids_certain:
        banner += (
            f'<div class="banner warn"><strong>PUID/PGID {cfg.puid}:{cfg.pgid}</strong> — '
            f"{html.escape(t(cfg.ids_source))}. "
            + t("Cette valeur decide de qui possede vos medias.")
            + "</div>"
        )

    if not live:
        banner += (
            '<div class="banner info">'
            + t(
                "Cette page est un <b>fichier fige</b> : elle ne montre ni "
                "l'etat des services, ni les mises a jour disponibles, et ses "
                "boutons n'existent pas ici.<br>Pour tout cela, ouvrez "
                "<code>{lanceur}</code>, depose a cote de cette page.",
                lanceur=LAUNCHER_NAME,
            )
            + "</div>"
        )

    # Importe ici et non en tete : `orchestrator` importe `dashboard`.
    from .orchestrator import prochaine_etape

    page = _TEMPLATE.format(
        generated=generated,
        count=count,
        cards=_cards(cfg, host, live=live),
        paths=_paths(cfg),
        ajouts=_ajouts(cfg) if live else "",
        outils=_outils() if live else "",
        banner=banner,
        data_root=html.escape(cfg.data_root),
        # Le conseil de fin depend de ce qui est REELLEMENT installe : citer
        # Prowlarr a qui n'a installe que Silo envoyait chercher un ecran
        # inexistant.
        prochaine_etape=html.escape(" ".join(prochaine_etape(cfg))),
        version=__version__,
        live_script=_LIVE_SCRIPT if live else "",
        title=t("Administration") if live else t("Acces"),
        # Le bouton « copier » change de libelle une seconde apres le clic.
        copie=t("copie"),
        langue=i18n.langue(),
        titre_page=t("Votre stack media"),
        sous_titre=t(
            "{nombre} services installes et cables le {date}.",
            nombre=count,
            date=generated,
        ),
        titre_services=t("Services"),
        titre_dossiers=t("Dossiers"),
        colonne_contenu=t("Contenu"),
        colonne_hote=t("Sur cette machine"),
        colonne_conteneur=t("Vu par les conteneurs"),
        note_liens=t(
            "Les liens « ouvrir » ne fonctionnent que si ce navigateur tourne "
            "sur la machine d'installation. Depuis un autre appareil, utilisez "
            "le chemin copiable, ou passez par un partage reseau."
        ),
        note_secrets=t(
            "Cette page contient vos mots de passe et vos cles API. Elle est "
            "en lecture seule pour vous (<code>chmod 600</code>) et exclue du "
            "depot git. Ne la partagez pas."
        ),
        note_generee=t(
            "Genere par plugarr {version} — donnees dans <code>{racine}</code>.",
            version=__version__,
            racine=html.escape(cfg.data_root),
        ),
    )

    if live:
        from .console_ui import enhance
        return enhance(page)
    return page


def write(cfg: StackConfig, target_dir: Path, *, failed: int = 0) -> Path:
    """Ecrit la page. Renvoie son chemin."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / FILENAME
    path.write_text(render(cfg, failed=failed), encoding="utf-8")
    try:
        # Meme regime que le .env : la page contient les memes secrets.
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass
    return path


def open_in_browser(path: Path) -> bool:
    """Ouvre la page. Renvoie False sans bruit sur une machine sans navigateur,
    ce qui est le cas normal d'un NAS."""
    import webbrowser

    try:
        return webbrowser.open(path.resolve().as_uri())
    except Exception:  # noqa: BLE001 - un echec ici ne doit jamais interrompre
        return False


_TEMPLATE = """<!doctype html>
<html lang="{langue}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — stack media</title>
<style>
  :root {{
    --bg: #f6f7f9; --panel: #fff; --text: #16181d; --muted: #6b7280;
    --line: #e4e7ec; --warn-bg: #fff7ed; --warn-line: #f59e0b;
    --info-bg: #eff6ff; --info-line: #4c8dff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #101216; --panel: #181b21; --text: #e8eaed; --muted: #9aa3af;
      --line: #272b33; --warn-bg: #2a2015; --info-bg: #15202f;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem 1.5rem 4rem; background: var(--bg); color: var(--text);
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  header h1 {{ margin: 0 0 .3rem; font-size: 1.6rem; letter-spacing: -.02em; }}
  header p {{ margin: 0 0 1.6rem; color: var(--muted); }}
  .banner {{
    padding: .8rem 1rem; border-radius: 8px; margin-bottom: .7rem;
    background: var(--info-bg); border-left: 4px solid var(--info-line);
  }}
  .banner.warn {{ background: var(--warn-bg); border-left-color: var(--warn-line); }}
  h2 {{ font-size: 1rem; text-transform: uppercase; letter-spacing: .06em;
       color: var(--muted); margin: 2.2rem 0 .9rem; }}
  .grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); }}
  .card {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 1rem 1.1rem; border-top: 3px solid var(--accent);
  }}
  .title {{ display: flex; gap: .75rem; align-items: center; text-decoration: none; color: inherit; }}
  .title:hover .url {{ text-decoration: underline; }}
  .title.headless:hover .url {{ text-decoration: none; }}
  .title.headless .url {{ color: var(--muted); font-style: italic; }}
  .badge {{
    width: 38px; height: 38px; flex: none; border-radius: 9px; background: var(--accent);
    color: #fff; display: grid; place-items: center; font-weight: 700; font-size: 1.1rem;
  }}
  .title strong {{ display: block; font-size: 1.05rem; }}
  .url {{ color: var(--accent); font-size: .87rem; font-family: ui-monospace, monospace; }}
  .note {{ color: var(--muted); font-size: .85rem; margin: .7rem 0 .5rem; }}
  .creds {{ border-top: 1px solid var(--line); padding-top: .6rem; }}
  .row {{ display: flex; justify-content: space-between; align-items: center;
          gap: .5rem; padding: .22rem 0; font-size: .87rem; }}
  .k {{ color: var(--muted); }}
  .v {{ display: flex; align-items: center; gap: .4rem; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .dim {{ color: var(--muted); }}
  .none {{ color: var(--muted); }}
  .secret {{ cursor: pointer; font-family: ui-monospace, monospace; }}
  .secret .dots {{ letter-spacing: .1em; }}
  button.copy {{
    font: inherit; font-size: .75rem; padding: .1rem .45rem; cursor: pointer;
    background: transparent; color: var(--muted);
    border: 1px solid var(--line); border-radius: 5px;
  }}
  button.copy:hover {{ color: var(--text); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--panel);
           border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: .6rem .8rem; border-bottom: 1px solid var(--line);
            font-size: .88rem; }}
  th {{ color: var(--muted); font-weight: 600; font-size: .78rem;
        text-transform: uppercase; letter-spacing: .05em; }}
  tr:last-child td {{ border-bottom: none; }}
  td a {{ color: var(--info-line); }}
  footer {{ margin-top: 2.5rem; color: var(--muted); font-size: .85rem;
            border-top: 1px solid var(--line); padding-top: 1.2rem; }}
  code {{ font-family: ui-monospace, monospace; background: var(--bg);
          padding: .1rem .35rem; border-radius: 4px; }}
  .state {{ display: flex; align-items: center; gap: .45rem; flex-wrap: wrap;
            margin: .6rem 0 .2rem; font-size: .84rem; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; background: #9ca3af; flex: none; }}
  .dot.up {{ background: #22c55e; }}
  .dot.down {{ background: #ef4444; }}
  .dot.busy {{ background: #f59e0b; }}
  .state .label {{ color: var(--muted); }}
  .state .actions {{ margin-left: auto; display: flex; gap: .3rem; }}
  button.act {{
    font: inherit; font-size: .75rem; padding: .15rem .5rem; cursor: pointer;
    background: transparent; color: var(--muted);
    border: 1px solid var(--line); border-radius: 5px;
  }}
  button.act:hover:not(:disabled) {{ color: var(--text); border-color: var(--accent); }}
  button.act.danger:hover:not(:disabled) {{ color: #ef4444; border-color: #ef4444; }}
  button.act:disabled {{ opacity: .4; cursor: not-allowed; }}
  button.rotate {{
    margin-left: .5rem; font-size: .78rem; padding: .1rem .5rem; cursor: pointer;
    border: 1px solid var(--line); border-radius: 5px; background: none; color: var(--muted);
  }}
  button.rotate:hover:not(:disabled) {{ color: var(--text); border-color: var(--accent); }}
  button.rotate:disabled {{ opacity: .5; cursor: progress; }}
  .card.add {{ opacity: .85; border-style: dashed; }}
  .card.add:hover {{ opacity: 1; }}
  button.install {{
    font-size: .82rem; padding: .3rem .8rem; cursor: pointer; border-radius: 6px;
    border: 1px solid var(--accent); background: none; color: var(--accent);
  }}
  button.install:hover:not(:disabled) {{ background: var(--accent); color: #fff; }}
  button.install:disabled {{ opacity: .5; cursor: progress; }}
  .echec {{ color: #ef4444; font-size: .8rem; margin-right: .4rem; }}
  .upd {{ display: inline-flex; align-items: center; gap: .35rem; }}
  .upd .tag {{
    font-size: .7rem; padding: .05rem .4rem; border-radius: 999px;
    background: var(--warn-bg); color: var(--warn-line);
    border: 1px solid var(--warn-line); font-weight: 600;
  }}
  button.upgrade {{
    font: inherit; font-size: .75rem; padding: .15rem .5rem; cursor: pointer;
    background: var(--warn-line); color: #1b1200; border: none; border-radius: 5px;
    font-weight: 600;
  }}
  button.upgrade:disabled {{ opacity: .5; cursor: not-allowed; }}
  .outils {{ display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-top: .75rem; }}
  button.outil {{
    font: inherit; padding: .35rem .8rem; border-radius: 6px; cursor: pointer;
    border: 1px solid var(--line); background: var(--panel); color: var(--text);
  }}
  button.outil:disabled {{ opacity: .5; cursor: progress; }}
  .outil-etat {{ font-size: .85rem; color: var(--muted); }}
  pre.rapport {{
    margin-top: .75rem; padding: .75rem 1rem; border: 1px solid var(--line);
    border-radius: 8px; background: var(--panel); overflow-x: auto;
    font-size: .85rem; line-height: 1.5; white-space: pre-wrap;
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{titre_page}</h1>
    <p>{sous_titre}</p>
    {banner}
    {outils}
  </header>

  <h2>{titre_services}</h2>
  <div class="grid">
{cards}
  </div>

{ajouts}
  <h2>{titre_dossiers}</h2>
  <table>
    <thead><tr><th>{colonne_contenu}</th><th>{colonne_hote}</th><th>{colonne_conteneur}</th><th></th></tr></thead>
    <tbody>
{paths}
    </tbody>
  </table>
  <p class="note">{note_liens}</p>

  <footer>
    <p><strong>{prochaine_etape}</strong></p>
    <p>{note_secrets}</p>
    <p>{note_generee}</p>
  </footer>
</div>
<script>
  document.querySelectorAll('.secret').forEach(function (el) {{
    el.addEventListener('click', function () {{
      var dots = el.querySelector('.dots');
      if (el.dataset.shown === '1') {{
        dots.textContent = '\\u2022'.repeat(8);
        el.dataset.shown = '0';
      }} else {{
        dots.textContent = el.dataset.value;
        el.dataset.shown = '1';
      }}
    }});
  }});
  document.querySelectorAll('button.copy').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      navigator.clipboard.writeText(btn.dataset.value).then(function () {{
        var before = btn.textContent;
        btn.textContent = '{copie}';
        setTimeout(function () {{ btn.textContent = before; }}, 1200);
      }});
    }});
  }});
</script>
{live_script}</body>
</html>
"""

#: Barre d'outils de la console. Deux actions demandees a l'usage : lancer le
#: diagnostic, et forcer la recherche de mises a jour. Celle-ci tournait deja,
#: mais seule et en silence — toutes les quinze minutes, sans qu'on puisse la
#: declencher ni savoir quand elle avait eu lieu.
_OUTILS = """<div class="outils">
      <button class="outil" id="btn-doctor">{diagnostic}</button>
      <button class="outil" id="btn-maj">{maj}</button>
      <button class="outil" id="btn-sauvegarde">{sauvegarde}</button>
      <span class="outil-etat" id="outil-etat"></span>
    </div>
    <pre class="rapport" id="rapport-doctor" hidden></pre>"""


def _commentaire_lanceur(marque: str, fin: str) -> str:
    """En-tete du script lanceur, dans la langue de l'installation.

    Les deux variantes ne different que par leur marque de commentaire et leur
    fin de ligne : Windows veut `rem` et CRLF, le reste `#` et LF.
    """
    return "".join(
        f"{marque} {ligne}{fin}"
        for ligne in t(
            "Genere par plugarr. Ouvre la page d'administration : etat des|"
            "services, demarrage, arret, mises a jour."
        ).split("|")
    )


def _outils() -> str:
    """Barre d'outils formee A L'AFFICHAGE.

    `str.format` ne recurse pas : passee telle quelle au gabarit, cette chaine
    aurait affiche ses champs en clair sur la page. Et la former a l'import
    figerait ses libelles dans la langue chargee a ce moment-la, avant meme
    que l'utilisateur ait choisi la sienne.
    """
    return _OUTILS.format(
        diagnostic=t("diagnostic"),
        maj=t("chercher les mises a jour"),
        sauvegarde=t("sauvegarder la configuration"),
    )


_LIVE_SCRIPT = """<script>
  // Sert uniquement quand la page vient de `plugarr serve` : c'est ce serveur
  // qui expose /api/status et /api/action. Le jeton voyage en cookie HttpOnly,
  // pose lors du chargement de la page.
  var LIBELLES = {running: 'en marche', exited: 'arrete', created: 'cree',
                  paused: 'en pause', absent: 'conteneur absent', unknown: 'etat inconnu'};

  function peindre(services) {
    services.forEach(function (s) {
      var bloc = document.querySelector('.state[data-service="' + s.id + '"]');
      if (!bloc) return;
      var dot = bloc.querySelector('.dot');
      dot.className = 'dot ' + (s.up ? 'up' : 'down');
      dot.title = s.status;
      bloc.querySelector('.label').textContent =
        (s.intentional_stop && !s.up ? 'arret volontaire' : (LIBELLES[s.state] || s.state))
        + (s.status ? ' — ' + s.status : '');
      bloc.querySelectorAll('button.act').forEach(function (b) {
        b.disabled = (b.dataset.action === 'start') ? s.up : !s.up;
      });
    });
  }

  function rafraichir() {
    fetch('/api/status', {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (d) { peindre(d.services); })
      .catch(function () {});
  }

  // Renouvellement d'un mot de passe. L'operation dure : elle change le mot de
  // passe DANS le service, puis rejoue tout le cablage pour que les *arr et
  // Prowlarr apprennent le nouveau. Sans ce recablage, six liaisons casseraient
  // en silence et leur bouton Test echouerait sans rien expliquer.
  document.querySelectorAll('button.rotate').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var cellule = btn.closest('[data-secret]');
      var quoi = btn.dataset.what;
      var nom = (quoi === 'api_key') ? 'la cle API' : 'le mot de passe';
      // Une cle API redemarre le service : le dire, c'est eviter que quelqu'un
      // se demande pourquoi sa serie s'est arretee de telecharger.
      var suite = (quoi === 'api_key')
        ? 'Le service va REDEMARRER, puis toutes les liaisons seront recablees.'
        : 'Le nouveau sera applique puis toutes les liaisons seront recablees.';
      if (!window.confirm(
            'Renouveler ' + nom + ' de ce service ?\\n\\n' + suite + ' '
            + 'Toute application exterieure utilisant l\\'ancien devra etre mise a jour.')) {
        return;
      }
      var avant = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'en cours…';
      fetch('/api/rotate', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({service: btn.dataset.service, what: quoi})
      }).then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          btn.textContent = avant;
          if (!d.ok) {
            btn.insertAdjacentHTML('beforebegin',
              '<span class="echec"></span>');
            cellule.querySelector('.echec').textContent = d.message || d.error;
            return;
          }
          // Le nouveau secret remplace l'ancien sur place, deja devoile : c'est
          // le seul moment ou l'utilisateur peut le noter.
          var secret = cellule.querySelector('.secret');
          secret.dataset.value = d.secret;
          secret.textContent = d.secret;
          secret.classList.add('devoile');
          var copie = cellule.querySelector('button.copy');
          if (copie) copie.dataset.value = d.secret;
        })
        .catch(function (e) {
          btn.disabled = false;
          btn.textContent = avant;
        });
    });
  });

  // Ajout d'un service absent de l'installation. L'operation est longue : elle
  // telecharge une image, demarre le conteneur, puis rejoue tout le cablage —
  // c'est la seule facon de relier le nouveau venu aux anciens DANS LES DEUX
  // SENS. Un client de telechargement ajoute doit apparaitre dans les quatre
  // *arr, et un *arr ajoute doit apparaitre dans Prowlarr et dans autobrr.
  document.querySelectorAll('button.install').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var carte = btn.closest('.card');
      if (!window.confirm(
            'Installer ce service et le cabler ?\\n\\n'
            + 'Son image sera telechargee, ce qui peut prendre plusieurs minutes. '
            + 'Aucun service en marche n\\'est arrete, et aucun mot de passe existant '
            + 'n\\'est touche.')) {
        return;
      }
      btn.disabled = true;
      btn.textContent = 'installation…';
      fetch('/api/add', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({service: btn.dataset.service})
      }).then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            btn.disabled = false;
            btn.textContent = 'installer et cabler';
            carte.insertAdjacentHTML('beforeend', '<p class="echec"></p>');
            carte.querySelector('.echec').textContent = d.message || d.error;
            return;
          }
          // La carte du nouveau service doit apparaitre avec son adresse et ses
          // identifiants : seul un rechargement les connait.
          btn.textContent = 'installe, rechargement…';
          window.location.reload();
        })
        .catch(function () {
          btn.disabled = false;
          btn.textContent = 'installer et cabler';
        });
    });
  });

  document.querySelectorAll('button.act').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var bloc = btn.closest('.state');
      bloc.querySelector('.dot').className = 'dot busy';
      bloc.querySelector('.label').textContent = 'en cours…';
      bloc.querySelectorAll('button.act').forEach(function (b) { b.disabled = true; });
      fetch('/api/action', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({service: btn.dataset.service, action: btn.dataset.action})
      }).then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { bloc.querySelector('.label').textContent = 'echec : ' + (d.message || d.error); }
          setTimeout(rafraichir, 900);
        })
        .catch(function () { bloc.querySelector('.label').textContent = 'serveur injoignable'; });
    });
  });

  function peindreMaj(services) {
    services.forEach(function (s) {
      var zone = document.querySelector('.upd[data-service="' + s.id + '"]');
      if (!zone) return;
      if (!s.available) { zone.hidden = true; zone.innerHTML = ''; return; }
      var libelle = s.latest
        ? 'v' + s.latest.replace(/^v/, '') + ' disponible'
        : 'image reconstruite';
      var titre = s.latest
        ? 'Version ' + s.current + ' installee, ' + s.latest + ' disponible'
        : 'Meme version, image republiee en amont (correctifs de securite)';
      zone.hidden = false;
      zone.innerHTML =
        '<span class="tag" title="' + titre + '">' + libelle + '</span>' +
        '<button class="upgrade">mettre a jour</button>';
      zone.querySelector('button').addEventListener('click', function () {
        lancerMaj(s, zone);
      });
    });
  }

  function lancerMaj(s, zone) {
    var quoi = s.latest ? ('passer de ' + s.current + ' a ' + s.latest) : 'retirer la meme version';
    var question = s.name + ' : ' + quoi + ' ?'
      + '\\n\\nLe conteneur sera recree. Les autres services ne bougent pas.';
    if (!confirm(question)) return;
    zone.innerHTML = '<span class="tag">mise a jour…</span>';
    fetch('/api/update', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({service: s.id, target: s.latest || null})
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        zone.innerHTML = '<span class="tag">' + (d.ok ? 'fait : ' + d.message : 'echec') + '</span>';
        if (!d.ok) { alert(s.name + ' : ' + (d.message || d.error)); }
        setTimeout(function () { rafraichir(); verifierMaj(); }, 1500);
      })
      .catch(function () { zone.innerHTML = '<span class="tag">serveur injoignable</span>'; });
  }

  function verifierMaj() {
    fetch('/api/updates', {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (d) { peindreMaj(d.services); })
      .catch(function () {});
  }

  rafraichir();
  setInterval(rafraichir, 5000);
  // Le controle interroge les registres : lent, et sans urgence.
  verifierMaj();
  setInterval(verifierMaj, 900000);

  // -- barre d'outils ------------------------------------------------------

  var etat = document.getElementById('outil-etat');

  function heure() {
    return new Date().toLocaleTimeString();
  }

  var btnMaj = document.getElementById('btn-maj');
  if (btnMaj) {
    btnMaj.addEventListener('click', function () {
      btnMaj.disabled = true;
      etat.textContent = 'interrogation des registres…';
      // La verification tournait deja toutes les 15 minutes, en silence. Ce
      // bouton ne l'ajoute pas : il la rend declenchable et DATEE.
      fetch('/api/updates', {credentials: 'same-origin'})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var liste = d.services || [];
          peindreMaj(liste);
          var n = liste.filter(function (s) { return s.available; }).length;
          var soucis = liste.filter(function (s) { return (s.problems || []).length; }).length;
          // PlugArr lui-meme. Le bouton ne regardait que les images des
          // services : on pouvait tout avoir a jour sauf l'outil qui le dit.
          var moi = d.plugarr || {};
          var mien = moi.available
            ? 'PlugArr ' + moi.latest + ' disponible (vous avez la ' + moi.current + '). '
            : '';
          etat.textContent = mien
            + (n ? n + ' mise(s) a jour disponible(s)' : 'tout est a jour')
            + (soucis ? ', ' + soucis + ' service(s) non verifiable(s)' : '')
            + ' — ' + heure();
          if (moi.available && moi.url) {
            etat.innerHTML = etat.textContent.replace(
              'PlugArr ' + moi.latest,
              '<a href="' + moi.url + '" target="_blank" rel="noopener">PlugArr '
                + moi.latest + '</a>'
            );
          }
        })
        .catch(function () { etat.textContent = 'serveur injoignable'; })
        .then(function () { btnMaj.disabled = false; });
    });
  }

  var btnSauv = document.getElementById('btn-sauvegarde');
  if (btnSauv) {
    btnSauv.addEventListener('click', function () {
      if (!confirm('Sauvegarder la configuration complete ?'
          + '\\n\\nLes conteneurs seront ARRETES le temps de la copie, puis redemarres. '
          + 'Une base copiee a chaud est corrompue. Vos medias ne sont pas touches.')) return;
      btnSauv.disabled = true;
      etat.textContent = 'conteneurs arretes, copie en cours…';
      fetch('/api/backup', {method: 'POST', credentials: 'same-origin'})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          etat.textContent = d.ok
            ? d.fichiers + ' fichiers, ' + d.mega + ' Mo — ' + d.archive
            : 'echec : ' + (d.error || 'inconnu');
          if (d.ok) { rafraichir(); }
        })
        .catch(function () { etat.textContent = 'serveur injoignable'; })
        .then(function () { btnSauv.disabled = false; });
    });
  }

  var btnDoc = document.getElementById('btn-doctor');
  var rapport = document.getElementById('rapport-doctor');
  if (btnDoc) {
    btnDoc.addEventListener('click', function () {
      if (!rapport.hidden && rapport.dataset.rempli === '1') {
        rapport.hidden = true;
        rapport.dataset.rempli = '0';
        etat.textContent = '';
        return;
      }
      btnDoc.disabled = true;
      etat.textContent = 'diagnostic en cours…';
      fetch('/api/doctor', {credentials: 'same-origin'})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var lignes = (d.checks || []).map(function (c) {
            // Trois marques et non deux : un port entrant desynchronise coute
            // du partage, pas de l'exposition. Le ranger sous ECHEC a cote d'un
            // tunnel tombe ferait craindre une fuite la ou il n'y en a aucune.
            var marque = c.ok ? '  OK    ' : (c.partage ? '  PORT  ' : '  ECHEC ');
            return marque + c.name + ' : ' + c.detail;
          });
          rapport.textContent = lignes.join('\\n') || 'aucun controle';
          rapport.hidden = false;
          rapport.dataset.rempli = '1';
          var resume;
          if (d.failed) {
            resume = d.failed + ' controle(s) en echec';
            if (d.partage) resume += ', ' + d.partage + ' port(s) entrant(s) a revoir';
          } else if (d.partage) {
            resume = 'protection en ordre, ' + d.partage + ' port(s) entrant(s) a revoir';
          } else {
            resume = 'tout est en ordre';
          }
          etat.textContent = resume + ' — ' + heure();
        })
        .catch(function () { etat.textContent = 'serveur injoignable'; })
        .then(function () { btnDoc.disabled = false; });
    });
  }
</script>
"""


#: Nom du lanceur ecrit a cote des artefacts, selon la plateforme.
LAUNCHER_NAME = "administration.cmd" if sys.platform == "win32" else "administration.sh"


def admin_command(project_dir: Path) -> str:
    """Commande capable de relancer la page d'administration.

    Un utilisateur qui a double-clique un executable n'a pas `plugarr` dans son
    PATH : lui dire « lancez plugarr serve » ne l'avance a rien. On note donc le
    chemin reellement utilise pour cette installation.
    """
    cible = f'"{Path(project_dir).resolve()}"'
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" serve --project-dir {cible}'
    return f'"{Path(sys.executable).resolve()}" -m plugarr serve --project-dir {cible}'


def write_admin_launcher(project_dir: Path) -> Path:
    """Ecrit un lanceur double-cliquable pour la page d'administration.

    C'est elle qui porte l'etat des services, les boutons demarrer / arreter /
    redemarrer et les mises a jour disponibles. La page d'acces, elle, est un
    fichier fige : signale a l'usage, personne ne devine qu'il faut lancer une
    commande pour obtenir le reste.
    """
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    cible = project_dir / LAUNCHER_NAME
    commande = admin_command(project_dir)

    if sys.platform == "win32":
        contenu = (
            "@echo off\r\n"
            + _commentaire_lanceur("rem", "\r\n")
            +             "title plugarr - administration\r\n"
            f"{commande}\r\n"
            "pause\r\n"
        )
        cible.write_text(contenu, encoding="utf-8", newline="")
    else:
        contenu = (
            "#!/bin/sh\n"
            + _commentaire_lanceur("#", "\n")
            +             f"exec {commande}\n"
        )
        cible.write_text(contenu, encoding="utf-8")
        cible.chmod(0o755)
    return cible
