"""Lecture d'une reference d'image Docker.

`image.rpartition(":")` marche pour `lscr.io/linuxserver/sonarr:4.0.19` et se
trompe partout ailleurs. Trois formes le mettent en defaut, et les trois se
presentent pour de vrai :

- **un registre avec un port** : `localhost:5000/silo` n'a pas de tag, mais le
  deux-points du port en fait croire un. La regle est simple : un tag ne peut
  apparaitre qu'APRES le dernier `/` ;
- **un epinglage par digest** : `ghcr.io/silo-server/silo-server@sha256:0627…`
  donnait `current_tag` = les soixante-quatre caracteres du condensat, affiches
  tels quels comme « version » dans la page d'administration ;
- **les deux ensemble** : `depot:2026.9.0@sha256:0627…`. C'est la meilleure
  forme — Docker retient le DIGEST, donc l'installation est reproductible, et le
  tag reste la pour etre lu.

Pourquoi ce module existe maintenant : certaines images ne publient aucun tag
versionne exploitable, et toutes gagnent a etre epinglees par digest. Silo est
maintenant epingle sous la forme `build-522@sha256:…` : le numero de construction
reste comparable, tandis que Docker retient le contenu exact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Un condensat, tel que Docker l'ecrit. L'algorithme n'est pas toujours sha256
#: dans la specification, mais c'est le seul que les registres emettent
#: aujourd'hui ; on accepte donc la forme generale et on ne s'y fie pas.
DIGEST = re.compile(r"^[a-z0-9]+(?:[.+_-][a-z0-9]+)*:[a-fA-F0-9]{32,}$")


@dataclass(frozen=True)
class ImageRef:
    """Une reference decomposee. `repository` ne contient jamais de tag."""

    repository: str
    tag: str = ""
    digest: str = ""

    @property
    def pinned(self) -> bool:
        """Cette reference designe-t-elle un contenu IMMUABLE ?

        Un tag peut etre repousse sur une autre image ; un digest, non. C'est
        toute la difference entre « la meme version » et « le meme contenu ».
        """
        return bool(self.digest)

    @property
    def floating(self) -> bool:
        """Tag connu pour bouger sous les pieds, sans digest pour le retenir."""
        return not self.digest and self.tag in ("latest", "nightly", "dev", "main", "")

    def __str__(self) -> str:
        texte = self.repository
        if self.tag:
            texte += f":{self.tag}"
        if self.digest:
            texte += f"@{self.digest}"
        return texte


def parse(image: str) -> ImageRef:
    """Decompose une reference. Ne leve jamais : une forme inconnue reste entiere.

    Rendre la main sur une chaine incomprise vaut mieux que lever : la reference
    vient parfois d'un `stack.yml` ecrit a la main, et une installation ne doit
    pas s'arreter parce qu'on n'a pas su la lire.
    """
    reste, _, digest = image.partition("@")
    if digest and not DIGEST.match(digest):
        # Un `@` qui n'introduit pas un condensat : on ne comprend pas, on ne
        # touche a rien.
        return ImageRef(repository=image)

    # Un tag ne vit qu'apres le dernier `/`. Sans cette regle, le port d'un
    # registre — `localhost:5000/silo` — passerait pour un tag.
    coupure = reste.rfind("/")
    segment = reste[coupure + 1 :]
    if ":" in segment:
        nom, _, tag = segment.rpartition(":")
        return ImageRef(repository=reste[: coupure + 1] + nom, tag=tag, digest=digest)
    return ImageRef(repository=reste, digest=digest)


def repository(image: str) -> str:
    """Depot seul, sans tag ni digest."""
    return parse(image).repository


def tag(image: str) -> str:
    """Tag seul. Vide pour une reference epinglee par digest uniquement."""
    return parse(image).tag


def with_tag(image: str, nouveau: str) -> str:
    """Remplace le tag, en LAISSANT TOMBER le digest.

    Changer de version et garder l'ancien condensat donnerait une reference qui
    ment : Docker retient le digest, donc le nouveau tag ne serait qu'un
    ornement. Mieux vaut une reference honnete qu'une reference jolie.
    """
    return str(ImageRef(repository=parse(image).repository, tag=nouveau))
