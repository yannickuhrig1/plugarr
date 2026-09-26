"""Langue de PlugArr lui-meme, a ne pas confondre avec celle des services.

Deux reglages distincts vivent dans ce projet, et les melanger serait une
erreur d'usage :

- **la langue de PlugArr** : celle de l'assistant, de la ligne de commande, du
  rapport et de la page d'acces. C'est ce module ;
- **la langue des services** : celle que Sonarr, Radarr, Prowlarr, Jellyfin et
  Silo afficheront dans LEUR interface. C'est `langues.py`, livre en 0.1.11.

Quelqu'un peut vouloir PlugArr en anglais et sa mediatheque en francais, ou
l'inverse. Le second retombe sur le premier tant qu'on n'en decide pas
autrement, ce qui est le cas courant, mais les deux restent separes.

**La cle de traduction est la phrase francaise elle-meme.** C'est delibere :
inventer des cles (`ecran.accueil.titre`) ajoute un dictionnaire a tenir, et
une cle mal orthographiee s'affiche telle quelle a l'utilisateur. Ici une
phrase absente du catalogue retombe sur le francais, qui est au pire
comprehensible plutot que cryptique.

Le garde-fou est dans les tests : `test_traduction.py` releve tous les appels
a `t("...")` dans le code et **echoue si l'un d'eux n'a pas d'entree
anglaise**. Sans lui, une phrase ajoutee en francais resterait francaise en
anglais sans que personne ne le voie avant un utilisateur.
"""

from __future__ import annotations

import locale
import os

from .traductions import EN

#: Les langues dans lesquelles PlugArr lui-meme existe. Ce n'est pas la meme
#: liste que `langues.PROPOSEES`, qui dit ce que les SERVICES acceptent.
DISPONIBLES: tuple[tuple[str, str], ...] = (
    ("fr", "Francais"),
    ("en", "English"),
)

_CATALOGUES = {"en": EN}

_langue = "fr"


def langue() -> str:
    """Langue courante de PlugArr."""
    return _langue


def utiliser(code: str | None) -> str:
    """Fixe la langue de PlugArr. Renvoie celle reellement retenue.

    Une langue inconnue ne leve pas : elle retombe sur le francais. Un
    assistant qui refuse de demarrer parce qu'une variable d'environnement
    contient `LANG=C.UTF-8` serait insupportable.
    """
    global _langue
    code = (code or "").strip().lower()[:2]
    _langue = code if code in dict(DISPONIBLES) else "fr"
    return _langue


def langue_du_systeme() -> str:
    """Langue deduite de l'environnement, pour le premier demarrage.

    Un francophone doit trouver PlugArr en francais sans rien regler, et tout
    le monde d'autre en anglais : c'est la valeur par defaut la plus utile
    pour un projet qui vise les deux publics.

    `LANG` et `LC_ALL` sont lus avant `locale`, parce qu'ils sont explicites
    la ou `getlocale()` renvoie sous Windows un nom de region traduit
    (« French_France ») qui ne ressemble a aucun code ISO.
    """
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        valeur = os.environ.get(variable, "")
        if valeur:
            code = valeur.split(".")[0].split("_")[0].strip().lower()
            if code in dict(DISPONIBLES):
                return code
    try:
        systeme = locale.getlocale()[0] or ""
    except ValueError:  # pragma: no cover - depend de la machine
        systeme = ""
    systeme = systeme.lower()
    if systeme.startswith(("fr", "french")):
        return "fr"
    if systeme.startswith(("en", "english")):
        return "en"
    return "fr"


def t(texte: str, /, **valeurs: object) -> str:
    """Traduit une phrase, puis y insere les valeurs nommees.

    Le formatage se fait APRES la traduction, sans quoi la cle de recherche
    contiendrait deja les valeurs et ne correspondrait jamais au catalogue.
    """
    return traduire(texte, _langue, **valeurs)


def traduire(texte: str, code: str, /, **valeurs: object) -> str:
    """Comme `t`, dans une langue donnee, sans toucher a la langue courante.

    L'assistant web en a besoin : la langue y est choisie DANS la page, et
    peut changer a tout moment, pendant qu'une installation tourne dans un
    autre fil. Basculer la langue du processus pour traduire une phrase
    changerait celle de tout ce que ce fil ecrit au meme instant.
    """
    traduit = _CATALOGUES.get(code, {}).get(texte, texte)
    if not valeurs:
        return traduit
    try:
        return traduit.format(**valeurs)
    except (KeyError, IndexError):
        # Une traduction dont les champs ne correspondent pas ne doit pas
        # faire tomber l'assistant : on rend le francais, qui lui est bon.
        return texte.format(**valeurs)


def bilingue(texte: str, /, **valeurs: object) -> dict[str, str]:
    """La meme phrase dans chaque langue de PlugArr, pour qu'une page choisisse."""
    return {code: traduire(texte, code, **valeurs) for code, _ in DISPONIBLES}


def phrase(texte: str, /) -> str:
    """Marque une phrase a traduire plus tard, sans la traduire maintenant.

    Rend le texte tel quel. Son seul role est d'etre vu par
    `scripts/audit_traductions.py` : une phrase qui ne passe par `t` qu'au
    moment de l'affichage, dans une autre fonction, echapperait sinon au
    controle et resterait francaise en anglais.
    """
    return texte
