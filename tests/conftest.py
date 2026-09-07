"""Outils partages par les tests de l'assistant.

`appuyer` existe pour une raison precise : quatre tests differents ont echoue,
chacun une fois sur plusieurs dizaines, toujours de la meme facon.

    screen.query_one("#next", Button).press()
    await pilot.pause()
    assert pilot.app.username == "yannick"

`press()` ne fait qu'ENVOYER un message. Une passe d'evenements suffit
d'ordinaire, mais pas quand la machine est chargee — et une suite de 580 tests
charge la machine. Compter les passes revient a parier sur une duree.

On attend donc le RESULTAT. Le test dit ce qu'il attend, et n'a plus a deviner
combien de tours de boucle cela demande.

Ce sont des FIXTURES et non des fonctions importables : `tests/` n'est pas sur
le chemin d'import, et pytest decouvre les fixtures d'un conftest sans qu'on ait
rien a importer.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from textual.widgets import Button

#: 60 passes : largement au-dela de ce qu'il faut, et sans consequence quand la
#: condition est vraie tout de suite — la boucle sort a la premiere.
PASSES_MAX = 60


@pytest.fixture
def appuyer():
    """Appuie sur un bouton, puis attend que la condition soit vraie.

    Renvoie False si elle ne l'est jamais : le test echoue alors sur SON
    assertion, avec son propre message, pas sur un delai depasse.
    """

    async def _appuyer(pilot, selecteur: str, jusqu_a: Callable[[], bool]) -> bool:
        pilot.app.screen.query_one(selecteur, Button).press()
        for _ in range(PASSES_MAX):
            await pilot.pause()
            if jusqu_a():
                return True
        return False

    return _appuyer


@pytest.fixture
def attendre():
    """Meme chose sans appui : pour ce qu'un worker met a jour en arriere-plan."""

    async def _attendre(pilot, jusqu_a: Callable[[], bool]) -> bool:
        for _ in range(PASSES_MAX):
            await pilot.pause()
            if jusqu_a():
                return True
        return False

    return _attendre


@pytest.fixture(autouse=True)
def _registre_isole(tmp_path_factory, monkeypatch):
    """Le registre des installations vit hors du depot : il ne doit pas fuir ici.

    `compose.write_artifacts` note chaque installation dans le dossier PlugArr
    de l'utilisateur, et `reprise.trouver` l'y relit. Sans isolation, une suite
    de tests ecrirait dans le registre REEL de la machine, puis y retrouverait
    l'installation d'un autre test — voire celle de l'utilisateur.
    """
    monkeypatch.setenv("PLUGARR_HOME", str(tmp_path_factory.mktemp("plugarr-home")))


@pytest.fixture(autouse=True)
def _francais_par_defaut():
    """La suite est ecrite en francais : la langue ne doit pas venir de la machine.

    PlugArr suit `LANG` au demarrage, ce qui est le bon comportement pour un
    utilisateur et le mauvais pour une suite de tests : sur un poste en
    `en_US`, PlugArr rend l'anglais et **67 tests echouent** en cherchant des
    phrases francaises. Mesure sur un LXC Debian ; la CI, elle, ne le voyait
    pas, sa locale etant vide et le repli valant deja le francais.

    Un test qui verifie une phrase doit obtenir la meme reponse partout. Ceux
    qui portent SUR la langue posent la leur explicitement et restent maitres
    d'eux-memes.
    """
    from plugarr import i18n

    avant = i18n.langue()
    i18n.utiliser("fr")
    yield
    i18n.utiliser(avant)
