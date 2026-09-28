"""Checks shared by the CLI and the administration console.

Everything here reads, except the section at the end: the two bounded repairs
that `doctor --repair` may apply after an explicit confirmation, each followed
by a re-read of the condition it fixed.

`build_findings` turns raw checks into consequence-oriented findings. Each one
states what was observed, what it costs the user, the evidence behind it and a
proposed fix. Evidence never carries a secret: known credentials and URL
parameters that look like keys are masked before anything leaves this module.
"""

from __future__ import annotations

from os import stat_result
from pathlib import Path

import yaml

from . import catalog, compose, connections, gluetun_auth, journal, vpncheck
from .i18n import t
from .models import StackConfig
from .runner import Check


def connection_checks(cfg: StackConfig) -> list[dict]:
    """Test actual *arr links without replaying their wiring."""
    checks: list[dict] = []
    for edge in connections.entries(cfg):
        outcome = connections.test(cfg, edge)
        ok = outcome["state"] == "verifiee"
        source, target = edge["source"], edge["target"]
        checks.append(
            {
                "name": t("Liaison {source} -> {target}", source=source, target=target),
                "ok": ok,
                "detail": outcome["detail"],
                "blocking": False,
                "partage": False,
                "edge_id": edge["id"],
                "source": source,
                "target": target,
                "kind": edge["kind"],
                "next_step": (
                    t("Aucune action necessaire.")
                    if ok
                    else (
                        t("Examinez la liaison dans {source}. Apres verification de l'adresse et des identifiants, confirmez la reapplication de {liaison}.", source=source, liaison=edge["id"])
                        if not cfg.services[source].adopted
                        else t("Service adopte : corrigez la liaison {liaison} dans {source}.", liaison=edge["id"], source=source)
                    )
                ),
            }
        )
    return checks


def compose_drift(cfg: StackConfig, project_dir: Path) -> dict | None:
    """Compare the effective Compose structure with PlugArr's saved model.

    An adopted stack has no PlugArr-owned Compose file. Never print the diff:
    environment values and service settings can contain credentials. The
    evidence names what differs (services, sections, .env variable names),
    never a value.
    """
    if cfg.services and all(inst.adopted for inst in cfg.services.values()):
        return None
    path = project_dir / "docker-compose.yml"
    env_path = project_dir / ".env"
    if not (project_dir / "stack.yml").is_file() and not path.is_file():
        return None
    evidence: list[str] = []
    try:
        actual = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected = yaml.safe_load(compose.render_compose(cfg))
        expected_env = _env_entries(compose.render_env(cfg, project_dir))
        actual_env = _env_entries(env_path.read_text(encoding="utf-8"))
        ok = actual == expected and actual_env == expected_env
        detail = (
            t("Les fichiers Compose et .env correspondent au modele PlugArr.")
            if ok
            else t("Les fichiers Compose ou .env divergent de la configuration PlugArr.")
        )
        if not ok:
            evidence = _drift_evidence(actual, expected, actual_env, expected_env)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        ok = False
        detail = t("Comparaison impossible ({erreur}).", erreur=type(exc).__name__)
    return {
        "name": t("Derive des fichiers Docker"),
        "ok": ok,
        "detail": detail,
        "blocking": False,
        "partage": False,
        "evidence": evidence,
        "next_step": (
            t("Aucune action necessaire.")
            if ok
            else t("Sauvegardez le fichier, comparez-le a stack.yml, puis validez toute regeneration.")
        ),
    }


def _drift_evidence(actual, expected, actual_env: dict, expected_env: dict) -> list[str]:
    """Names of what differs, never the values: both files carry secrets."""
    evidence: list[str] = []
    if not isinstance(actual, dict):
        return [t("docker-compose.yml ne contient pas un document Compose lisible.")]
    services = actual.get("services") if isinstance(actual.get("services"), dict) else {}
    attendus = expected.get("services", {})
    manquants = sorted(set(attendus) - set(services))
    en_trop = sorted(set(services) - set(attendus))
    modifies = sorted(s for s in set(attendus) & set(services) if attendus[s] != services[s])
    if modifies:
        evidence.append(t("Services dont le bloc Compose differe : {services}", services=", ".join(modifies)))
    if manquants:
        evidence.append(t("Services attendus absents du fichier : {services}", services=", ".join(manquants)))
    if en_trop:
        evidence.append(t("Services presents en plus dans le fichier : {services}", services=", ".join(en_trop)))
    sections = sorted(
        k for k in set(actual) | set(expected) if k != "services" and actual.get(k) != expected.get(k)
    )
    if sections:
        evidence.append(t("Autres sections differentes : {sections}", sections=", ".join(sections)))
    variables = sorted(
        k for k in set(actual_env) | set(expected_env) if actual_env.get(k) != expected_env.get(k)
    )
    if variables:
        evidence.append(
            t(
                "Variables .env differentes (noms seulement) : {variables}",
                variables=", ".join(variables),
            )
        )
    return evidence


def _env_entries(text: str) -> dict[str, str]:
    """Ignore comment language while comparing secret-bearing values in memory."""
    return {
        key: value
        for line in text.splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
        for key, _, value in (line.partition("="),)
    }


def existing_hardlinks(data_root: str | Path, *, max_files: int = 20000) -> dict:
    """Read-only, bounded evidence of existing torrent-to-media hardlinks.

    A lack of matching inodes is inconclusive: media may come from Usenet, or
    matching files may be beyond the scan limit. Never claim all links are OK.
    """
    if max_files < 2:
        raise ValueError("max_files must be at least 2")
    root = Path(data_root)
    sources = root / "torrents"
    targets = root / "media"
    if not sources.is_dir() or not targets.is_dir():
        return {"checked": 0, "matched": 0, "partial": False, "available": False}

    checked = 0
    partial = False
    source_inodes: set[tuple[int, int]] = set()
    matched = 0
    for directory, is_source in ((sources, True), (targets, False)):
        directory_count = 0
        try:
            paths = directory.rglob("*")
            for path in paths:
                if directory_count >= max_files // 2:
                    partial = True
                    break
                try:
                    if not path.is_file() or path.is_symlink():
                        continue
                    info: stat_result = path.stat()
                except OSError:
                    continue
                checked += 1
                directory_count += 1
                if info.st_nlink < 2:
                    continue
                inode = (info.st_dev, info.st_ino)
                if is_source:
                    source_inodes.add(inode)
                elif inode in source_inodes:
                    matched += 1
        except OSError:
            partial = True
    return {"checked": checked, "matched": matched, "partial": partial, "available": True}


# ------------------------------------------------------------------ secrets


def _known_secrets(cfg: StackConfig) -> list[str]:
    """Every credential PlugArr holds for this stack, longest first.

    Same threshold as the log: shorter values would mask ordinary words and
    make the report unreadable without protecting anything real.
    """
    valeurs = {gluetun_auth.cle(cfg), cfg.admin_password_hash}
    for inst in cfg.services.values():
        valeurs |= {inst.api_key or "", inst.password or "", inst.secret_key}
    valeurs |= {cfg.vpn.wireguard_private_key, cfg.vpn.openvpn_password}
    return sorted((v for v in valeurs if v and len(v) >= journal.MIN_SECRET), key=len, reverse=True)


def redact(text: str, secrets: list[str]) -> str:
    """Mask known secrets, then keys carried by URL parameters."""
    for secret in secrets:
        text = text.replace(secret, "<masque>")
    return journal.caviarder(text)


def redact_checks(checks: list[dict], cfg: StackConfig) -> list[dict]:
    """Mask secrets in every text field of raw checks, in place."""
    secrets = _known_secrets(cfg)
    for check in checks:
        for key in ("detail", "next_step"):
            if isinstance(check.get(key), str):
                check[key] = redact(check[key], secrets)
        if isinstance(check.get("evidence"), list):
            check["evidence"] = [redact(e, secrets) for e in check["evidence"]]
    return checks


# ----------------------------------------------------------------- findings

#: Reading order: exposure first, then what stops working, then what degrades.
SEVERITIES = ("critical", "error", "warning", "info")
KINDS = ("vpn", "storage", "service", "link", "hardlink", "drift", "port")

#: Identifier of the incoming-port repair; `link:<edge id>` names the others.
PORT_SYNC = "port-sync"


def labels() -> dict[str, str]:
    """Headings for a rendered finding, in the language of the stack."""
    return {
        "finding": t("Constat"),
        "consequence": t("Consequence pour vous"),
        "evidence": t("Preuves"),
        "fix": t("Correction proposee"),
        "repair": t("Reparation possible"),
        "critical": t("CRITIQUE"),
        "error": t("ECHEC"),
        "warning": t("ATTENTION"),
        "info": t("A SAVOIR"),
    }


def _finding(
    kind: str,
    subject: str,
    severity: str,
    title: str,
    finding: str,
    consequence: str,
    evidence: list[str],
    fix: str,
    repair: dict | None = None,
) -> dict:
    return {
        "kind": kind,
        "subject": subject,
        "severity": severity,
        "title": title,
        "finding": finding,
        "consequence": consequence,
        "evidence": [e for e in evidence if e],
        "fix": fix,
        "repair": repair,
    }


def _preuve(controle: str, detail: str) -> str:
    """Un controle brut, cite tel quel : c'est lui la preuve."""
    return t("{controle} : {detail}", controle=controle, detail=detail)


def _nom(sid: str) -> str:
    if sid == "gluetun":
        return "Gluetun"
    if sid == "docker":
        return "Docker"
    try:
        return catalog.get(sid).display_name
    except KeyError:
        return sid


def _service_consequence(sid: str) -> str:
    service = _nom(sid)
    if sid == "docker":
        return t("Aucun service de la pile ne peut etre demarre, controle ni joint tant que Docker ne repond pas.")
    if sid == "gluetun":
        return t("Les clients proteges par le VPN n'ont plus aucun acces reseau : leurs telechargements sont a l'arret.")
    if sid == "prowlarr":
        return t("Prowlarr ne fournit plus d'indexeurs : Sonarr, Radarr et Lidarr ne trouvent plus de nouvelles sorties.")
    if sid in catalog.MANAGED_ARRS:
        return t("{service} ne recherche plus et n'importe plus de nouveaux medias : demandes et sorties attendues restent en suspens.", service=service)
    if sid in catalog.DOWNLOAD_CLIENTS:
        return t("{service} ne telecharge plus : les *arr ne peuvent plus lui confier de demandes et les telechargements en cours sont interrompus.", service=service)
    if sid in ("jellyfin", "silo", "audiobookshelf"):
        return t("{service} n'est plus joignable : la mediatheque ne se lit plus depuis vos appareils.", service=service)
    if sid == "seerr":
        return t("Seerr n'accepte plus de demandes : personne ne peut demander de film ni de serie.")
    if sid in ("silo-postgres", "silo-redis"):
        return t("{service} est une dependance de Silo : Silo ne peut pas fonctionner sans elle.", service=service)
    return t("{service} est indisponible : les fonctions qui dependent de lui sont interrompues.", service=service)


def _service_findings(
    services: list[dict], preflight: list[Check], links: list[dict]
) -> tuple[list[dict], set[str]]:
    """One finding per unavailable service, with the links it makes untestable."""
    moteur = {"docker", t("daemon docker"), "docker compose"}
    echecs: dict[str, dict] = {}
    for check in preflight:
        if check.name in moteur and not check.ok and "docker" not in echecs:
            echecs["docker"] = {
                "name": check.name, "detail": check.detail, "probe": "engine",
                "next_step": t("Demarrez Docker, puis relancez le diagnostic."),
            }
    for check in services:
        sid = check.get("service")
        if check["ok"] or not sid or sid in echecs:
            continue
        echecs[sid] = check

    findings: list[dict] = []
    for sid, check in echecs.items():
        service = _nom(sid)
        if check.get("probe") == "api":
            constat = t("Le conteneur de {service} tourne, mais son API ne repond pas.", service=service)
        elif sid == "docker":
            constat = t("Docker ne repond pas a PlugArr.")
        else:
            constat = t("Le conteneur de {service} n'est pas en service.", service=service)
        touchees = sorted(
            link["edge_id"] for link in links
            if not link["ok"] and sid in (link.get("source"), link.get("target"), "docker")
        )
        evidence = [_preuve(check["name"], check["detail"])]
        if touchees:
            evidence.append(
                t(
                    "Liaisons non verifiables tant que {service} est indisponible : {liaisons}",
                    service=service,
                    liaisons=", ".join(touchees),
                )
            )
        findings.append(
            _finding(
                "service", sid, "critical" if sid == "docker" else "error",
                t("{service} indisponible", service=service),
                constat, _service_consequence(sid), evidence,
                check.get("next_step") or t("Consultez les journaux du service, puis relancez le diagnostic."),
            )
        )
    return findings, set(echecs)


def _link_consequence(link: dict) -> str:
    source, cible = _nom(link.get("source", "")), _nom(link.get("target", ""))
    kind = link.get("kind")
    if kind == "downloadclient":
        return t("{source} ne peut plus confier de telechargements a {cible} ni suivre leur progression : les demandes restent sans suite.", source=source, cible=cible)
    if kind == "application":
        return t("{source} ne synchronise plus ses indexeurs vers {cible} : les recherches de {cible} ne trouvent plus de nouvelles sorties.", source=source, cible=cible)
    if kind == "notification":
        return t("{cible} n'est plus prevenu des imports de {source} : les nouveaux medias n'apparaissent qu'au prochain scan de bibliotheque.", source=source, cible=cible)
    return t("La liaison {liaison} ne fonctionne plus.", liaison=link["edge_id"])


def _link_findings(cfg: StackConfig, links: list[dict], indisponibles: set[str]) -> list[dict]:
    """Broken links whose two ends are up: the link itself is the cause."""
    findings = []
    for link in links:
        if link["ok"]:
            continue
        source, cible = link.get("source", ""), link.get("target", "")
        if {source, cible, "docker"} & indisponibles:
            continue
        adopte = source in cfg.services and cfg.services[source].adopted
        repair = None if adopte else {
            "id": f"link:{link['edge_id']}",
            "label": t("Reappliquer uniquement la liaison {liaison}, puis la retester", liaison=link["edge_id"]),
        }
        findings.append(
            _finding(
                "link", link["edge_id"], "error",
                t("Liaison {source} -> {cible} cassee", source=_nom(source), cible=_nom(cible)),
                t("Le test reel de la liaison echoue : {detail}", detail=link["detail"]),
                _link_consequence(link),
                [
                    t("Test lance par l'API de {source}, sans rien reappliquer", source=_nom(source)),
                    t("Liaison attendue par le plan de cablage : {liaison}", liaison=link["edge_id"]),
                ],
                link["next_step"],
                repair,
            )
        )
    return findings


def _storage_findings(cfg: StackConfig, preflight: list[Check]) -> list[dict]:
    """Group data-volume and config-volume symptoms, one finding per volume."""
    par_nom = {c.name: c for c in preflight}
    findings = []

    donnees = [
        par_nom[n] for n in (t("racine des donnees"), t("arborescence des donnees"), t("espace disque"))
        if n in par_nom and not par_nom[n].ok
    ]
    adoptee = bool(cfg.services) and all(inst.adopted for inst in cfg.services.values())
    if adoptee and [c.name for c in donnees] == [t("arborescence des donnees")]:
        # Une pile adoptee garde SON arborescence : sans torrents/ ni media/,
        # ce n'est pas un volume absent, c'est une disposition que PlugArr
        # n'a pas choisie. Seuls les hardlinks restent sans reponse.
        findings.append(
            _finding(
                "hardlink", "data", "info",
                t("Hardlinks non verifiables sur cette pile adoptee"),
                t("torrents/ et media/ ne sont pas sous la racine declaree : l'arborescence de cette pile n'est pas celle de PlugArr."),
                t("PlugArr ne peut pas dire si vos imports sont hardlinkes ; s'ils recopient, l'espace occupe double."),
                [_preuve(c.name, c.detail) for c in donnees],
                t("Verifiez que la racine declaree a l'adoption ({racine}) est bien celle qui contient les telechargements et la mediatheque.", racine=cfg.data_root),
            )
        )
        donnees = []
    if donnees:
        seulement_espace = all(c.name == t("espace disque") for c in donnees)
        findings.append(
            _finding(
                "storage", "data", "warning" if seulement_espace else "critical",
                t("Volume des donnees suspect"),
                t("Il reste peu d'espace libre sur le disque des donnees.")
                if seulement_espace
                else t("Le volume des donnees est absent, incomplet ou monte en lecture seule."),
                t("Quand le disque sera plein, les telechargements s'arreteront et les imports echoueront.")
                if seulement_espace
                else t("Les telechargements et les imports echouent, ou remplissent un autre disque que prevu ; les bibliotheques peuvent paraitre vides."),
                [_preuve(c.name, c.detail) for c in donnees],
                t("Liberez de l'espace ou agrandissez le volume qui porte {racine}.", racine=cfg.data_root)
                if seulement_espace
                else t("Verifiez que le disque ou le partage qui porte {racine} est monte en lecture-ecriture, puis redemarrez la pile.", racine=cfg.data_root),
            )
        )

    configurations = [
        par_nom[n] for n in (t("racine des configurations"), t("configurations *arr"))
        if n in par_nom and not par_nom[n].ok
    ]
    if configurations:
        findings.append(
            _finding(
                "storage", "config", "critical",
                t("Volume des configurations suspect"),
                t("Le dossier des configurations est absent, monte en lecture seule, ou ne contient plus les fichiers des services."),
                t("Au prochain demarrage, les services concernes repartiraient d'une configuration vierge : cles API, liaisons et reglages perdus pour eux."),
                [_preuve(c.name, c.detail) for c in configurations],
                t("Verifiez que {racine} est bien le dossier monte par les conteneurs (disque ou partage monte, chemin inchange) avant tout redemarrage.", racine=cfg.config_root),
            )
        )
    return findings


def _hardlink_findings(cfg: StackConfig, preflight: list[Check], audit: dict | None) -> list[dict]:
    lien = next((c for c in preflight if c.name == "hardlinks /data"), None)
    audit_ligne = (
        t(
            "Echantillon --deep-hardlinks : {nombre} lien(s) confirme(s) sur {examines} fichiers ({portee})",
            nombre=audit["matched"],
            examines=audit["checked"],
            portee=t("echantillon partiel") if audit["partial"] else t("dossiers parcourus entierement"),
        )
        if audit and audit.get("available")
        else ""
    )
    if lien is not None and not lien.ok:
        return [
            _finding(
                "hardlink", "data", "warning",
                t("Imports non hardlinkes"),
                t("Les hardlinks entre torrents/ et media/ ne sont pas assures."),
                t("Chaque import recopie le fichier au lieu de le lier : l'espace occupe double tant que le torrent est partage, et les gros imports durent."),
                [_preuve(lien.name, lien.detail), audit_ligne],
                t("Placez torrents/ et media/ sur le meme systeme de fichiers et montez {racine} d'un seul bloc sur /data dans chaque conteneur. Rien n'est deplace automatiquement.", racine=cfg.data_root),
            )
        ]
    if audit and audit.get("available") and audit["checked"] and not audit["matched"]:
        return [
            _finding(
                "hardlink", "data", "info",
                t("Aucun hardlink existant confirme"),
                t("Aucun fichier de media/ ne partage son inode avec un fichier de torrents/."),
                t("Resultat indetermine : des medias venus d'Usenet, ou hors de l'echantillon, n'ont pas de lien a montrer. Si vos imports torrent recopient, l'espace occupe double."),
                [audit_ligne],
                t("Verifiez l'option des hardlinks dans la gestion des medias de chaque *arr, puis relancez `plugarr doctor --deep-hardlinks` apres un nouvel import."),
            )
        ]
    return []


def _vpn_findings(cfg: StackConfig, vpn: list[Check], project_dir: Path) -> list[dict]:
    findings = []
    gluetun = f"{cfg.project_name}-gluetun"
    for check in vpn:
        if check.name == "VPN" and vpncheck.clients_torrent(cfg):
            findings.append(
                _finding(
                    "vpn", "vpn", "info",
                    t("Clients torrent hors VPN, par choix"),
                    check.detail,
                    t("Votre adresse IP publique est visible des autres pairs pour chaque torrent partage."),
                    [t("stack.yml : aucun VPN active")],
                    t("Si ce choix n'est pas voulu, reinstallez avec un VPN (option --vpn, ou l'ecran VPN de l'assistant)."),
                )
            )
            continue
        if not check.name.startswith("VPN ") or check.ok:
            continue
        sid = check.name[4:]
        service = _nom(sid)
        adopte = sid in cfg.services and cfg.services[sid].adopted
        findings.append(
            _finding(
                "vpn", sid, "critical",
                t("{service} potentiellement hors VPN", service=service),
                t("La protection VPN de {service} n'est pas confirmee.", service=service),
                t("Tant que ce point n'est pas regle, un torrent lance par {service} peut sortir par votre connexion : votre adresse IP publique devient visible des autres pairs et de votre fournisseur d'acces.", service=service),
                [
                    _preuve(check.name, check.detail),
                    t("Attendu : {service} dans la pile reseau du conteneur {gluetun}", service=service, gluetun=gluetun),
                ],
                t("PlugArr ne gere pas ce conteneur : recreez-le vous-meme avec network_mode: container:{gluetun}, puis relancez le diagnostic.", gluetun=gluetun)
                if adopte
                else t("Mettez {service} en pause, verifiez que Gluetun tourne, puis recreez la pile avec `docker compose up -d` dans {dossier} et relancez le diagnostic.", service=service, dossier=project_dir),
            )
        )

    ports = [c for c in vpn if c.name.startswith(vpncheck.PREFIXE_PORT) and not c.ok]
    sans_port = [c for c in ports if c.name == vpncheck.PREFIXE_PORT]
    decales = [c for c in ports if c.name != vpncheck.PREFIXE_PORT]
    consequence = t("Aucune connexion entrante n'arrive : le partage et le ratio baissent. Les telechargements continuent, et la protection VPN n'est pas en cause.")
    if sans_port:
        findings.append(
            _finding(
                "port", "port", "warning",
                t("Aucun port entrant obtenu"),
                t("Le VPN n'a ouvert aucun port entrant."),
                consequence,
                [_preuve(c.name, c.detail) for c in sans_port],
                t("Verifiez que votre offre {fournisseur} autorise la redirection de port, puis redemarrez Gluetun et relancez le diagnostic.", fournisseur=cfg.vpn.provider),
            )
        )
    if decales:
        adopted_client = any(
            cfg.services[sid].adopted for sid in vpncheck.clients_proteges(cfg)
        )
        findings.append(
            _finding(
                "port", "port", "warning",
                t("Port entrant desynchronise"),
                t("Le port ouvert par le VPN n'est pas celui qu'ecoute le client."),
                consequence,
                [_preuve(c.name, c.detail) for c in decales],
                t("Client adopté : synchronisez son port dans votre propre configuration VPN.")
                if adopted_client else t("Rejouer la synchronisation du port Gluetun, puis relire le port ecoute par chaque client."),
                None if adopted_client else {"id": PORT_SYNC, "label": t("Rejouer la synchronisation du port Gluetun")},
            )
        )
    return findings


def _drift_findings(drift: dict | None) -> list[dict]:
    if drift is None or drift["ok"]:
        return []
    return [
        _finding(
            "drift", "compose", "warning",
            t("Derive de configuration"),
            drift["detail"],
            t("Les conteneurs peuvent ne plus correspondre a stack.yml, et la prochaine regeneration par PlugArr (mise a jour, ajout de service) ecrasera les modifications faites a la main dans ces fichiers."),
            list(drift.get("evidence") or []),
            drift["next_step"],
        )
    ]


def build_findings(
    cfg: StackConfig,
    project_dir: Path,
    *,
    preflight: list[Check],
    services: list[dict],
    links: list[dict],
    drift: dict | None,
    vpn: list[Check],
    hardlink_audit: dict | None = None,
) -> list[dict]:
    """Consequence-oriented findings, most severe first. Reads only.

    A root cause hides its symptoms: a stopped Sonarr makes each of its links
    fail too, and listing them as broken links would send the user repairing
    wiring that is fine. They are named in the service finding instead.
    """
    service_findings, indisponibles = _service_findings(services, preflight, links)
    findings = [
        *_vpn_findings(cfg, vpn, project_dir),
        *_storage_findings(cfg, preflight),
        *service_findings,
        *_link_findings(cfg, links, indisponibles),
        *_hardlink_findings(cfg, preflight, hardlink_audit),
        *_drift_findings(drift),
    ]
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), KINDS.index(f["kind"])))
    secrets = _known_secrets(cfg)
    for item in findings:
        for key in ("title", "finding", "consequence", "fix"):
            item[key] = redact(item[key], secrets)
        item["evidence"] = [redact(e, secrets) for e in item["evidence"]]
    return findings


# ------------------------------------------------------------------ repairs


def repairs(findings: list[dict]) -> list[dict]:
    """Distinct repairs offered by the findings, in reading order."""
    vus: set[str] = set()
    offertes = []
    for item in findings:
        repair = item.get("repair")
        if repair and repair["id"] not in vus:
            vus.add(repair["id"])
            offertes.append({**repair, "title": item["title"]})
    return offertes


def apply_repair(cfg: StackConfig, repair_id: str) -> dict:
    """Apply ONE confirmed repair, then re-read the condition it targets.

    Only the two repairs `doctor` has always proposed exist: replaying the
    wiring step of a single *arr link, and replaying Gluetun's own port
    synchronisation. The verdict comes from the re-read, never from the
    write: a repair that "succeeded" but left the link broken is reported as
    still failing.
    """
    if repair_id == PORT_SYNC:
        remise = vpncheck.reparer_port(cfg)
        if remise is None:
            return {
                "id": repair_id, "applied": False, "verified": None,
                "detail": t("Relecture avant correction : aucun ecart de port a corriger, rien n'a ete modifie."),
            }
        return {"id": repair_id, "applied": True, "verified": remise.ok, "detail": remise.detail}

    if repair_id.startswith("link:"):
        edge_id = repair_id.removeprefix("link:")
        edge = next((e for e in connections.entries(cfg) if e["id"] == edge_id), None)
        if edge is None or cfg.services[edge["source"]].adopted:
            return {
                "id": repair_id, "applied": False, "verified": None,
                "detail": t("Reparation refusee : liaison inconnue ou service adopte."),
            }
        try:
            applique = connections.repair(cfg, edge)
        except Exception:  # noqa: BLE001 - un correctif echoue ne doit pas interrompre le diagnostic
            applique = False
        relu = connections.test(cfg, edge)
        return {
            "id": repair_id,
            "applied": applique,
            "verified": relu["state"] == "verifiee",
            "detail": t("Liaison retestee : {etat}", etat=relu["state"]),
        }

    raise ValueError(f"reparation inconnue : {repair_id}")
