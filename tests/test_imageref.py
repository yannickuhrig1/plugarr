"""Lecture d'une reference d'image Docker.

`image.rpartition(":")` marchait pour `lscr.io/linuxserver/sonarr:4.0.19` et se
trompait partout ailleurs. Lire correctement tag et digest reste necessaire,
notamment pour la forme Silo `build-N@sha256:…`, et pour ne pas confondre le port
d'un registre avec un tag.
"""

from __future__ import annotations

import pytest

from plugarr import imageref, updates

SHA = "sha256:" + "a" * 64


# ------------------------------------------------------------------ lecture


@pytest.mark.parametrize(
    ("image", "depot", "tag", "digest"),
    [
        ("lscr.io/linuxserver/sonarr:4.0.19", "lscr.io/linuxserver/sonarr", "4.0.19", ""),
        ("redis:alpine", "redis", "alpine", ""),
        ("pgvector/pgvector:pg18", "pgvector/pgvector", "pg18", ""),
        # Sans tag : le depot seul.
        ("getmeili/meilisearch", "getmeili/meilisearch", "", ""),
        # Digest seul : aucune version lisible, mais un contenu immuable.
        (f"ghcr.io/silo-server/silo-server@{SHA}", "ghcr.io/silo-server/silo-server", "", SHA),
        # Tag ET digest : la meilleure forme. Docker retient le digest, le tag
        # reste lisible.
        (f"ghcr.io/wizarrrr/wizarr:2026.9.0@{SHA}", "ghcr.io/wizarrrr/wizarr", "2026.9.0", SHA),
    ],
)
def test_les_formes_courantes_sont_lues(image, depot, tag, digest):
    ref = imageref.parse(image)

    assert (ref.repository, ref.tag, ref.digest) == (depot, tag, digest)


def test_le_port_d_un_registre_n_est_pas_un_tag():
    """`localhost:5000/silo` n'a pas de tag. Un tag ne vit qu'apres le dernier
    `/` — sans cette regle, `rpartition(':')` rendait `5000/silo`."""
    ref = imageref.parse("localhost:5000/silo")

    assert ref.repository == "localhost:5000/silo"
    assert ref.tag == ""


def test_un_registre_avec_port_ET_un_tag():
    ref = imageref.parse("registre.local:5000/silo:v2")

    assert ref.repository == "registre.local:5000/silo"
    assert ref.tag == "v2"


def test_une_forme_incomprise_reste_entiere():
    """La reference vient parfois d'un `stack.yml` ecrit a la main : une
    installation ne doit pas s'arreter parce qu'on n'a pas su la lire."""
    ref = imageref.parse("quelquechose@pasundigest")

    assert ref.repository == "quelquechose@pasundigest"
    assert ref.digest == ""


def test_la_reference_se_reecrit_a_l_identique():
    for image in (
        "redis:alpine",
        f"ghcr.io/silo-server/silo-server@{SHA}",
        f"ghcr.io/wizarrrr/wizarr:2026.9.0@{SHA}",
        "localhost:5000/silo",
    ):
        assert str(imageref.parse(image)) == image


# --------------------------------------------------------------- epinglage


def test_un_digest_est_epingle_un_tag_non():
    assert imageref.parse(f"depot@{SHA}").pinned is True
    assert imageref.parse("depot:1.2.3").pinned is False


@pytest.mark.parametrize("tag", ["latest", "nightly", "dev", "main", ""])
def test_les_tags_qui_bougent_sont_reperes(tag):
    """Ils designent un nom, pas un contenu : demain ce ne sera plus la meme
    image, sans que rien ne l'indique."""
    image = f"depot:{tag}" if tag else "depot"

    assert imageref.parse(image).floating is True


def test_un_tag_qui_bouge_mais_epingle_ne_flotte_plus():
    """C'est exactement ce qu'il faut pour Wizarr : sa version courante n'existe
    que sous `latest`, le digest la fige."""
    assert imageref.parse(f"depot:latest@{SHA}").floating is False


def test_une_version_precise_ne_flotte_pas():
    assert imageref.parse("lscr.io/linuxserver/sonarr:4.0.19").floating is False


# ------------------------------------------------------- changement de tag


def test_changer_de_tag_abandonne_le_digest():
    """Garder l'ancien condensat avec un nouveau tag donnerait une reference qui
    MENT : Docker retient le digest, le tag ne serait qu'un ornement."""
    nouveau = imageref.with_tag(f"lscr.io/linuxserver/sonarr:4.0.19@{SHA}", "4.1.0")

    assert nouveau == "lscr.io/linuxserver/sonarr:4.1.0"
    assert "@" not in nouveau


def test_changer_de_tag_preserve_le_port_du_registre():
    assert imageref.with_tag("registre.local:5000/silo:v1", "v2") == "registre.local:5000/silo:v2"


# ------------------------------------------------ consequences sur les MAJ


def test_une_image_epinglee_n_est_jamais_dite_reconstruite():
    """Un condensat designe un CONTENU : il ne peut pas etre republie. Comparer
    le local au distant revenait a comparer une chose a elle-meme, et la page
    affichait « image reconstruite » sur une image immuable."""
    info = updates.check_service(f"ghcr.io/silo-server/silo-server@{SHA}", check_tags=False)

    assert info.rebuilt is False
    assert info.problems == []


def test_une_image_epinglee_n_affiche_pas_son_condensat_comme_version():
    """`rpartition(':')` rendait les soixante-quatre caracteres du condensat,
    affiches tels quels comme « version » dans la page d'administration."""
    info = updates.check_service(f"ghcr.io/silo-server/silo-server@{SHA}", check_tags=False)

    assert info.current_tag == ""
    assert "a" * 64 not in str(info.current_tag)


def test_sans_tag_comparable_le_probleme_est_dit():
    """Une reference par digest seul ne permet pas de proposer une version."""
    _tags, probleme = updates.newer_tags(f"ghcr.io/silo-server/silo-server@{SHA}")

    assert probleme is not None
    assert "aucun tag" in probleme
