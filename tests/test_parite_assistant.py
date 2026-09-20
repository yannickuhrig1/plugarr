"""L'assistant doit couvrir tout ce que la ligne de commande sait faire.

Signale a l'usage : « pourquoi tout n'est pas dans l'assistant ? ». Sept options
`--vpn*` et `--host` n'existaient qu'en ligne de commande, et le recapitulatif
avertissait qu'aucun VPN n'etait configure sans offrir le moindre moyen d'en
mettre un. Ce test empeche l'ecart de se reformer sans qu'on le decide.
"""

from __future__ import annotations

import inspect

from plugarr.cli import install, wizard

#: Options qui decident du LANCEMENT et non de la stack. Elles vivent sur la
#: commande `wizard` elle-meme, pas dans un ecran : demander « voulez-vous une
#: confirmation ? » a quelqu'un qui vient de cliquer n'aurait aucun sens.
LANCEMENT = {"project_dir", "open_page"}

#: Options sans equivalent possible dans un assistant interactif : il montre
#: deja son recapitulatif avant d'agir, ce qui est exactement `--dry-run` suivi
#: d'un `--yes`.
SANS_OBJET = {"dry_run", "yes"}

#: Ou chaque option d'`install` se pose dans l'assistant. Le nom est celui de
#: l'ecran, pour que l'echec dise ou aller regarder.
COUVERTES = {
    "reprendre": "SummaryScreen",
    "services": "ServicesScreen",
    "config_root": "PathsScreen",
    "data_root": "PathsScreen",
    "platform": "PathsScreen",
    "host": "PathsScreen",
    "username": "PathsScreen",
    "project_name": "PathsScreen",
    "language": "PathsScreen",
    "timezone": "PathsScreen",
    "vpn": "VpnScreen",
    "vpn_provider": "VpnScreen",
    "vpn_type": "VpnScreen",
    "vpn_user": "VpnScreen",
    "vpn_pass": "VpnScreen",
    "vpn_key": "VpnScreen",
    "vpn_countries": "VpnScreen",
    "sabnzbd_vpn": "VpnScreen",
    "client_prefere": "VpnScreen",
    "qbittorrent_ui": "VpnScreen",
    "veille": "PathsScreen",
    "veille_port": "PathsScreen",
    "recyclarr_sonarr": "TemplatesScreen",
    "recyclarr_radarr": "TemplatesScreen",
    "reset_config": "ExistingConfigScreen",
}


def test_aucune_option_d_install_n_echappe_a_l_assistant():
    options = set(inspect.signature(install).parameters)
    orphelines = options - set(COUVERTES) - LANCEMENT - SANS_OBJET
    assert not orphelines, (
        f"options reservees a la ligne de commande : {sorted(orphelines)}. "
        "Ajoutez-leur un ecran, ou classez-les dans LANCEMENT / SANS_OBJET "
        "en disant pourquoi."
    )


def test_les_options_de_lancement_sont_sur_la_commande_wizard():
    """Sans elles, `plugarr wizard` ecrivait toujours dans le repertoire courant
    et ouvrait toujours un navigateur."""
    assert LANCEMENT <= set(inspect.signature(wizard).parameters)


def test_le_tableau_ne_cite_que_des_options_reelles():
    """Un renommage dans `install` doit faire echouer ce test, pas passer."""
    options = set(inspect.signature(install).parameters)
    assert set(COUVERTES) <= options
    assert LANCEMENT | SANS_OBJET <= options
