"""Une sauvegarde qui oublie quelque chose ne se revele qu'au pire moment.

Demande a l'usage : « un systeme de sauvegarde complete de notre config, pour
la reinstaller. Ca eviterait de remettre tous les parametres des indexeurs ».

La distinction qui donne sa forme au module : PlugArr regenere tout ce qu'il a
GENERE — mots de passe, cles API, ports, tous dans `stack.yml`. Il ne sait rien
de ce que l'utilisateur a saisi ENSUITE, qui vit dans les bases SQLite des
services. C'est cela qu'une reinstallation perdait.

Le piege le moins visible : la base de Silo n'est PAS sous CONFIG_ROOT depuis
qu'elle est passee dans un volume Docker pour des raisons de vitesse. Une
sauvegarde qui n'archive que des dossiers la manque en SILENCE, et la
restauration rend un Silo qui redemarre en boucle sur « password
authentication failed ».
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest
import yaml

from plugarr import orchestrator, sauvegarde


class _FauxCompose:
    """La pile est reputee arretee : aucun Docker dans les tests."""

    def __init__(self, *_args):
        pass

    def stop(self):
        return True, ""

    def up(self):
        return True, ""


@pytest.fixture
def projet(tmp_path, monkeypatch):
    """Une installation minimale posee sur le disque, sans Docker."""
    config = tmp_path / "config"
    dossier = tmp_path / "projet"
    dossier.mkdir()
    cfg = orchestrator.build_config(
        services=["sonarr", "prowlarr"],
        config_root=str(config),
        data_root=str(tmp_path / "data"),
    )
    (config / "sonarr").mkdir(parents=True)
    (config / "sonarr" / "sonarr.db").write_bytes(b"vos series et vos profils")
    (config / "sonarr" / "config.xml").write_text("<Config/>", encoding="utf-8")
    (config / "sonarr" / "logs").mkdir()
    (config / "sonarr" / "logs" / "bruit.txt").write_text("x" * 5000, encoding="utf-8")
    (config / "prowlarr").mkdir()
    (config / "prowlarr" / "prowlarr.db").write_bytes(b"vos indexeurs")

    for nom, contenu in (
        ("stack.yml", "project_name: plugarr\n"),
        (".env", f"CONFIG_ROOT={config.as_posix()}\nSONARR_API_KEY=secret\n"),
        ("docker-compose.yml", "services: {}\n"),
    ):
        (dossier / nom).write_text(contenu, encoding="utf-8")

    monkeypatch.setattr(sauvegarde, "volumes_du_projet", lambda c: [])
    monkeypatch.setattr(sauvegarde, "Compose", _FauxCompose)
    return cfg, dossier, config


def _noms(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


def test_le_travail_de_l_utilisateur_est_dedans(projet, tmp_path):
    """Les indexeurs de Prowlarr : la raison d'etre de la fonction."""
    cfg, dossier, _ = projet

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    noms = _noms(tmp_path / "a.zip")
    assert "config/prowlarr/prowlarr.db" in noms
    assert "config/sonarr/sonarr.db" in noms


def test_les_secrets_generes_sont_dedans(projet, tmp_path):
    """Sans le .env ni stack.yml, aucun service ne se rouvre apres restauration."""
    cfg, dossier, _ = projet

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    noms = _noms(tmp_path / "a.zip")
    assert "projet/stack.yml" in noms
    assert "projet/.env" in noms
    assert "projet/docker-compose.yml" in noms


def test_les_journaux_et_les_caches_sont_exclus(projet, tmp_path):
    """Ils se refabriquent et pesent souvent plus que la configuration."""
    cfg, dossier, _ = projet

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    assert not [n for n in _noms(tmp_path / "a.zip") if "/logs/" in n]


def test_un_fichier_date_de_1970_ne_fait_pas_echouer_toute_la_sauvegarde(
    projet, tmp_path
):
    """Des conteneurs posent parfois des mtimes Unix impossibles pour ZIP."""
    cfg, dossier, config = projet
    ancien = config / "sonarr" / "epoch.db"
    ancien.write_bytes(b"etat important")
    os.utime(ancien, (0, 0))

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    assert "config/sonarr/epoch.db" in _noms(tmp_path / "a.zip")


def test_les_medias_ne_sont_jamais_touches(projet, tmp_path):
    """DATA_ROOT pese des teraoctets. L'inclure transformerait une sauvegarde
    de trente secondes en une nuit de copie."""
    cfg, dossier, _ = projet
    medias = Path(cfg.data_root) / "media" / "movies"
    medias.mkdir(parents=True)
    (medias / "film.mkv").write_bytes(b"x" * 10000)

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    assert not [n for n in _noms(tmp_path / "a.zip") if "film.mkv" in n]


def test_le_manifeste_dit_ce_qu_il_y_a_dedans(projet, tmp_path):
    cfg, dossier, config = projet

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    with zipfile.ZipFile(tmp_path / "a.zip") as zf:
        m = json.loads(zf.read(sauvegarde.MANIFESTE))
    assert m["format"] == sauvegarde.FORMAT
    assert m["config_root"] == str(config)
    assert m["services"] == ["prowlarr", "sonarr"]
    assert m["a_chaud"] is False


def test_une_sauvegarde_a_chaud_le_dit(projet, tmp_path):
    """Elle peut etre corrompue : la restauration doit pouvoir avertir."""
    cfg, dossier, _ = projet

    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip", live=True)

    with zipfile.ZipFile(tmp_path / "a.zip") as zf:
        assert json.loads(zf.read(sauvegarde.MANIFESTE))["a_chaud"] is True


def test_les_conteneurs_sont_arretes_par_defaut(projet, tmp_path):
    """Une base SQLite copiee pendant qu'on ecrit dedans donne un fichier
    valide en apparence et inutilisable en pratique."""
    cfg, dossier, _ = projet

    assert sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip").arret is True
    assert sauvegarde.sauvegarder(cfg, dossier, tmp_path / "b.zip", live=True).arret is False


def test_la_restauration_repose_tout(projet, tmp_path, monkeypatch):
    cfg, dossier, _config = projet
    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")

    neuf_projet = tmp_path / "ailleurs"
    neuve_config = tmp_path / "config2"
    monkeypatch.setattr(sauvegarde, "_restaurer_volume", lambda n, s: True)

    sauvegarde.restaurer(tmp_path / "a.zip", neuf_projet, config_root=str(neuve_config))

    assert (neuve_config / "prowlarr" / "prowlarr.db").read_bytes() == b"vos indexeurs"
    assert (neuf_projet / "stack.yml").is_file()
    assert (neuf_projet / ".env").is_file()


def test_restaurer_ailleurs_reecrit_les_chemins(projet, tmp_path, monkeypatch):
    """Une machine neuve n'a pas les memes lettres de lecteur. Sans reecriture,
    la pile restauree pointe vers un dossier inexistant."""
    cfg, dossier, _config = projet
    sauvegarde.sauvegarder(cfg, dossier, tmp_path / "a.zip")
    monkeypatch.setattr(sauvegarde, "_restaurer_volume", lambda n, s: True)

    neuve = tmp_path / "config2"
    sauvegarde.restaurer(tmp_path / "a.zip", tmp_path / "p2", config_root=str(neuve))

    donnees = yaml.safe_load((tmp_path / "p2" / "stack.yml").read_text(encoding="utf-8"))
    assert donnees["config_root"] == str(neuve)
    assert neuve.as_posix() in (tmp_path / "p2" / ".env").read_text(encoding="utf-8")


def test_une_archive_etrangere_est_refusee(tmp_path):
    """Deballer n'importe quel zip sur CONFIG_ROOT serait destructeur."""
    faux = tmp_path / "faux.zip"
    with zipfile.ZipFile(faux, "w") as zf:
        zf.writestr("bonjour.txt", "je ne suis pas une sauvegarde")

    with pytest.raises(ValueError, match="pas une sauvegarde"):
        sauvegarde.lire_manifeste(faux)


def test_un_format_inconnu_est_refuse(tmp_path):
    """Mieux vaut refuser que deballer une disposition qu'on ne comprend pas."""
    futur = tmp_path / "futur.zip"
    with zipfile.ZipFile(futur, "w") as zf:
        zf.writestr(sauvegarde.MANIFESTE, json.dumps({"format": 999}))

    with pytest.raises(ValueError, match="format"):
        sauvegarde.lire_manifeste(futur)


def test_un_manifeste_malforme_est_refuse_proprement(tmp_path):
    archive = tmp_path / "manifeste-invalide.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(sauvegarde.MANIFESTE, "{pas du json")

    with pytest.raises(ValueError, match="manifeste"):
        sauvegarde.lire_manifeste(archive)


@pytest.mark.parametrize(
    "membre",
    (
        "config/../../hors-racine.txt",
        "config/..\\hors-racine.txt",
        "projet/../../hors-racine.txt",
    ),
)
def test_la_restauration_refuse_toute_sortie_des_racines(tmp_path, membre):
    """L'archive choisie dans l'assistant web peut etre hostile."""
    archive = tmp_path / "hostile.zip"
    manifeste = {
        "format": sauvegarde.FORMAT,
        "project_name": "plugarr",
        "config_root": str(tmp_path / "ancien"),
        "data_root": str(tmp_path / "data"),
        "services": [],
        "volumes": [],
        "a_chaud": False,
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(sauvegarde.MANIFESTE, json.dumps(manifeste))
        zf.writestr(membre, "interdit")

    with pytest.raises(ValueError, match="interdit"):
        sauvegarde.restaurer(
            archive,
            tmp_path / "projet-neuf",
            config_root=str(tmp_path / "config-neuve"),
        )
    assert not (tmp_path / "hors-racine.txt").exists()


def test_la_restauration_ne_suit_pas_un_lien_symbolique_hors_config(tmp_path):
    archive = tmp_path / "hostile-lien.zip"
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    config = tmp_path / "config-neuve"
    config.mkdir()
    try:
        (config / "lien").symlink_to(dehors, target_is_directory=True)
    except OSError:
        pytest.skip("la creation de liens symboliques n'est pas autorisee")
    manifeste = {
        "format": sauvegarde.FORMAT,
        "project_name": "plugarr",
        "config_root": str(config),
        "data_root": str(tmp_path / "data"),
        "services": [],
        "volumes": [],
        "a_chaud": False,
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(sauvegarde.MANIFESTE, json.dumps(manifeste))
        zf.writestr("config/lien/secret.txt", "interdit")

    with pytest.raises(ValueError, match="interdit"):
        sauvegarde.restaurer(archive, tmp_path / "projet-neuf", config_root=str(config))
    assert not (dehors / "secret.txt").exists()


def test_la_restauration_refuse_un_nom_de_volume_injecte(tmp_path):
    archive = tmp_path / "hostile-volume.zip"
    manifeste = {
        "format": sauvegarde.FORMAT,
        "project_name": "plugarr",
        "config_root": str(tmp_path / "config"),
        "data_root": str(tmp_path / "data"),
        "services": [],
        "volumes": ["../volume"],
        "a_chaud": False,
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(sauvegarde.MANIFESTE, json.dumps(manifeste))

    with pytest.raises(ValueError, match="volumes"):
        sauvegarde.restaurer(archive, tmp_path / "projet-neuf")


def test_le_volume_de_silo_est_reclame(monkeypatch):
    """Il n'est PAS sous CONFIG_ROOT. Une sauvegarde qui n'archive que des
    dossiers le manque en silence."""
    cfg = orchestrator.build_config(
        services=["silo"], config_root="/c", data_root="/d", project_name="essai"
    )
    monkeypatch.setattr(sauvegarde, "volume_exists", lambda n: True)

    assert sauvegarde.volumes_du_projet(cfg) == ["essai_silo-pgdata"]


def test_aucun_volume_sans_silo():
    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")

    assert sauvegarde.volumes_du_projet(cfg) == []


def test_la_console_porte_le_bouton_de_sauvegarde():
    """Regle du projet : rien ne doit etre reserve a la ligne de commande."""
    from plugarr import dashboard

    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")
    page = dashboard.render(cfg, live=True)

    assert 'id="btn-sauvegarde"' in page
    assert "/api/backup" in page


def test_la_page_d_acces_statique_ne_le_porte_pas():
    """Aucun serveur derriere elle : le bouton ne serait branche a rien."""
    from plugarr import dashboard

    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")

    assert "btn-sauvegarde" not in dashboard.render(cfg)


def test_la_restauration_reste_en_ligne_de_commande():
    """Elle ECRASE une configuration en place. Un bouton sur une page ouverte
    dans un navigateur, a un clic d'une mauvaise archive, serait une arme."""
    from plugarr import dashboard

    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")

    assert "/api/restore" not in dashboard.render(cfg, live=True)


def test_un_fichier_qui_n_est_pas_une_archive_ne_plante_pas(tmp_path):
    """`zipfile.BadZipFile` herite d'`Exception`, PAS de `ValueError`.

    Les deux appelants attrapaient `(ValueError, OSError)` : un fichier texte
    renomme en .zip passait donc au travers, et `plugarr restore` sortait sur
    une trace Python brute suivie de « Failed to execute script 'launcher' ».

    Constate en lancant l'EXECUTABLE PUBLIE, pas en relisant le code : les
    tests passaient tous.
    """
    faux = tmp_path / "faux.zip"
    faux.write_text("ceci n'est pas une archive", encoding="utf-8")

    with pytest.raises(ValueError, match="archive"):
        sauvegarde.lire_manifeste(faux)


def test_les_deux_appelants_attrapent_bien_cette_erreur():
    """Le correctif vaut par la conversion en `ValueError`, pas par un
    `except` elargi dans chaque appelant : c'est ce qui garantit qu'un
    troisieme appelant en beneficiera aussi."""
    import inspect

    from plugarr import cli
    from plugarr.tui import screens

    for source in (
        inspect.getsource(cli.restore),
        inspect.getsource(screens.RestaurationScreen.examiner),
    ):
        assert "lire_manifeste" in source
        assert "ValueError" in source
