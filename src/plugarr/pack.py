"""Mise a jour du pack : aligner une installation ancienne sur cette version.

`plugarr` sait dire qu'une image a une version plus recente et l'appliquer,
service par service. Il ne savait pas mettre a jour **sa propre installation**
quand c'est PlugArr qui change : quelqu'un qui a installe il y a six mois et
telecharge le binaire du jour n'avait aucune commande a lancer.

Ce module calcule l'ecart entre ce qu'une installation porte et ce que le
catalogue de cette version epingle, puis le decrit. Il n'ecrit rien : c'est
`cli.upgrade` qui decide, apres avoir montre.

**Une regle qui prime sur le reste : on ne redescend jamais.** Le tag deploye
vit dans `stack.yml` et non dans le code, precisement pour que quelqu'un
puisse mettre Sonarr a jour sans attendre une version de PlugArr, ou rester
delibrement sur une version ancienne. Un `upgrade` qui ramenerait tout au
catalogue annulerait ce choix sans le dire. On ne propose donc que ce qui
AVANCE, et la comparaison se fait sur des numeros de version, pas sur des
chaines : `4.9.5` vient avant `4.16.1`, ce que l'ordre alphabetique inverse.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import catalog, imageref, updates
from .i18n import t
from .models import StackConfig


@dataclass
class Ecart:
    """Un service dont l'image installee differe de celle du catalogue."""

    service: str
    installee: str
    catalogue: str

    @property
    def tag_installe(self) -> str:
        return imageref.tag(self.installee)

    @property
    def tag_catalogue(self) -> str:
        return imageref.tag(self.catalogue)

    @property
    def meme_tag(self) -> bool:
        """Meme version, digest different : le catalogue a re-epingle la meme
        version sur une image reconstruite en amont."""
        return self.tag_installe == self.tag_catalogue


def ecarts(cfg: StackConfig) -> tuple[list[Ecart], list[str]]:
    """Ce que le catalogue de cette version propose de plus que l'installation.

    Renvoie les ecarts retenus et les services ECARTES avec leur raison. Les
    seconds comptent autant que les premiers : un `upgrade` qui saute
    silencieusement un service donne l'impression d'avoir tout aligne.
    """
    retenus: list[Ecart] = []
    ecartes: list[str] = []

    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        if cfg.services[sid].adopted:
            ecartes.append(t("{service} : service adopte, mise a jour externe", service=sid))
            continue
        installee = cfg.services[sid].image
        referme = catalog.get(sid).image
        if not installee or installee == referme:
            continue

        ecart = Ecart(sid, installee, referme)
        if ecart.meme_tag:
            # Meme version, digest different. Rien a decider : c'est le meme
            # logiciel, re-epingle.
            retenus.append(ecart)
            continue

        pose = updates.parse_version(ecart.tag_installe)
        propose = updates.parse_version(ecart.tag_catalogue)
        if pose is None or propose is None:
            ecartes.append(
                t(
                    "{service} : {installee} et {catalogue} ne se comparent pas",
                    service=sid,
                    installee=ecart.tag_installe,
                    catalogue=ecart.tag_catalogue,
                )
            )
            continue
        if propose <= pose:
            # Le cas courant d'un utilisateur qui a mis a jour lui-meme, et le
            # seul ou aligner serait une REGRESSION.
            ecartes.append(
                t(
                    "{service} : {installee} est deja plus recent que {catalogue}",
                    service=sid,
                    installee=ecart.tag_installe,
                    catalogue=ecart.tag_catalogue,
                )
            )
            continue
        retenus.append(ecart)

    return retenus, ecartes


def appliquer(cfg: StackConfig, choisis: list[Ecart]) -> list[str]:
    """Pose les images retenues dans la configuration EN MEMOIRE.

    L'ecriture de `stack.yml` et du compose reste a l'appelant : c'est lui qui
    sait s'il est en `--dry-run`, et une fonction qui calcule ne doit pas
    ecrire par surprise.
    """
    poses = []
    for ecart in choisis:
        cfg.services[ecart.service].image = ecart.catalogue
        poses.append(ecart.service)
    return poses
