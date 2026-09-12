"""Controle de l'executable : l'assistant vit-il vraiment dedans ?

Compile en un second executable jetable, puis lance. C'est le seul moyen de
verifier ce qui casse le plus facilement a l'empaquetage : un fichier non-Python
absent de l'archive.

Deux cas rencontres pour de vrai :

- `app.tcss` manquant : Textual leve `StylesheetError` et l'assistant ne s'ouvre
  pas du tout. Panne bruyante, mais invisible tant que personne ne lance
  l'executable produit ;
- `data/vpn_countries.json` manquant en 0.1.8 : l'assistant s'ouvrait
  parfaitement, affichait ses services, et plantait plus loin — sur l'ecran
  VPN, c'est-a-dire des qu'un client de telechargement etait coche. Ce controle
  s'arretait a l'ecran des services : il ne voyait rien.

D'ou la regle : ce controle doit PARCOURIR l'assistant, pas seulement l'ouvrir.

Les modules importes tardivement — `clients/silo.py` ne l'est qu'au fond d'une
etape de cablage — ne se verifient PAS ici : cet executable est construit a
part, et ce qu'il embarque ne dit rien de ce qu'embarque `plugarr.exe`. Cette
verification-la se fait sur le vrai binaire, dans le workflow.

Sortie non nulle si l'assistant ne se rend pas correctement.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import sys

#: En dessous, la feuille de style n'a pas ete chargee.
MIN_REGLES = 50


async def probe() -> int:
    from textual.widgets import Button, RadioButton, Select, SelectionList

    from plugarr import catalog
    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import PathsScreen, ServicesScreen, VpnScreen

    app = PlugArrApp()
    app.auto_open_page = False
    lieux = -1
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        regles = len(app.stylesheet.rules)
        app.push_screen(ServicesScreen())
        await pilot.pause()
        cases = len(app.screen.query("Checkbox"))

        # Jusqu'a l'ecran VPN, en passant par les chemins : c'est le trajet
        # reel, et celui qui a plante en 0.1.8.
        app.selection = ["sonarr", "qbittorrent"]
        app.push_screen(PathsScreen())
        await pilot.pause()
        langues_proposees = len(app.screen.query_one("#langue", Select)._options)
        app.screen.query_one("#next", Button).press()
        await pilot.pause()
        atteint = type(app.screen).__name__
        if isinstance(app.screen, VpnScreen):
            app.screen.query_one("#vpn-oui", RadioButton).value = True
            await pilot.pause()
            lieux = len(app.screen.query_one("#vpn-lieux", SelectionList)._options)

    choisissables = len(list(catalog.selectable()))
    print(f"  feuille de style : {regles} regles")
    print(f"  services affiches : {cases} / {choisissables}")
    print(f"  ecran apres les chemins : {atteint}")
    print(f"  langues proposees : {langues_proposees}")
    print(f"  lieux VPN proposes : {lieux}")

    problemes = []
    if regles < MIN_REGLES:
        problemes.append(f"feuille de style absente ou vide ({regles} regles)")
    if cases != choisissables:
        # `CATALOG` contient aussi la base et le cache de Silo, tires comme
        # prerequis et jamais coches : c'est `selectable()` qui fait foi.
        problemes.append(f"{cases} services affiches au lieu de {choisissables}")
    if langues_proposees <= 1:
        problemes.append("le choix de la langue est vide ou absent")
    if atteint != "VpnScreen":
        problemes.append(f"l'ecran VPN n'est pas atteint ({atteint})")
    elif lieux <= 0:
        problemes.append("aucun lieu VPN propose : data/vpn_countries.json est-il embarque ?")

    for probleme in problemes:
        print(f"  ECHEC : {probleme}")
    if not problemes:
        print("  OK : l'assistant se rend correctement depuis l'executable")
    return 1 if problemes else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(asyncio.run(probe()))
