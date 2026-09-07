"""Reinstaller par-dessus une installation existante sans tout perdre.

`install` construisait sa configuration de zero et **ne regardait jamais le
`stack.yml` deja present**. Reinstaller effacait donc tout ce qu'il portait.
Mesure sur une installation d'essai :

    | | avant | apres reinstallation |
    | identifiant       | yannick             | plugarr    |
    | VPN               | mullvad + cle       | DESACTIVE  |
    | profils Recyclarr | choisis             | vides      |
    | mot de passe console | pose             | perdu      |

Le VPN est le cas grave : il disparait **en silence**, et l'installation
affiche « Aucun VPN n'est configure » — quelqu'un qui reinstalle pour reparer
autre chose se retrouve avec son trafic torrent en clair sans l'avoir voulu.

**Reprendre repare aussi un defaut plus ancien.** qBittorrent, Jellyfin,
autobrr, qui et les autres ne stockent leur mot de passe que HACHE : PlugArr ne
peut pas le relire dans leur configuration, en generait un nouveau, l'annoncait,
et le service le refusait. Mais quand c'est PlugArr qui a installe, le mot de
passe est dans SON `stack.yml` — il n'a jamais eu besoin de le relire ailleurs.
Reprendre les identifiants precedents fait donc coincider ce qui est annonce et
ce qui est en place.

**Ce qu'on ne reprend pas** : la selection de services, les racines, la
plateforme. Ce sont les reponses de l'installation en cours, pas des reglages
qu'on herite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import migrations, registre
from .i18n import t
from .models import StackConfig


@dataclass
class Reprise:
    """Ce qui a ete repris d'une installation precedente, pour l'afficher.

    Une reprise silencieuse serait pire que pas de reprise : l'utilisateur doit
    voir ce que PlugArr a decide de garder a sa place.
    """

    reglages: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.reglages or self.services)


def _lire(chemin: Path) -> StackConfig | None:
    """Lit un `stack.yml`, ou rend None s'il n'est pas exploitable.

    Un `stack.yml` illisible n'arrete pas une installation neuve : on repart de
    zero, ce qui est exactement ce que l'utilisateur a demande. Une version
    FUTURE, en revanche, remonte — la refuser est tout l'interet du garde-fou.
    """
    if not chemin.is_file():
        return None
    try:
        cfg, _notes = migrations.lire(chemin)
    except migrations.VersionFuture:
        raise
    except (ValueError, OSError):
        return None
    return cfg


@dataclass
class Trouvee:
    """Une installation precedente, et OU elle a ete trouvee.

    Le chemin compte autant que la configuration : quand il ne designe pas le
    repertoire courant, l'assistant doit le dire. Reprendre en silence les
    identifiants d'une installation posee ailleurs, puis ecrire les artefacts
    ici, donnerait deux piles divergentes portant les memes mots de passe.
    """

    cfg: StackConfig
    chemin: Path

    @property
    def project_dir(self) -> Path:
        return self.chemin.parent


def trouver(project_dir: Path, config_root: str | None = None) -> Trouvee | None:
    """Cherche l'installation precedente, y compris hors du repertoire courant.

    Deux endroits, dans cet ordre :

    1. `project_dir/stack.yml` — le cas courant, celui de qui relance
       l'executable la ou il l'a lance la premiere fois ;
    2. le registre des installations — le cas de qui l'a deplace sur son
       bureau, ou qui l'a lance depuis `Telechargements` puis depuis ailleurs.

    Le second manquait, et son absence coutait cher : sans `stack.yml` sous la
    main, PlugArr generait des mots de passe neufs pour des services qui, eux,
    avaient garde les anciens. L'installation se terminait sur une serie de
    401 incomprehensibles.
    """
    ici = Path(project_dir) / "stack.yml"
    cfg = _lire(ici)
    if cfg is not None:
        return Trouvee(cfg, ici)

    connue = registre.retrouver(config_root)
    if connue is None:
        return None
    ailleurs = _lire(connue.stack)
    if ailleurs is None:
        return None
    return Trouvee(ailleurs, connue.stack)


def precedente(project_dir: Path, config_root: str | None = None) -> StackConfig | None:
    """Configuration de l'installation deja presente, si elle est lisible."""
    trouvee = trouver(project_dir, config_root)
    return trouvee.cfg if trouvee else None


#: Combien de mots de passe passes on accepte d'essayer contre un service.
#:
#: Ce n'est pas une optimisation. qBittorrent bannit une adresse apres CINQ
#: echecs d'authentification, une heure durant ; rien ne dit que les autres
#: n'ont pas de garde-fou comparable. Essayer les vingt installations d'un
#: registre bien rempli transformerait un rattrapage en blocage.
MAX_ESSAIS = 4


def mots_de_passe_connus(
    project_dir: Path | None, service_id: str, limite: int = MAX_ESSAIS
) -> list[str]:
    """Les mots de passe qu'un service a pu recevoir, du plus recent au plus ancien.

    Jellyfin, autobrr et qui ne gardent leur mot de passe que HACHE. Quand
    celui qu'on s'apprete a annoncer est refuse, le vrai n'est pas perdu pour
    autant : il est dans un `stack.yml` precedent, garde par la rotation de
    `compose._historiser`. Les essayer coute quelques requetes et evite d'avoir
    a effacer la configuration du service.

    L'ordre compte : le plus recent d'abord, parce que c'est le plus probable,
    et le repertoire courant avant les autres installations de la machine.
    """
    from . import compose

    if project_dir is None:
        return []
    dossiers: list[Path] = [Path(project_dir)]
    for connue in registre.lire():
        if connue.vivante and connue.project_dir not in dossiers:
            dossiers.append(connue.project_dir)

    trouves: list[str] = []
    for dossier in dossiers:
        for chemin in (dossier / "stack.yml", *compose.historique(dossier)):
            try:
                cfg = _lire(chemin)
            except migrations.VersionFuture:
                # Ici on ne REECRIT rien : on relit un vieux mot de passe. Un
                # fichier venu d'une version future se saute, il n'arrete pas un
                # cablage en cours.
                continue
            if cfg is None:
                continue
            instance = cfg.services.get(service_id)
            mot = getattr(instance, "password", "") or ""
            if mot and mot not in trouves:
                trouves.append(mot)
                if len(trouves) >= limite:
                    return trouves
    return trouves


#: Reglages repris tels quels, avec le libelle montre a l'utilisateur. L'ordre
#: est celui de l'affichage.
_REGLAGES: tuple[tuple[str, str], ...] = (
    ("username", "identifiant"),
    ("timezone", "fuseau horaire"),
    ("host", "adresse de la machine"),
    ("language", "langue des services"),
    ("ui_language", "langue de PlugArr"),
    ("admin_password_hash", "mot de passe de la console"),
    ("recyclarr_templates", "profils de qualite"),
)


def appliquer(
    neuve: StackConfig, ancienne: StackConfig, *, imposes: set[str] | None = None
) -> Reprise:
    """Reporte les reglages de l'ancienne installation dans la nouvelle.

    `imposes` nomme les reglages donnes EXPLICITEMENT sur la ligne de commande
    ou dans l'assistant : une option ecrite a la main prime toujours sur ce
    qu'on herite, sinon elle serait sans effet et personne ne comprendrait
    pourquoi.
    """
    imposes = imposes or set()
    reprise = Reprise()

    for champ, libelle in _REGLAGES:
        if champ in imposes:
            continue
        valeur = getattr(ancienne, champ, None)
        if not valeur or valeur == getattr(type(neuve).model_fields[champ], "default", None):
            continue
        setattr(neuve, champ, valeur)
        reprise.reglages.append(t(libelle))

    # Le VPN en bloc : reprendre le fournisseur sans la cle donnerait une
    # configuration incomplete, que Gluetun refuserait au demarrage.
    if "vpn" not in imposes and ancienne.vpn.enabled:
        neuve.vpn = ancienne.vpn.model_copy(deep=True)
        reprise.reglages.append(t("VPN ({fournisseur})", fournisseur=ancienne.vpn.provider))

    # Les identifiants, service par service. C'est ce qui evite d'annoncer un
    # mot de passe que le service refusera.
    for sid, instance in neuve.services.items():
        precedent = ancienne.services.get(sid)
        if precedent is None:
            continue
        repris = False
        for champ in ("username", "password", "api_key"):
            valeur = getattr(precedent, champ, "")
            if valeur:
                setattr(instance, champ, valeur)
                repris = True
        # Le port aussi : quelqu'un qui a decale qBittorrent pour eviter un
        # conflit ne veut pas le retrouver sur 8080.
        if precedent.host_port and precedent.host_port != instance.host_port:
            instance.host_port = precedent.host_port
            repris = True
        if repris:
            reprise.services.append(sid)

    return reprise
