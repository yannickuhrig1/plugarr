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
