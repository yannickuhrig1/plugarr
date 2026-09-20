"""VueTorrent, interface de remplacement de qBittorrent, en option.

Mesure le 2026-09-19 sur le banc (qBittorrent 5.2.3, LinuxServer) :

- le chargeur de mods accepte `depot:tag@sha256:...` : la version est figee ;
- recree sans Internet et sans `/modcache` en volume, le conteneur saute le mod
  et qBittorrent reecrit `AlternativeUIEnabled=false` : VueTorrent est perdu
  pour de bon. Avec le volume, il est repris du cache ;
- theme.park, lui, reclone les sources de qBittorrent a chaque creation et
  disparait hors ligne meme avec le cache : il n'est pas propose.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from plugarr import catalog, compose, migrations, orchestrator, reprise, seed, webwizard
from plugarr.cli import app
from plugarr.models import StackConfig


def _cfg(services=("sonarr", "qbittorrent"), interface=""):
    cfg = orchestrator.build_config(services=list(services), config_root="/c", data_root="/d")
    cfg.qbittorrent_ui = interface
    return cfg


def _bloc_qbittorrent(cfg):
    return compose.build_compose(cfg)["services"]["qbittorrent"]


# ------------------------------------------------------------------ compose


def test_vuetorrent_pose_le_mod_epingle_et_son_cache():
    bloc = _bloc_qbittorrent(_cfg(interface="vuetorrent"))

    assert bloc["environment"]["DOCKER_MODS"] == catalog.VUETORRENT_MOD
    assert "${CONFIG_ROOT}/qbittorrent/modcache:/modcache" in bloc["volumes"]


def test_le_mod_est_fige_par_son_digest():
    """Un tag seul peut etre republie : seul le digest fige le contenu."""
    depot, _, digest = catalog.VUETORRENT_MOD.partition("@sha256:")
    assert ":" in depot.rsplit("/", 1)[1], "tag lisible absent"
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


def test_l_interface_d_origine_ne_touche_pas_au_conteneur():
    bloc = _bloc_qbittorrent(_cfg())

    assert "DOCKER_MODS" not in bloc["environment"]
    assert not any("modcache" in v for v in bloc["volumes"])


# ----------------------------------------------------------- qBittorrent.conf


def test_le_pre_semis_choisit_vuetorrent_des_le_premier_demarrage(tmp_path):
    seed.seed_qbittorrent(tmp_path, username="u", password="p", interface="vuetorrent")
    texte = (tmp_path / "qBittorrent" / "qBittorrent.conf").read_text(encoding="utf-8")

    assert "WebUI\\AlternativeUIEnabled=true" in texte.splitlines()
    assert "WebUI\\RootFolder=/vuetorrent" in texte.splitlines()


def test_sans_vuetorrent_le_pre_semis_ne_dit_rien_de_l_interface(tmp_path):
    seed.seed_qbittorrent(tmp_path, username="u", password="p")
    texte = (tmp_path / "qBittorrent" / "qBittorrent.conf").read_text(encoding="utf-8")

    assert "AlternativeUIEnabled" not in texte
    assert "RootFolder" not in texte


def _conf_existante(tmp_path, *lignes):
    dossier = tmp_path / "qBittorrent"
    dossier.mkdir()
    cible = dossier / "qBittorrent.conf"
    cible.write_text("[Preferences]\n" + "\n".join(lignes) + "\n", encoding="utf-8")
    return cible


def test_une_conf_existante_passe_a_vuetorrent(tmp_path):
    cible = _conf_existante(tmp_path, "WebUI\\AlternativeUIEnabled=false", "Garder=1")

    seed.seed_qbittorrent(tmp_path, username="u", password="p", interface="vuetorrent")
    lignes = cible.read_text(encoding="utf-8").splitlines()

    assert "WebUI\\AlternativeUIEnabled=true" in lignes
    assert "WebUI\\RootFolder=/vuetorrent" in lignes
    assert "Garder=1" in lignes


def test_abandonner_vuetorrent_rend_l_interface_d_origine(tmp_path):
    cible = _conf_existante(
        tmp_path, "WebUI\\AlternativeUIEnabled=true", "WebUI\\RootFolder=/vuetorrent"
    )

    seed.seed_qbittorrent(tmp_path, username="u", password="p")

    assert "WebUI\\AlternativeUIEnabled=false" in cible.read_text(encoding="utf-8").splitlines()


def test_une_interface_posee_a_la_main_n_est_pas_touchee(tmp_path):
    cible = _conf_existante(
        tmp_path, "WebUI\\AlternativeUIEnabled=true", "WebUI\\RootFolder=/mon-theme"
    )

    seed.seed_qbittorrent(tmp_path, username="u", password="p")
    lignes = cible.read_text(encoding="utf-8").splitlines()

    assert "WebUI\\AlternativeUIEnabled=true" in lignes
    assert "WebUI\\RootFolder=/mon-theme" in lignes


# ------------------------------------------------------ stack.yml et reprise


def test_seules_les_interfaces_mesurees_sont_acceptees():
    donnees = {**_cfg().model_dump(), "qbittorrent_ui": "themepark"}
    with pytest.raises(ValidationError):
        StackConfig.model_validate(donnees)


def test_stack_yml_passe_en_version_4():
    """Une PlugArr plus ancienne doit refuser ce fichier plutot que d'effacer
    le choix de VueTorrent, champ qu'elle ne connait pas."""
    migre, notes = migrations.migrer({"version": 3})

    assert migre["version"] == 4 == migrations.VERSION_COURANTE
    assert notes == ["stack.yml migre en version 4"]


def test_une_reinstallation_garde_vuetorrent():
    neuve = _cfg()
    reprise.appliquer(neuve, _cfg(interface="vuetorrent"))

    assert neuve.qbittorrent_ui == "vuetorrent"


def test_revenir_a_l_origine_a_la_reinstallation_est_respecte():
    neuve = _cfg()
    reprise.appliquer(neuve, _cfg(interface="vuetorrent"), imposes={"qbittorrent_ui"})

    assert neuve.qbittorrent_ui == ""


# ----------------------------------------------------- les trois interfaces


def _install(tmp_path, *options):
    return CliRunner().invoke(
        app,
        [
            "install",
            "--config-root", str(tmp_path / "c"),
            "--data-root", str(tmp_path / "d"),
            "--project-dir", str(tmp_path),
            "--dry-run",
            *options,
        ],
    )


def test_la_ligne_de_commande_refuse_une_interface_inconnue(tmp_path):
    resultat = _install(tmp_path, "--services", "sonarr,qbittorrent", "--qbittorrent-ui", "themepark")

    assert resultat.exit_code == 1
    assert "--qbittorrent-ui" in resultat.output


def test_la_ligne_de_commande_refuse_vuetorrent_sans_qbittorrent(tmp_path):
    resultat = _install(tmp_path, "--services", "sonarr,transmission", "--qbittorrent-ui", "vuetorrent")

    assert resultat.exit_code == 1
    assert "--qbittorrent-ui" in resultat.output


def test_l_assistant_web_accepte_et_valide_le_choix(tmp_path):
    etat = webwizard.WizardState(tmp_path, demo=True)
    formulaire = etat.bootstrap()["form"]
    assert formulaire["qbittorrent_ui"] == ""
    formulaire["services"] = ["sonarr", "qbittorrent"]
    formulaire["qbittorrent_ui"] = "vuetorrent"

    assert etat.build_config(formulaire).qbittorrent_ui == "vuetorrent"

    formulaire["services"] = ["sonarr", "transmission"]
    with pytest.raises(ValueError, match="VueTorrent"):
        etat.build_config(formulaire)
    formulaire["services"] = ["sonarr", "qbittorrent"]
    formulaire["qbittorrent_ui"] = "themepark"
    with pytest.raises(ValueError, match="inconnue"):
        etat.build_config(formulaire)


@pytest.mark.asyncio
async def test_le_tui_ne_pose_la_question_qu_avec_qbittorrent(tmp_path):
    from textual.widgets import RadioButton

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import VpnScreen

    app_tui = PlugArrApp(project_dir=tmp_path)
    async with app_tui.run_test() as pilot:
        pilot.app.selection = ["sonarr", "transmission"]
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        assert not pilot.app.screen.query("#qbittorrent-ui"), "question posee sans objet"
        pilot.app.pop_screen()
        await pilot.pause()

        pilot.app.selection = ["sonarr", "qbittorrent"]
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        ecran = pilot.app.screen
        assert ecran.qbittorrent_ui_voulu() == "", "VueTorrent coche sans qu'on le demande"

        ecran.query_one("#qbui-vuetorrent", RadioButton).value = True
        await pilot.pause()
        assert ecran.qbittorrent_ui_voulu() == "vuetorrent"
