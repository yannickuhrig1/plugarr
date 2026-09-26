"""Les droits des dossiers de donnees DEJA presents.

Panne reelle, journal a l'appui, UGOS le 2026-09-21 : l'arborescence existait
d'une installation precedente faite en root, `create_tree` n'y touchait plus —
il ne redistribue que ce qu'il cree — et Sonarr comme Radarr refusaient leurs
trois dossiers racines sur « Folder '/data/media/tv' is not writable by user
'abc' ». L'installation se poursuivait jusqu'au bout, en laissant croire que
seul le gabarit de l'API avait change de forme.
"""

from __future__ import annotations

import os

import pytest

from plugarr import catalog, layout, seed
from plugarr.clients.base import WiringError
from plugarr.models import ServiceInstance, StackConfig
from plugarr.wiring import Wirer

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="droits POSIX : Windows ne porte pas ces bits"
)


def _autre_compte() -> tuple[int, int]:
    """Un couple (uid, gid) qui n'est pas celui qui fait tourner les tests.

    Le test ne doit dependre ni de l'utilisateur ni de la machine : c'est
    l'ECART entre le proprietaire du dossier et l'utilisateur des conteneurs
    qui est mesure, pas une valeur particuliere.
    """
    return os.getuid() + 1, os.getgid() + 1


def _arborescence(tmp_path, mode: int):
    data = tmp_path / "data"
    for sous_dossier in layout.DATA_SUBDIRS:
        (data / sous_dossier).mkdir(parents=True, exist_ok=True)
    for sous_dossier in layout.DATA_SUBDIRS:
        os.chmod(data / sous_dossier, mode)
    return data


def test_un_dossier_ferme_aux_conteneurs_est_repere(tmp_path):
    data = _arborescence(tmp_path, 0o755)

    fermes = layout.donnees_inaccessibles(data, _autre_compte())

    assert [str(p) for p in fermes] == [
        str(data / sous_dossier) for sous_dossier in layout.DATA_SUBDIRS
    ]


def test_un_dossier_ouvert_a_tous_ne_pose_pas_de_probleme(tmp_path):
    data = _arborescence(tmp_path, 0o707)

    assert layout.donnees_inaccessibles(data, _autre_compte()) == []


def test_un_dossier_partage_avec_le_groupe_des_conteneurs_est_laisse_tel_quel(tmp_path):
    """Un dossier de groupe en 770 est un partage VOULU. Le reprendre au nom de
    la reparation reviendrait a defaire le reglage de quelqu'un."""
    data = _arborescence(tmp_path, 0o770)

    fermes = layout.donnees_inaccessibles(data, (os.getuid() + 1, os.getgid()))

    assert fermes == []


def test_un_dossier_absent_n_est_pas_un_dossier_ferme(tmp_path):
    """Ce que `create_tree` va creer lui-meme n'a rien a faire dans la liste :
    il naitra avec le bon proprietaire."""
    assert layout.donnees_inaccessibles(tmp_path / "data", _autre_compte()) == []


def test_lance_en_sudo_les_dossiers_fermes_sont_rendus(tmp_path, monkeypatch):
    data = _arborescence(tmp_path, 0o755)
    donnes: list[tuple[str, tuple[int, int]]] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(
        os, "chown", lambda chemin, uid, gid, **_: donnes.append((str(chemin), (uid, gid)))
    )

    repares, restants = layout.ouvrir_donnees(data, (1000, 10))

    assert restants == []
    assert [str(p) for p in repares] == [nom for nom, _ in donnes]
    assert all(owner == (1000, 10) for _, owner in donnes)


def test_le_chown_ne_descend_pas_dans_la_mediatheque(tmp_path, monkeypatch):
    """Un `chown -R` sur plusieurs tera prendrait des heures, et redistribuerait
    des fichiers que plugarr n'a pas crees. Donner le dossier suffit."""
    data = _arborescence(tmp_path, 0o755)
    film = data / "media" / "movies" / "un film"
    film.mkdir()
    (film / "un film.mkv").write_text("x")
    touches: list[str] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(os, "chown", lambda chemin, *_a, **_k: touches.append(str(chemin)))

    layout.ouvrir_donnees(data, (1000, 10))

    assert str(film) not in touches
    assert str(film / "un film.mkv") not in touches
    assert str(data / "media" / "movies") in touches


def test_hors_root_rien_n_est_repare_mais_tout_est_signale(tmp_path, monkeypatch):
    """`chown` est refuse a tout le monde sauf root, meme sur ses propres
    dossiers : il n'y a rien a tenter, seulement quelque chose a dire."""
    data = _arborescence(tmp_path, 0o755)
    monkeypatch.setattr(layout, "_est_root", lambda: False)
    monkeypatch.setattr(
        os, "chown", lambda *_a, **_k: pytest.fail("chown tente sans elevation")
    )

    repares, restants = layout.ouvrir_donnees(data, _autre_compte())

    assert repares == []
    assert len(restants) == len(layout.DATA_SUBDIRS)


def test_un_chown_refuse_laisse_le_dossier_dans_les_restants(tmp_path, monkeypatch):
    data = _arborescence(tmp_path, 0o755)
    monkeypatch.setattr(layout, "_est_root", lambda: True)

    def _refuse(*_a, **_k):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chown", _refuse)

    repares, restants = layout.ouvrir_donnees(data, _autre_compte())

    assert repares == []
    assert len(restants) == len(layout.DATA_SUBDIRS)


def test_l_installation_repare_avant_de_demarrer_la_pile():
    """L'ordre compte : reparer apres le demarrage laisserait les applications
    decouvrir des dossiers interdits, ce qui est exactement la panne d'origine."""
    import inspect

    from plugarr import orchestrator

    source = inspect.getsource(orchestrator.install)
    assert source.index("ouvrir_donnees") < source.index("runner.pull_many"), source


# ------------------------------------------------ ce que Sonarr repond vraiment


def _cfg(tmp_path):
    cfg = StackConfig(config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d"))
    cfg.puid, cfg.pgid = 1000, 10
    for sid in catalog.resolve_dependencies(["sonarr"]):
        spec = catalog.get(sid)
        cfg.services[sid] = ServiceInstance(
            spec_id=sid,
            host_port=spec.default_host_port,
            api_key=seed.generate_api_key() if spec.api_family == "arr" else None,
            username="plugarr",
            password="pw",
        )
    return cfg


#: La reponse de Sonarr, recopiee du journal du 2026-09-21.
REFUS = (
    'HTTP 400 - [{"propertyName":"Path","errorMessage":"Folder \'/data/media/tv\' '
    "is not writable by user 'abc'\",\"errorCode\":\"FolderWritableValidator\"}]"
)


def test_le_refus_de_sonarr_devient_un_chown_a_faire(tmp_path):
    cfg = _cfg(tmp_path)
    brute = WiringError(
        "sonarr: POST rootfolder a echoue",
        REFUS,
        "le gabarit renvoye par /schema a peut-etre change de forme",
    )

    traduite = Wirer(cfg)._dossier_refuse("sonarr", "/data/media/tv", brute)

    assert "/data/media/tv" in traduite.what
    # Le chemin de l'HOTE : « /data » ne mene nulle part depuis un terminal.
    assert str(tmp_path / "d" / "media" / "tv") in traduite.fix
    assert "chown 1000:10" in traduite.fix
    assert "/schema" not in traduite.fix


def test_une_vraie_panne_de_gabarit_n_est_pas_maquillee_en_probleme_de_droits(tmp_path):
    """Le message generique reste le bon pour tout le reste : le traduire au
    petit bonheur enverrait chercher un `chown` la ou il n'y en a pas."""
    cfg = _cfg(tmp_path)
    brute = WiringError(
        "sonarr: POST rootfolder a echoue",
        "HTTP 400 - [{'errorCode': 'PathValidator'}]",
        "le gabarit renvoye par /schema a peut-etre change de forme",
    )

    assert Wirer(cfg)._dossier_refuse("sonarr", "/data/media/tv", brute) is brute


def test_un_chemin_hors_du_montage_unique_est_rendu_tel_quel(tmp_path):
    cfg = _cfg(tmp_path)

    assert Wirer(cfg)._chemin_hote("/mnt/ailleurs") == "/mnt/ailleurs"


def test_une_arborescence_entiere_ne_noie_pas_la_consigne(tmp_path):
    """Vingt-huit chemins cites en entier repoussent hors de vue le `chown` qui
    suit. Les premiers suffisent a reconnaitre de quoi on parle."""
    from plugarr.orchestrator import _liste_courte

    chemins = [tmp_path / f"d{rang}" for rang in range(28)]

    resume = _liste_courte(chemins)

    assert str(chemins[0]) in resume
    assert str(chemins[5]) not in resume
    assert "+23" in resume
    assert _liste_courte(chemins[:2]) == f"{chemins[0]}, {chemins[1]}"
