"""Releve toutes les phrases affichables et les compare au catalogue anglais.

Meme role que `audit_indexers.py` et `audit_templates.py` : un controle
mecanique de quelque chose qu'aucune relecture ne verifie de facon fiable.

Une phrase ajoutee en francais et oubliee dans le catalogue s'afficherait en
francais a un utilisateur anglophone, sans erreur, sans avertissement, et sans
que rien ne le signale avant qu'il ne la voie.

Deux sources sont relevees, parce que le projet traduit de deux facons :

- les appels directs a `t("...")` ;
- les litteraux passes aux widgets de `tui/widgets.py`, qui traduisent au
  passage. Les ecrans ecrivent leurs phrases en francais et en clair ; c'est
  ici qu'on verifie qu'elles ont toutes leur equivalent.

    python scripts/audit_traductions.py             # liste ce qui manque
    python scripts/audit_traductions.py --squelette # sortie collable

Sort non nul s'il manque une entree, ou si le catalogue en porte une morte.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "src" / "plugarr"

sys.path.insert(0, str(RACINE / "src"))

#: Widgets qui traduisent leur premier argument. La liste doit suivre
#: `tui/widgets.py` : un test le verifie, pour qu'un widget ajoute la-bas ne
#: sorte pas du controle en silence.
WIDGETS_TRADUISANTS = ("Button", "Label", "Static", "Checkbox", "RadioButton", "DataTable")

#: Methodes dont le premier argument est une phrase. `update` pose le texte
#: d'un widget deja monte ; `print` est celui de la console traduisante de
#: `report.py`, qui joue le meme role pour la ligne de commande.
METHODES_TRADUISANTES = ("update", "print")

#: Ce qui ressemble a une phrase mais n'en est pas. Les identifiants et les
#: classes CSS passent par des mots-cles (`id=`, `classes=`), donc jamais par
#: le premier argument positionnel : il n'y a rien a exclure de ce cote.
IGNOREES = ("",)


def _est_phrase(valeur: str) -> bool:
    return bool(valeur.strip()) and valeur not in IGNOREES


def phrases() -> dict[str, list[str]]:
    """Phrases traduisibles trouvees dans le code, par fichier."""
    trouvees: dict[str, list[str]] = {}

    def retenir(fichier: Path, valeur: str) -> None:
        if _est_phrase(valeur):
            trouvees.setdefault(str(fichier.relative_to(RACINE)).replace("\\", "/"), []).append(valeur)

    for fichier in sorted(SOURCES.rglob("*.py")):
        if fichier.name in ("widgets.py", "i18n.py", "traductions.py"):
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call) or not noeud.args:
                continue
            fonction = noeud.func
            nom = getattr(fonction, "id", None) or getattr(fonction, "attr", None)
            premier = noeud.args[0]
            interessant = nom == "t" or nom in WIDGETS_TRADUISANTS or (
                isinstance(fonction, ast.Attribute) and nom in METHODES_TRADUISANTES
            )
            if not interessant:
                continue
            if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                retenir(fichier, premier.value)
            elif nom == "DataTable":
                continue
        # Les attributs de classe qui sont des cles : le sous-titre de chaque
        # ecran, traduit par `WizardScreen.compose`, et les titres de categorie.
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    nom_cible = getattr(cible, "id", None)
                    if nom_cible in (
                        "SUB_TITLE",
                        "IDS_EXPLICATION",
                        "_SILO_AVERTISSEMENT",
                        "_GITIGNORE_ENTETE",
                    ) and isinstance(
                        noeud.value, ast.Constant
                    ):
                        retenir(fichier, str(noeud.value.value))
                    elif nom_cible in ("CATEGORY_TITLES", "_ROTATIONS") and isinstance(
                        noeud.value, ast.Dict
                    ):
                        # Les libelles vivent dans les valeurs : directement pour
                        # les titres de categorie, dans un couple pour les
                        # infobulles de rotation.
                        for valeur in noeud.value.values:
                            elements = (
                                valeur.elts if isinstance(valeur, ast.Tuple) else [valeur]
                            )
                            for element in elements:
                                if isinstance(element, ast.Constant) and isinstance(
                                    element.value, str
                                ):
                                    retenir(fichier, element.value)

        # `_REGLAGES` est un tuple de couples (champ, libelle) : seul le
        # SECOND element est une phrase.
        for noeud in ast.walk(arbre):
            # `_REGLAGES` porte une annotation de type : c'est donc un
            # `AnnAssign` et non un `Assign`. Les deux formes sont acceptees,
            # sinon la constante sort du controle selon qu'elle est annotee.
            cibles = (
                noeud.targets
                if isinstance(noeud, ast.Assign)
                else [noeud.target]
                if isinstance(noeud, ast.AnnAssign)
                else []
            )
            if any(getattr(cible, "id", None) == "_REGLAGES" for cible in cibles):
                for couple in getattr(noeud.value, "elts", []):
                    elements = getattr(couple, "elts", [])
                    if len(elements) == 2 and isinstance(elements[1], ast.Constant):
                        retenir(fichier, str(elements[1].value))

        # `resolve_ids` rend trois origines de plus, construites dans son corps
        # plutot que declarees : elles finissent affichees sous le profil de
        # plateforme, au meme titre que les autres.
        if fichier.name == "layout.py":
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Return) and isinstance(noeud.value, ast.Tuple):
                    for element in noeud.value.elts:
                        if isinstance(element, ast.Constant) and isinstance(
                            element.value, str
                        ):
                            retenir(fichier, element.value)

        # Phrases portees par des mots-cles plutot que par un appel de widget :
        # les notes du catalogue, affichees sous chaque service a la selection,
        # l'origine des PUID/PGID et la note d'un profil de plateforme, toutes
        # deux affichees sous le choix de profil. Elles arrivent aux widgets par
        # une variable : seul leur point de DECLARATION est un litteral.
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            for mot_cle in noeud.keywords:
                if (
                    mot_cle.arg in ("notes", "source", "note")
                    and isinstance(mot_cle.value, ast.Constant)
                    and isinstance(mot_cle.value.value, str)
                ):
                    retenir(fichier, mot_cle.value.value)

        # `add_columns` prend PLUSIEURS phrases, toutes positionnelles.
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Call)
                and getattr(noeud.func, "attr", None) == "add_columns"
            ):
                for argument in noeud.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        retenir(fichier, argument.value)
    return trouvees


def main() -> int:
    from plugarr.traductions import EN

    par_fichier = phrases()
    toutes = {phrase for liste in par_fichier.values() for phrase in liste}
    manquantes = sorted(toutes - set(EN))
    mortes = sorted(set(EN) - toutes)

    print(f"{len(toutes)} phrases traduisibles, {len(EN)} entrees anglaises")

    if "--squelette" in sys.argv:
        for phrase in manquantes:
            print(f"    {phrase!r}: {phrase!r},")
        return 0

    for fichier, liste in par_fichier.items():
        absentes = sorted({p for p in liste if p not in EN})
        if absentes:
            print(f"\n{fichier} : {len(absentes)} sans traduction")
            for phrase in absentes[:12]:
                print(f"  - {phrase[:88]}")

    if mortes:
        print(f"\n{len(mortes)} entrees anglaises ne correspondent a aucune phrase du code :")
        for phrase in mortes[:12]:
            print(f"  - {phrase[:88]}")

    if manquantes or mortes:
        print(f"\nECHEC : {len(manquantes)} sans traduction, {len(mortes)} entrees mortes.")
        return 1
    print("\nOK : chaque phrase a son entree anglaise, et aucune de trop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
