"""Les captures ne doivent bouger que quand l'INTERFACE bouge.

Elles portaient le numero de version dans leur bandeau, parce que le produit
l'affiche sur chaque ecran — et il a de bonnes raisons de le faire : c'est la
premiere chose a demander quand quelqu'un signale un probleme.

Mais dans une capture, ce numero ne documente rien et coute cher. La seule
0.7.2 faisait bouger 18 fichiers et 1609 lignes de SVG sans qu'un pixel
d'interface ait change. La CI comparant les captures a celles du depot, chaque
version obligeait a les regenerer et a relire un diff entierement faux — le
genre de diff qu'on finit par approuver sans regarder, et c'est la que se cache
le vrai changement le jour ou il arrive.

`freeze_environment()` le retire donc des captures, et de la seulement. Ce test
verifie que ca tient : un `# type: ignore` retire par megarde, un bandeau
reecrit, et le numero reviendrait sans que rien ne le signale.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CAPTURES = Path(__file__).resolve().parent.parent / "docs" / "screenshots"

#: `&#160;` : les SVG de Rich ecrivent les espaces en insecables.
BANDEAU_VERSIONNE = re.compile(r"plugarr(?:&#160;|\s)+\d+\.\d+\.\d+")


def _svgs() -> list[Path]:
    return sorted(CAPTURES.rglob("*.svg"))


def test_il_y_a_bien_des_captures_a_controler():
    """Sans ce garde-fou, le test ci-dessous passerait sur zero fichier."""
    assert len(_svgs()) >= 10


@pytest.mark.parametrize("capture", _svgs(), ids=lambda p: p.name)
def test_aucune_capture_ne_porte_le_numero_de_version(capture):
    trouve = BANDEAU_VERSIONNE.search(capture.read_text(encoding="utf-8"))

    assert trouve is None, (
        f"{capture.relative_to(CAPTURES)} porte « {trouve.group() if trouve else ''} » : "
        "chaque publication fera de nouveau bouger toutes les captures. "
        "Voir freeze_environment() dans scripts/screenshots.py."
    )


#: Ce que la machine qui produit les captures ne doit JAMAIS y laisser passer.
#: Chacun a ete constate, pas imagine : la 0.8.0 a publie deux SVG portant
#: « C:\Users\darkl\Downloads », parce que l'assistant avait retrouve une vraie
#: installation dans le registre du poste.
#: `&#160;` : les SVG de Rich ecrivent les espaces en insecables, comme pour
#: `BANDEAU_VERSIONNE` ci-dessus. Un motif qui cherche une espace ordinaire ne
#: trouve donc rien — premiere version de ce test, qui laissait tout passer.
SEP = r"(?:&#160;|\s)+"

FUITES = (
    ("un chemin Windows local", re.compile(r"C:[\\/]Users[\\/]", re.IGNORECASE)),
    ("un dossier personnel Unix", re.compile(r"/home/(?!runner\b)[a-z]")),
    ("une reprise d'installation", re.compile("installation" + SEP + "precedente", re.IGNORECASE)),
)


@pytest.mark.parametrize("capture", _svgs(), ids=lambda p: p.name)
def test_aucune_capture_ne_porte_de_trace_de_la_machine(capture):
    """Une capture doit documenter l'INTERFACE, pas le poste qui l'a produite.

    Deux consequences, et la premiere est la plus genante : le chemin local de
    quelqu'un est parti dans un depot public. La seconde est mecanique — la CI
    regenere les captures et les compare a celles du depot, donc une capture qui
    depend de la machine fait echouer la CI sans qu'un pixel d'interface ait
    bouge. Voir `freeze_environment()` dans scripts/screenshots.py.
    """
    contenu = capture.read_text(encoding="utf-8")
    for quoi, motif in FUITES:
        trouve = motif.search(contenu)
        assert trouve is None, (
            f"{capture.relative_to(CAPTURES)} porte {quoi} "
            f"(« {trouve.group() if trouve else ''} ») : la capture depend de la "
            "machine qui l'a produite."
        )
