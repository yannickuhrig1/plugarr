"""Le coffre ne garde que sur demande, et ne garde rien en clair."""

from __future__ import annotations

import sys

import pytest

from plugarr import coffre

windows = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI n'existe que sous Windows")


@windows
def test_un_secret_garde_se_relit_et_n_apparait_pas_en_clair():
    coffre.garder("ssh-0123456789ab", {"password": "MotDePasse-accentue-e", "sudo_password": "s"})

    brut = coffre._fichier("ssh-0123456789ab").read_bytes()
    assert b"MotDePasse" not in brut
    assert coffre.lire("ssh-0123456789ab") == {
        "password": "MotDePasse-accentue-e",
        "sudo_password": "s",
    }


@windows
def test_une_grande_cle_privee_tient_dans_le_coffre():
    """Le Gestionnaire d'identifiants plafonne a 2 560 octets : une cle RSA
    4 096 bits en PEM fait plus de 3 000. C'est la raison de DPAPI."""
    cle = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + "A" * 3300 + "\n-----END-----\n"
    coffre.garder("ssh-0123456789ab", {"private_key": cle})

    assert coffre.lire("ssh-0123456789ab")["private_key"] == cle


@windows
def test_seuls_les_champs_connus_sont_gardes():
    coffre.garder("ssh-0123456789ab", {"password": "x", "cle_api_sonarr": "fuite"})

    assert coffre.lire("ssh-0123456789ab") == {"password": "x"}


@windows
def test_un_fichier_abime_vaut_rien_de_garde():
    coffre.garder("ssh-0123456789ab", {"password": "x"})
    coffre._fichier("ssh-0123456789ab").write_bytes(b"pas du DPAPI")

    assert coffre.lire("ssh-0123456789ab") == {}


def test_oublier_efface_le_fichier():
    if coffre.disponible():
        coffre.garder("ssh-0123456789ab", {"password": "x"})
    coffre.oublier("ssh-0123456789ab")

    assert not coffre.garde("ssh-0123456789ab")
    assert coffre.lire("ssh-0123456789ab") == {}


def test_un_identifiant_hors_format_est_refuse():
    """Il compose un nom de fichier : pas de separateur, pas de remontee."""
    with pytest.raises(ValueError):
        coffre._fichier("../../ailleurs")
    assert not coffre.garde("../../ailleurs")


@pytest.mark.skipif(sys.platform == "win32", reason="hors Windows seulement")
def test_hors_windows_le_coffre_refuse_plutot_que_d_ecrire_en_clair():
    with pytest.raises(coffre.CoffreIndisponible):
        coffre.garder("ssh-0123456789ab", {"password": "x"})
