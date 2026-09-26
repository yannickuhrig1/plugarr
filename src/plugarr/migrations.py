"""Lecture versionnee de `stack.yml`.

`StackConfig` porte un champ `version` depuis la premiere ligne du projet, et
**rien ne le lisait** — aucune occurrence dans le code. Ce module le lit enfin,
et repare au passage un chemin de perte de donnees mesure plutot que suppose.

**Le probleme, en une experience.** On ecrit un `stack.yml` marque
`version: 2`, portant un champ qu'une version future aurait ajoute, et on le
donne a lire a la version courante :

    version lue          : 2
    champ futur garde ?  : False
    champ futur reecrit ?: False

Pydantic ignore les champs qu'il ne connait pas — c'est son comportement par
defaut. La version ancienne lit donc le fichier sans broncher, en jette une
partie, et **la premiere ecriture la detruit definitivement** : `install`,
`generate` et la rotation d'un mot de passe reecrivent tous `stack.yml`.

Le cas se produit des qu'on revient en arriere : on essaie une nouvelle
version, quelque chose deplait, on relance l'ancien binaire. Rien ne signale
la perte.

**Les migrations tournent sur le dictionnaire BRUT**, avant validation. C'est
la seule facon de distinguer « ce champ etait absent » de « ce champ valait sa
valeur par defaut » : apres pydantic, les deux sont identiques, et une
migration qui a besoin de cette difference ne peut plus la voir.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from .i18n import t
from .models import StackConfig

#: Version de schema que cette version de PlugArr sait ecrire. A augmenter
#: UNIQUEMENT en ajoutant une entree a `MIGRATIONS` : le test
#: `test_migrations.py` verifie que les deux avancent ensemble.
#:
#: Ajouter un champ neuf avec une valeur par defaut ne demande PAS de
#: migration — pydantic l'absorbe, et c'est le cas courant. Ce qui en demande
#: une : un champ qui change de sens, de type, ou qui disparait.
VERSION_COURANTE = 7

#: `version depuis` -> transformation du dictionnaire brut. Chaque fonction
#: recoit le contenu du fichier tel qu'il a ete lu et rend la forme attendue
#: par la version suivante. Elle ne doit rien supposer de valide : le fichier
#: peut venir de n'importe quelle version passee.
def _vpn_sabnzbd_explicite(donnees: dict[str, Any]) -> dict[str, Any]:
    """Preserve le trajet SABnzbd des stacks creees avant le choix separe.

    En version 1, ``vpn.enabled`` placait TOUS les clients de telechargement
    derriere Gluetun. Le nouveau defaut direct ne vaut que pour une nouvelle
    installation ; une ancienne stack avec VPN et SABnzbd doit donc recevoir
    la valeur explicite ``True``.
    """
    vpn = donnees.get("vpn")
    services = donnees.get("services")
    if isinstance(vpn, dict) and "protect_sabnzbd" not in vpn:
        vpn = dict(vpn)
        vpn["protect_sabnzbd"] = bool(
            vpn.get("enabled") and isinstance(services, dict) and "sabnzbd" in services
        )
        donnees["vpn"] = vpn
    return donnees


def _client_prefere_introduit(donnees: dict[str, Any]) -> dict[str, Any]:
    """Aucune transformation : `client_prefere` a une valeur par defaut.

    La version avance quand meme. Sans cela, une PlugArr plus ancienne lirait
    ce fichier, ignorerait le champ qu'elle ne connait pas, et le reecrirait
    sans lui : le choix du client prefere disparaitrait en silence. Avec la
    version 3, elle refuse et demande une mise a jour.
    """
    return donnees


def _interface_qbittorrent_introduite(donnees: dict[str, Any]) -> dict[str, Any]:
    """Aucune transformation : `qbittorrent_ui` vaut par defaut l'interface
    d'origine. La version avance pour la meme raison qu'a la 3 : une PlugArr
    plus ancienne effacerait le choix de VueTorrent en reecrivant le fichier."""
    return donnees


def _veille_en_conteneur_introduite(donnees: dict[str, Any]) -> dict[str, Any]:
    """Aucune transformation : la veille en conteneur est desactivee par
    defaut, et le port vaut 7374. La version avance pour la meme raison qu'aux
    precedentes : une PlugArr plus ancienne reecrirait le fichier sans ces
    champs, et la veille disparaitrait du compose au premier `generate`."""
    return donnees


def _console_en_conteneur_introduite(donnees: dict[str, Any]) -> dict[str, Any]:
    """Aucune transformation : la console en conteneur est desactivee par
    defaut. La version avance pour la meme raison qu'aux precedentes : une
    PlugArr plus ancienne reecrirait le fichier sans ces champs."""
    return donnees


def _vue_docker_de_la_veille_introduite(donnees: dict[str, Any]) -> dict[str, Any]:
    """Aucune transformation : la vue Docker de la veille est desactivee par
    defaut. La version avance pour la meme raison qu'aux precedentes."""
    return donnees


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _vpn_sabnzbd_explicite,
    2: _client_prefere_introduit,
    3: _interface_qbittorrent_introduite,
    4: _veille_en_conteneur_introduite,
    5: _console_en_conteneur_introduite,
    6: _vue_docker_de_la_veille_introduite,
}


class VersionFuture(ValueError):
    """`stack.yml` vient d'une version plus recente de PlugArr.

    Continuer detruirait ce qu'on ne sait pas lire, en silence. On s'arrete.
    """


def migrer(donnees: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Amene un `stack.yml` brut a la version courante.

    Renvoie le dictionnaire et le journal de ce qui a ete fait, pour que
    l'appelant puisse le montrer : une migration silencieuse est une migration
    qu'on ne peut pas verifier.
    """
    version = donnees.get("version", 1)
    if not isinstance(version, int):
        # `ValueError` et non `TypeError` : ce n'est pas une erreur de
        # programmation mais un FICHIER dont le contenu ne veut rien dire, et
        # l'appelant le traite comme les autres refus de lecture.
        raise ValueError(  # noqa: TRY004
            t("version de stack.yml illisible : {valeur}", valeur=repr(version))
        )
    if version > VERSION_COURANTE:
        raise VersionFuture(
            t(
                "stack.yml est en version {trouvee}, cette version de PlugArr lit "
                "jusqu'a la {connue}. Mettez PlugArr a jour : continuer effacerait "
                "les reglages qu'il ne sait pas lire.",
                trouvee=version,
                connue=VERSION_COURANTE,
            )
        )

    notes: list[str] = []
    while version < VERSION_COURANTE:
        transformation = MIGRATIONS.get(version)
        if transformation is None:
            raise ValueError(
                t(
                    "aucune migration de la version {depuis} vers la {vers}",
                    depuis=version,
                    vers=version + 1,
                )
            )
        donnees = transformation(dict(donnees))
        version += 1
        donnees["version"] = version
        notes.append(t("stack.yml migre en version {version}", version=version))
    return donnees, notes


def lire(chemin: Path) -> tuple[StackConfig, list[str]]:
    """Lit, migre, puis valide. Renvoie la configuration et le journal.

    L'ordre compte : migrer APRES validation reviendrait a migrer des valeurs
    par defaut inventees par pydantic plutot que le contenu reel du fichier.
    """
    return lire_texte(Path(chemin).read_text(encoding="utf-8"), nom=Path(chemin).name)


def lire_texte(texte: str, *, nom: str = "stack.yml") -> tuple[StackConfig, list[str]]:
    """Comme `lire`, pour un contenu deja en memoire (pile distante lue par SSH)."""
    try:
        donnees = yaml.safe_load(texte) or {}
    except yaml.YAMLError as exc:
        # `yaml.YAMLError` herite d'`Exception`, PAS de `ValueError` : les
        # appelants qui attrapent `(ValueError, OSError)` la laisseraient
        # passer. Meme piege que `zipfile.BadZipFile` en 0.5.2, et meme
        # remede : on convertit ICI, une fois, plutot que dans chaque
        # appelant.
        raise ValueError(
            t("{chemin} est illisible : {erreur}", chemin=nom, erreur=exc)
        ) from exc
    donnees, notes = migrer(donnees)
    return StackConfig.model_validate(donnees), notes
