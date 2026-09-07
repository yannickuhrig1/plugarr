"""`--dry-run` annoncait « rien n'a encore ete ecrit » et ecrivait quand meme.

Le controle des hardlinks ne devine pas, il essaie : c'est sa qualite. Mais
essayer demande deux VRAIS dossiers, et il les laissait derriere lui — avec
toute leur chaine de parents, `mkdir` etant appele avec `parents=True`.

Constate sur un conteneur d'essai, avec une racine qui n'existait pas avant :

    $ plugarr install --dry-run --data-root /srv/essai-neuf/data ...
                        Summary - nothing written yet
    $ find /srv/essai-neuf
    /srv/essai-neuf
    /srv/essai-neuf/data
    /srv/essai-neuf/data/media
    /srv/essai-neuf/data/torrents

`--dry-run` est precisement la commande qu'on lance pour regarder sans
s'engager. Trois emplacements compares laissaient trois arborescences, et une
faute de frappe dans le chemin creait un dossier la ou personne ne le voulait.
"""

from __future__ import annotations

from pathlib import Path

from plugarr.layout import hardlink_supported


def test_le_controle_ne_laisse_aucun_dossier(tmp_path):
    """Le coeur du correctif."""
    racine = tmp_path / "jamais-vu" / "data"

    ok, _detail = hardlink_supported(racine)

    assert ok, "le controle doit toujours faire son travail"
    assert not racine.exists(), "DATA_ROOT a survecu au controle"
    assert not (tmp_path / "jamais-vu").exists(), "les parents aussi ont ete crees"


def test_toute_la_chaine_de_parents_est_reprise(tmp_path):
    """`parents=True` cree toute la chaine : la rendre entiere, ou rien."""
    racine = tmp_path / "a" / "b" / "c" / "d" / "data"

    hardlink_supported(racine)

    assert list(tmp_path.iterdir()) == []


def test_un_dossier_deja_la_n_est_jamais_touche(tmp_path):
    """La garantie qui compte : une installation existante ne doit rien perdre.

    `rmdir` refuse un dossier non vide — c'est ce refus qui protege. Mais un
    dossier VIDE qui existait avant nous ne nous appartient pas davantage.
    """
    racine = tmp_path / "data"
    (racine / "torrents").mkdir(parents=True)
    (racine / "media").mkdir(parents=True)

    hardlink_supported(racine)

    assert (racine / "torrents").is_dir(), "un dossier prealable a ete supprime"
    assert (racine / "media").is_dir()


def test_le_contenu_d_une_installation_survit(tmp_path):
    """Si quelque chose vit dedans, `rmdir` echoue et on n'insiste pas."""
    racine = tmp_path / "data"
    (racine / "torrents").mkdir(parents=True)
    (racine / "media").mkdir(parents=True)
    temoin = racine / "media" / "un-film.mkv"
    temoin.write_text("pas un vrai film")

    hardlink_supported(racine)

    assert temoin.exists(), "le controle a emporte du contenu"


def test_le_menage_passe_meme_quand_la_creation_echoue(tmp_path, monkeypatch):
    """Un `mkdir` qui casse a mi-chemin a pu creer une partie de la chaine.

    Le cas macOS exactement : `torrents` passe, `media` echoue — ou l'inverse.
    Sans le `finally`, le premier restait.
    """
    racine = tmp_path / "jamais-vu" / "data"
    vrai_mkdir = Path.mkdir
    appels = {"n": 0}

    def mkdir_capricieux(self, *args, **kwargs):
        appels["n"] += 1
        if appels["n"] >= 2:
            raise OSError(30, "Read-only file system")
        return vrai_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir_capricieux)

    ok, _detail = hardlink_supported(racine)

    assert not ok
    assert not (tmp_path / "jamais-vu").exists(), "la creation partielle est restee"


def test_le_verdict_reste_le_meme(tmp_path):
    """Le menage ne doit pas changer ce que le controle REPOND : c'est un
    diagnostic, et il vaut toujours 40 Go de recopie evites."""
    ok, detail = hardlink_supported(tmp_path / "data")

    assert ok
    assert "hardlink" in detail.lower()
