"""The diagnostic reports evidence and plans without silently changing a stack."""

from pathlib import Path

import pytest

from plugarr import (
    admin,
    compose,
    connections,
    diagnostics,
    i18n,
    orchestrator,
    runner,
    vpncheck,
)
from plugarr.models import VpnConfig
from plugarr.runner import Check
from plugarr.wiring import StepResult, Wirer, WiringStep


def test_existing_hardlinks_confirms_only_real_shared_inodes(tmp_path):
    from os import link

    torrents = tmp_path / "torrents"
    media = tmp_path / "media"
    torrents.mkdir()
    media.mkdir()
    source = torrents / "movie.mkv"
    source.write_bytes(b"sample")
    link(source, media / "movie.mkv")
    (media / "other.mkv").write_bytes(b"sample")

    result = diagnostics.existing_hardlinks(tmp_path)

    assert result == {"checked": 3, "matched": 1, "partial": False, "available": True}


def test_existing_hardlinks_never_counts_equal_content_as_a_link(tmp_path):
    for directory in ("torrents", "media"):
        folder = tmp_path / directory
        folder.mkdir()
        (folder / "same.mkv").write_bytes(b"same bytes")

    result = diagnostics.existing_hardlinks(tmp_path)

    assert result["matched"] == 0
    assert result["available"]


def test_existing_hardlinks_reports_partial_scan(tmp_path):
    for directory in ("torrents", "media"):
        folder = tmp_path / directory
        folder.mkdir()
        for index in range(3):
            (folder / f"{index}.mkv").write_bytes(b"x")

    result = diagnostics.existing_hardlinks(tmp_path, max_files=2)

    assert result["partial"]
    assert result["checked"] == 2


def _cfg(*services):
    return orchestrator.build_config(
        services=list(services), data_root="/data", config_root="/config"
    )


def test_broken_link_has_a_targeted_repair_plan(monkeypatch):
    cfg = _cfg("sonarr", "qbittorrent")
    edge = {
        "id": "sonarr/downloadclient/qbittorrent",
        "source": "sonarr",
        "target": "qbittorrent",
        "kind": "downloadclient",
    }
    monkeypatch.setattr(diagnostics.connections, "entries", lambda _cfg: [edge])
    monkeypatch.setattr(
        diagnostics.connections,
        "test",
        lambda _cfg, _edge: {"state": "en echec", "detail": "Connexion absente."},
    )

    check = diagnostics.connection_checks(cfg)[0]

    assert check["ok"] is False
    assert check["edge_id"] == edge["id"]
    assert edge["id"] in check["next_step"]
    cfg.services["sonarr"].adopted = True
    assert "Service adopte" in diagnostics.connection_checks(cfg)[0]["next_step"]


def test_compose_drift_reports_change_without_exposing_secrets(tmp_path):
    cfg = _cfg("sonarr")
    cfg.services["sonarr"].api_key = "private-key"
    path = tmp_path / "docker-compose.yml"
    path.write_text("services:\n  sonarr:\n    image: different\n", encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(compose.render_env(cfg, tmp_path), encoding="utf-8")

    check = diagnostics.compose_drift(cfg, tmp_path)

    assert check["ok"] is False
    assert "private-key" not in str(check)
    assert "Sauvegardez" in check["next_step"]
    path.write_text(compose.render_compose(cfg), encoding="utf-8")
    assert diagnostics.compose_drift(cfg, tmp_path)["ok"] is True
    env_path.write_text(env_path.read_text(encoding="utf-8").replace("private-key", "changed"), encoding="utf-8")
    assert diagnostics.compose_drift(cfg, tmp_path)["ok"] is False
    cfg.services["sonarr"].adopted = True
    assert diagnostics.compose_drift(cfg, tmp_path) is None


def test_selective_wiring_runs_only_the_approved_step(monkeypatch):
    wirer = Wirer(_cfg("sonarr", "qbittorrent"))
    called = []

    def step(name):
        return WiringStep(name, lambda: called.append(name) or StepResult(name, True, "ok"))

    monkeypatch.setattr(wirer, "build_plan", lambda: [step("a"), step("b")])

    result = wirer.execute(selected_steps={"b"})

    assert called == ["b"]
    assert [item.step_id for item in result] == ["b"]


def test_le_diagnostic_de_la_console_ne_signale_pas_ses_donnees_en_lecture_seule(tmp_path, monkeypatch):
    """Essai reel du 26/09/2026 : « racine des donnees » en echec BLOQUANT dans la
    console, qui monte DATA_ROOT en lecture seule par conception."""
    from plugarr import orchestrator
    from plugarr.i18n import t
    from plugarr.runner import Check

    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    monkeypatch.setattr(
        orchestrator,
        "preflight",
        lambda *_a, **_k: [
            Check(t("racine des donnees"), False, "Read-only file system", blocking=True),
            Check("hardlinks /data", False, "Read-only file system", blocking=False),
            Check("docker", True, "ok"),
        ],
    )

    monkeypatch.setattr(orchestrator, "_donnees_en_lecture_seule_voulue", lambda _d: True)
    console = orchestrator.diagnostic(cfg)
    assert all(c.ok for c in console)
    assert not any(c.blocking and not c.ok for c in console)

    monkeypatch.setattr(orchestrator, "_donnees_en_lecture_seule_voulue", lambda _d: False)
    hote = orchestrator.diagnostic(cfg)
    assert [c.ok for c in hote] == [False, False, True]


# ------------------------------------------------------ lecture seule stricte


def _instantane(racine):
    """Tout ce qu'une ecriture, meme annulee aussitot, laisserait voir."""
    return {
        (str(p.relative_to(racine)), p.is_dir(), p.stat().st_size, p.stat().st_mtime_ns)
        for p in [racine, *racine.rglob("*")]
    }


def _pile_installee(tmp_path, *services):
    cfg = orchestrator.build_config(
        services=list(services),
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    for dossier in ("torrents", "media"):
        (tmp_path / "data" / dossier).mkdir(parents=True)
    for sid in services:
        (tmp_path / "config" / sid).mkdir(parents=True)
        (tmp_path / "config" / sid / "config.xml").write_text("<Config/>", encoding="utf-8")
    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / "stack.yml").write_text("services: {}\n", encoding="utf-8")
    (projet / "docker-compose.yml").write_text(compose.render_compose(cfg), encoding="utf-8")
    (projet / ".env").write_text(compose.render_env(cfg, projet), encoding="utf-8")
    return cfg, projet


class _Docker:
    def __init__(self, *services):
        self.services = services

    def ps_json(self):
        return [{"Service": s, "State": "running", "Status": "Up 1 hour"} for s in self.services]


def _sans_reseau(monkeypatch):
    """Ni Docker ni sockets : le test ne doit dependre que du disque."""
    monkeypatch.setattr(orchestrator, "check_docker", lambda: [Check("docker", True, "ok")])
    monkeypatch.setattr(orchestrator, "our_published_ports", lambda *_a: set())
    monkeypatch.setattr(orchestrator, "check_port_free", lambda port, sid: Check(f"port {port}", True, "libre"))
    monkeypatch.setattr(orchestrator, "controles_hote", lambda _cfg: [])
    # L'espace libre de la machine de test ne doit pas decider du verdict.
    monkeypatch.setattr(
        orchestrator, "check_disk_space", lambda *_a, **_k: Check("espace disque", True, "ok", blocking=False)
    )
    monkeypatch.setattr(orchestrator, "iter_selected", lambda _cfg: [])
    monkeypatch.setattr(connections, "entries", lambda _cfg: [])
    monkeypatch.setattr(vpncheck, "verifier", lambda _cfg: [])


def test_doctor_sans_repair_n_ecrit_rien_pas_meme_un_fichier_d_essai(tmp_path, monkeypatch):
    """Exigence : le diagnostic sans --repair est ENTIEREMENT en lecture seule.

    Le preflight d'installation cree un fichier et un hardlink d'essai, puis
    les retire. Pour une pile installee, meme ce va-et-vient est une ecriture :
    les deux essais ne doivent plus etre appeles du tout.
    """
    cfg, projet = _pile_installee(tmp_path, "sonarr", "qbittorrent")
    _sans_reseau(monkeypatch)

    def _ecriture(*_a, **_k):
        raise AssertionError("essai d'ecriture pendant un diagnostic")

    monkeypatch.setattr(orchestrator, "check_writable", _ecriture)
    monkeypatch.setattr(orchestrator, "check_hardlinks", _ecriture)
    avant = _instantane(tmp_path)

    charge = admin.doctor_payload(cfg, projet, _Docker("sonarr", "qbittorrent"))

    assert _instantane(tmp_path) == avant
    assert charge["findings"] == [], charge["findings"]
    noms = {c["name"] for c in charge["checks"]}
    assert {"hardlinks /data", "configurations *arr"} <= noms


def test_racine_absente_ou_en_lecture_seule_sans_essai(tmp_path, monkeypatch):
    absente = runner.check_present(tmp_path / "absente", "racine")
    assert not absente.ok and "monte" in absente.detail

    fichier = tmp_path / "fichier"
    fichier.write_text("x", encoding="utf-8")
    assert not runner.check_present(fichier, "racine").ok

    monkeypatch.setattr(runner, "monte_en_lecture_seule", lambda _p: True)
    lecture_seule = runner.check_present(tmp_path, "racine")
    assert not lecture_seule.ok and "lecture seule" in lecture_seule.detail

    monkeypatch.setattr(runner, "monte_en_lecture_seule", lambda _p: None)
    assert runner.check_present(tmp_path, "racine").ok, "Windows : inconnu n'est pas une panne"


def test_hardlinks_juges_par_le_systeme_de_fichiers_sans_rien_creer(tmp_path, monkeypatch):
    manquant = runner.check_same_filesystem(tmp_path)
    assert [c.name for c in manquant] == ["arborescence des donnees"]
    assert not manquant[0].ok

    for dossier in ("torrents", "media"):
        (tmp_path / dossier).mkdir()
    avant = _instantane(tmp_path)
    assert runner.check_same_filesystem(tmp_path)[0].ok
    assert _instantane(tmp_path) == avant

    monkeypatch.setattr(runner, "_peripherique", lambda p: 1 if p.name == "torrents" else 2)
    separes = runner.check_same_filesystem(tmp_path)[0]
    assert separes.name == "hardlinks /data" and not separes.ok


class _Usage:
    free = 50 * 1024**3


def test_le_preflight_d_installation_mesure_le_disque_de_data_root(tmp_path, monkeypatch):
    """Sous Linux, l'ancre d'un chemin absolu est `/` : mesurer l'ancre annoncait
    l'espace du disque SYSTEME, alors que DATA_ROOT est souvent un disque monte
    a part (/mnt/user/data, /volume1/data). A l'installation le dossier n'existe
    pas encore : c'est son premier ancetre existant qui porte le disque."""
    mesures = []
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda p: mesures.append(Path(p)) or _Usage())
    monkeypatch.setattr(orchestrator, "check_docker", list)
    monkeypatch.setattr(orchestrator, "our_published_ports", lambda cfg, d: set())
    cfg = orchestrator.build_config(
        services=["sonarr"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "disque" / "data"),
    )
    assert Path(tmp_path.anchor) != tmp_path, "sinon le test ne distinguerait rien"

    espace = next(c for c in orchestrator.preflight(cfg, None) if c.name == "espace disque")

    assert mesures == [tmp_path]
    assert espace.ok and "50.0" in espace.detail


def test_l_espace_disque_mesure_le_disque_du_dossier_et_non_la_racine(tmp_path, monkeypatch):
    mesures = []
    monkeypatch.setattr(
        runner.shutil, "disk_usage", lambda p: mesures.append(str(p)) or type("U", (), {"free": 50 * 1024**3})()
    )

    runner.check_disk_space(tmp_path / "data" / "absent")
    (tmp_path / "data").mkdir()
    runner.check_disk_space(tmp_path / "data")

    assert mesures == [str(tmp_path), str(tmp_path / "data")]


def test_un_chemin_dont_rien_n_existe_remonte_jusqu_a_la_racine_du_disque(monkeypatch):
    """Pas de regression sous Windows : `C:/plugarr/data` avant la premiere
    installation se mesure toujours sur `C:\\`, comme quand on mesurait l'ancre."""
    mesures = []
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda p: mesures.append(Path(p)) or _Usage())
    racine = Path(Path.cwd().anchor)
    absent = racine / "plugarr-essai-inexistant-7f3a" / "data"
    assert not absent.parent.exists()

    assert runner.check_disk_space(absent).ok
    assert mesures == [racine]


def test_un_disque_illisible_reste_un_avertissement(monkeypatch):
    def _refus(_chemin):
        raise OSError("disque absent")

    monkeypatch.setattr(runner.shutil, "disk_usage", _refus)

    controle = runner.check_disk_space("Z:/data")

    assert not controle.ok and not controle.blocking
    assert "disque absent" in controle.detail


def test_config_xml_manquant_signale_un_volume_de_configuration_suspect(tmp_path):
    cfg, _projet = _pile_installee(tmp_path, "sonarr", "radarr")
    assert orchestrator.check_arr_configs(cfg).ok

    (tmp_path / "config" / "radarr" / "config.xml").unlink()
    manque = orchestrator.check_arr_configs(cfg)
    assert not manque.ok and "radarr" in manque.detail and "sonarr" not in manque.detail

    cfg.services["radarr"].adopted = True
    assert orchestrator.check_arr_configs(cfg).ok, "un service adopte garde sa configuration ailleurs"
    assert orchestrator.check_arr_configs(_cfg("qbittorrent")) is None


# ---------------------------------------------- constats orientes consequences


def _constats(cfg, **champs):
    base = {"preflight": [], "services": [], "links": [], "drift": None, "vpn": []}
    return diagnostics.build_findings(cfg, Path("/projet"), **{**base, **champs})


def _complet(constat):
    """Chaque constat porte les quatre rubriques demandees, non vides."""
    assert constat["finding"] and constat["consequence"] and constat["fix"]
    assert constat["evidence"] and all(constat["evidence"])
    assert constat["severity"] in diagnostics.SEVERITIES
    return constat


def _lien(ok=False, source="sonarr", cible="qbittorrent", kind="downloadclient"):
    return {
        "name": f"Liaison {source} -> {cible}", "ok": ok, "detail": "Connexion absente dans le service source.",
        "edge_id": f"{source}/{kind}/{cible}", "source": source, "target": cible, "kind": kind,
        "next_step": "Examinez la liaison.",
    }


def test_un_service_arrete_masque_ses_liaisons_au_lieu_de_les_dire_cassees():
    cfg = _cfg("sonarr", "qbittorrent")
    arret = {"name": "Etat Sonarr", "ok": False, "detail": "Exited (1)", "service": "sonarr",
             "probe": "state", "next_step": "Consultez les journaux."}

    constats = _constats(cfg, services=[arret], links=[_lien()])

    assert [c["kind"] for c in constats] == ["service"]
    service = _complet(constats[0])
    assert "Sonarr" in service["title"]
    assert any("sonarr/downloadclient/qbittorrent" in e for e in service["evidence"])
    assert service["repair"] is None, "redemarrer un service sort du perimetre de doctor"


def test_docker_injoignable_est_critique_et_absorbe_le_reste():
    constats = _constats(
        _cfg("sonarr", "qbittorrent"),
        preflight=[Check("daemon docker", False, "daemon injoignable")],
        links=[_lien()],
    )

    assert [(c["kind"], c["subject"], c["severity"]) for c in constats] == [("service", "docker", "critical")]


def test_une_liaison_cassee_entre_deux_services_vivants_est_reparable():
    cfg = _cfg("sonarr", "qbittorrent")

    lien = _complet(_constats(cfg, links=[_lien()])[0])

    assert lien["kind"] == "link"
    assert "qBittorrent" in lien["consequence"]
    assert lien["repair"]["id"] == "link:sonarr/downloadclient/qbittorrent"
    cfg.services["sonarr"].adopted = True
    assert _constats(cfg, links=[_lien()])[0]["repair"] is None


def test_un_client_torrent_hors_du_tunnel_est_le_premier_constat():
    cfg = _cfg("sonarr", "qbittorrent")
    fuite = Check("VPN qbittorrent", False, "NON PROTEGE : le conteneur est sur le reseau plugarr_plugarr")

    constats = _constats(
        cfg,
        vpn=[fuite],
        preflight=[Check("espace disque", False, "3.0 Go libres", blocking=False)],
        links=[_lien()],
    )

    vpn = _complet(constats[0])
    assert (vpn["kind"], vpn["severity"]) == ("vpn", "critical")
    assert "adresse IP publique" in vpn["consequence"]
    assert vpn["repair"] is None
    cfg.services["qbittorrent"].adopted = True
    assert "network_mode" in _constats(cfg, vpn=[fuite])[0]["fix"]


def test_se_passer_de_vpn_reste_visible_sans_etre_une_panne():
    constats = _constats(_cfg("qbittorrent"), vpn=[Check("VPN", True, "aucun VPN configure")])

    assert [(c["kind"], c["severity"]) for c in constats] == [("vpn", "info")]


def test_hardlinks_impossibles_et_echantillon_sans_lien():
    cfg = _cfg("sonarr")
    separes = Check("hardlinks /data", False, "deux systemes de fichiers", blocking=False)

    constat = _complet(_constats(cfg, preflight=[separes])[0])
    assert (constat["kind"], constat["severity"]) == ("hardlink", "warning")
    assert "recopie" in constat["consequence"]

    audit = {"checked": 40, "matched": 0, "partial": False, "available": True}
    indetermine = _complet(_constats(cfg, hardlink_audit=audit)[0])
    assert indetermine["severity"] == "info", "zero lien trouve n'est pas une preuve de panne"
    assert _constats(cfg, hardlink_audit={**audit, "matched": 3}) == []


def test_volume_suspect_distingue_absence_et_manque_de_place():
    cfg = _cfg("sonarr")
    absente = Check("racine des donnees", False, "/data est introuvable")
    plein = Check("espace disque", False, "3.0 Go libres", blocking=False)
    config = Check("configurations *arr", False, "config.xml absent pour sonarr", blocking=False)

    donnees = _complet(_constats(cfg, preflight=[absente, plein])[0])
    assert (donnees["subject"], donnees["severity"]) == ("data", "critical")
    assert len(donnees["evidence"]) == 2

    assert _constats(cfg, preflight=[plein])[0]["severity"] == "warning"
    configuration = _complet(_constats(cfg, preflight=[config])[0])
    assert configuration["subject"] == "config" and "vierge" in configuration["consequence"]


def test_une_pile_adoptee_garde_son_arborescence_sans_alarme():
    """`adopt` respecte l'arborescence existante : sans torrents/ ni media/,
    PlugArr ne sait rien des hardlinks, mais ce n'est pas un volume absent."""
    arborescence = Check("arborescence des donnees", False, "torrents/, media/ absent de /data", blocking=False)
    geree = _cfg("sonarr")
    assert _constats(geree, preflight=[arborescence])[0]["severity"] == "critical"

    adoptee = _cfg("sonarr")
    adoptee.services["sonarr"].adopted = True
    constat = _complet(_constats(adoptee, preflight=[arborescence])[0])
    assert (constat["kind"], constat["severity"]) == ("hardlink", "info")


def test_la_derive_nomme_ce_qui_differe_sans_jamais_montrer_une_valeur(tmp_path):
    cfg = _cfg("sonarr", "radarr")
    cfg.services["sonarr"].api_key = "cle-sonarr-tres-privee"
    (tmp_path / "docker-compose.yml").write_text(
        compose.render_compose(cfg).replace("lscr.io/linuxserver/radarr", "example/radarr"),
        encoding="utf-8",
    )
    env = compose.render_env(cfg, tmp_path)
    (tmp_path / ".env").write_text(env.replace("cle-sonarr-tres-privee", "autre-valeur-secrete"), encoding="utf-8")

    drift = diagnostics.compose_drift(cfg, tmp_path)
    constat = _complet(_constats(cfg, drift=drift)[0])

    texte = str(constat)
    assert "radarr" in texte and "SONARR" in texte.upper()
    assert "cle-sonarr-tres-privee" not in texte and "autre-valeur-secrete" not in texte
    assert constat["repair"] is None, "regenerer ecraserait des modifications faites a la main"


def test_port_entrant_desynchronise_n_est_pas_une_fuite():
    cfg = _cfg("qbittorrent")
    cfg.vpn = VpnConfig(enabled=True, provider="protonvpn", vpn_type="wireguard", wireguard_private_key="k" * 44)
    decale = Check(f"{vpncheck.PREFIXE_PORT} qbittorrent", False, "desynchronise", blocking=False)

    port = _complet(_constats(cfg, vpn=[decale])[0])

    assert (port["kind"], port["severity"]) == ("port", "warning")
    assert "protection VPN n'est pas en cause" in port["consequence"]
    assert port["repair"]["id"] == diagnostics.PORT_SYNC


def test_les_constats_parlent_la_langue_de_la_pile():
    avant = i18n.langue()
    try:
        i18n.utiliser("en")
        constat = _constats(_cfg("sonarr", "qbittorrent"), links=[_lien()])[0]
        assert diagnostics.labels()["consequence"] == "What it means for you"
        assert constat["title"].startswith("Connection")
    finally:
        i18n.utiliser(avant)


# ------------------------------------------------------------------ secrets


def test_aucun_secret_ne_sort_du_diagnostic(tmp_path, monkeypatch):
    """Une API qui echoue rend souvent l'URL de l'appel, parametres compris."""
    cfg, projet = _pile_installee(tmp_path, "sonarr")
    cle = cfg.services["sonarr"].api_key
    assert cle and len(cle) >= 8
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(orchestrator, "iter_selected", lambda c: [("sonarr", c.services["sonarr"])])

    class _Refus:
        def __init__(self, *_a, **_k):
            raise RuntimeError(f"401 for url http://localhost:8989/api/v3/system/status?apikey={cle}&x=1")

    monkeypatch.setattr(admin, "ArrClient", _Refus)

    charge = admin.doctor_payload(cfg, projet, _Docker("sonarr"))

    texte = str(charge)
    assert cle not in texte
    assert "<masque>" in texte
    assert [c["kind"] for c in charge["findings"]] == ["service"]


# ------------------------------------------------------------------ repairs


def test_une_reparation_de_liaison_est_toujours_relue(monkeypatch):
    cfg = _cfg("sonarr", "qbittorrent")
    edge = {"id": "sonarr/downloadclient/qbittorrent", "source": "sonarr", "target": "qbittorrent",
            "kind": "downloadclient"}
    appels = []
    monkeypatch.setattr(connections, "entries", lambda _cfg: [edge])

    def _echoue(_cfg, _edge):
        appels.append("repare")
        raise RuntimeError("API muette")

    monkeypatch.setattr(connections, "repair", _echoue)
    monkeypatch.setattr(connections, "test", lambda _c, _e: appels.append("relu") or {"state": "verifiee"})

    resultat = diagnostics.apply_repair(cfg, "link:" + edge["id"])

    assert appels == ["repare", "relu"]
    assert resultat["applied"] is False and resultat["verified"] is True


def test_une_reparation_hors_perimetre_est_refusee(monkeypatch):
    cfg = _cfg("sonarr", "qbittorrent")
    edge = {"id": "sonarr/downloadclient/qbittorrent", "source": "sonarr", "target": "qbittorrent",
            "kind": "downloadclient"}
    monkeypatch.setattr(connections, "entries", lambda _cfg: [edge])
    monkeypatch.setattr(connections, "repair", lambda *_a: pytest.fail("repare un service adopte"))
    cfg.services["sonarr"].adopted = True

    assert diagnostics.apply_repair(cfg, "link:" + edge["id"])["applied"] is False
    assert diagnostics.apply_repair(cfg, "link:inconnue")["applied"] is False
    with pytest.raises(ValueError):
        diagnostics.apply_repair(cfg, "restart:sonarr")


def test_un_port_deja_realigne_n_est_pas_retouche(monkeypatch):
    monkeypatch.setattr(vpncheck, "reparer_port", lambda _cfg: None)

    resultat = diagnostics.apply_repair(_cfg("qbittorrent"), diagnostics.PORT_SYNC)

    assert resultat == {**resultat, "applied": False, "verified": None}
    assert "rien n'a ete modifie" in resultat["detail"]

