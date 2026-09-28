"""Deux installations qui partagent un nom de projet partagent leurs conteneurs.

Panne reelle, provoquee en installant une pile d'essai a cote d'une pile en
service. Les deux portaient le nom par defaut `plugarr` :

    docker compose -p plugarr up   depuis C:/tmp/essai
    -> les six conteneurs de C:/plugarr sont RECREES, pointant vers C:/tmp/essai

Docker identifie une pile par un LABEL de projet, jamais par le repertoire d'ou
elle est lancee. Les fichiers de la premiere installation restent intacts, mais
ses services repartent sur la configuration de la seconde, et rien ne le dit.

Pire, le preflight rassurait : « port 8090 occupe par votre propre pile
plugarr ». C'etait vrai du nom et faux de l'installation.
"""

from __future__ import annotations

from pathlib import Path

from plugarr import orchestrator


def _cfg():
    return orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")


def test_une_pile_ailleurs_est_signalee(monkeypatch):
    monkeypatch.setattr(orchestrator, "running_project_dir", lambda nom: "C:/plugarr")

    check = orchestrator.check_project_collision(_cfg(), Path("C:/tmp/essai"))

    assert check is not None
    assert not check.ok
    assert "C:/plugarr" in check.detail or r"C:\plugarr" in check.detail


def test_se_reinstaller_soi_meme_ne_dit_rien(monkeypatch):
    """Le cas normal : rejouer une installation sur sa propre pile."""
    monkeypatch.setattr(orchestrator, "running_project_dir", lambda nom: "C:/plugarr")

    assert orchestrator.check_project_collision(_cfg(), Path("C:/plugarr")) is None


def test_aucune_pile_en_marche_ne_dit_rien(monkeypatch):
    monkeypatch.setattr(orchestrator, "running_project_dir", lambda nom: None)

    assert orchestrator.check_project_collision(_cfg(), Path("C:/plugarr")) is None


def test_l_avertissement_ne_bloque_pas(monkeypatch):
    """Ecraser sa propre pile est parfois voulu. On previent, on n'interdit pas."""
    monkeypatch.setattr(orchestrator, "running_project_dir", lambda nom: "C:/ailleurs")

    check = orchestrator.check_project_collision(_cfg(), Path("C:/ici"))

    assert check is not None and not check.blocking


def test_le_preflight_le_porte(monkeypatch):
    """Le controle doit atteindre l'utilisateur, pas seulement exister."""
    monkeypatch.setattr(orchestrator, "running_project_dir", lambda nom: "C:/ailleurs")
    monkeypatch.setattr(orchestrator, "check_docker", list)
    monkeypatch.setattr(orchestrator, "our_published_ports", lambda cfg, d: set())

    noms = [c.name for c in orchestrator.preflight(_cfg(), Path("C:/ici"))]

    assert "nom de projet" in noms


def test_le_nom_de_la_pile_se_choisit():
    """Sans cette option, deux piles sur une machine etaient impossibles : le
    nom etait fige a `plugarr`, et la seconde installation emportait la
    premiere. C'est ce qui est arrive."""
    from plugarr import orchestrator as o

    cfg = o.build_config(
        services=["sonarr"], config_root="/c", data_root="/d", project_name="plugarr-essai"
    )

    assert cfg.project_name == "plugarr-essai"


def test_les_conteneurs_portent_ce_nom():
    """Le nom doit atteindre les conteneurs, sinon il ne protege de rien."""
    from plugarr import compose
    from plugarr import orchestrator as o

    cfg = o.build_config(
        services=["sonarr"], config_root="/c", data_root="/d", project_name="plugarr-essai"
    )
    doc = compose.build_compose(cfg)

    assert doc["name"] == "plugarr-essai"
    assert doc["services"]["sonarr"]["container_name"] == "plugarr-essai-sonarr"


def test_les_piles_installees_avant_le_renommage_restent_reconnues():
    """arrsenal est devenu PlugArr. Les piles posees avant portent encore le
    marqueur `arrsenal.managed`, et elles tournent.

    Ne lire que le nouveau marqueur les rendrait invisibles a `scan` et a
    `adopt`, sans un mot — et une installation qu'un outil ne voit plus est une
    installation qu'il proposera de recreer par-dessus. C'est exactement la
    panne qui a remplace une pile en service pendant le developpement.
    """
    from plugarr.discovery import _pose_par_nous

    ancienne = {"Config": {"Labels": {"arrsenal.managed": "true"}}}
    nouvelle = {"Config": {"Labels": {"plugarr.managed": "true"}}}
    etrangere = {"Config": {"Labels": {"com.docker.compose.project": "autre"}}}

    assert _pose_par_nous(ancienne), "une pile arrsenal n'est plus reconnue"
    assert _pose_par_nous(nouvelle)
    assert not _pose_par_nous(etrangere)


def test_les_nouveaux_conteneurs_portent_le_nouveau_marqueur():
    from plugarr import compose, orchestrator

    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")
    labels = compose.build_compose(cfg)["services"]["sonarr"]["labels"]

    assert labels["plugarr.managed"] == "true"
    assert "arrsenal.managed" not in labels


def test_l_assistant_porte_les_couleurs_de_la_marque():
    """Demande a l'usage : « pense aussi a mettre l'installateur aux couleurs de
    l'app ». Textual construit toutes ses nuances a partir de ces valeurs."""
    from plugarr.tui.app import THEME

    assert THEME.name == "plugarr"
    assert THEME.primary == "#8B36C9"
    assert THEME.accent == "#F79B45"


def test_l_executable_a_une_icone():
    """Il n'en avait aucune : Windows lui collait celle, generique, de tout
    binaire console."""
    import pathlib

    racine = pathlib.Path(__file__).resolve().parent.parent
    icone = racine / "assets" / "plugarr.ico"

    assert icone.is_file(), "assets/plugarr.ico manquant"
    spec = (racine / "packaging" / "plugarr.spec").read_text(encoding="utf-8")
    assert 'OPTIONS_ICONE = {"icon": str(ROOT / "assets" / "plugarr.ico")}' in spec
    assert "sys.platform == \"win32\"" in spec
