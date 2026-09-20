"""Lancement automatique de la console d'administration, sur l'HOTE.

Pourquoi pas dans un conteneur, alors que c'est la demande naturelle : la
console doit creer, demarrer et recreer des conteneurs. Traduit en API Docker,
cela veut dire `POST /containers/create` puis `/start` — et un conteneur qu'on
cree peut monter la racine de l'hote et tourner en root. Un proxy de socket qui
autorise ces deux appels n'enferme donc rien, et sans eux la console ne peut
plus rien faire. Mettre cette console dans un conteneur avec le socket revient
a exposer sur le reseau un service qui a les pleins pouvoirs sur la machine.

Sur l'hote, elle tourne sous le compte de l'utilisateur, ecoute sur 127.0.0.1,
et n'est pas joignable depuis le reseau Docker. Le confort recherche — ne plus
avoir a lancer une commande — est le meme.

DEUX PORTEES, et elles ne repondent pas a la meme question.

- **utilisateur** : la console demarre a l'ouverture de SESSION, ecoute sur
  127.0.0.1, et n'exige aucun droit administrateur. C'est le cas courant, sur
  un poste dont on se sert ;
- **systeme** : la console demarre avec la MACHINE, sans qu'une session
  s'ouvre. C'est le seul cas qui couvre un serveur ou un LXC ou personne ne se
  connecte, et c'est ce qui permet d'administrer une machine distante. Elle
  exige alors un mot de passe, comme la veille : l'unite tourne sous le compte
  qui possede `stack.yml`, pas sous root par commodite.

Mecanismes de la portee utilisateur, aucun n'exigeant les droits
administrateur :

- **Windows** : un raccourci dans le dossier Demarrage de l'utilisateur. Visible,
  supprimable a la main, aucune elevation. `schtasks` ferait la meme chose en
  moins lisible et en demandant parfois une elevation ;
- **systemd** : une unite UTILISATEUR dans `~/.config/systemd/user/`. Attention,
  elle s'arrete a la deconnexion tant que `loginctl enable-linger` n'a pas ete
  passe : c'est dit, pas cache ;
- **ailleurs** (Unraid, Synology, BSD) : rien d'automatique. On rend la commande
  a coller, plutot que d'inventer un mecanisme non verifie.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .i18n import t

NOM = "plugarr-console"
UNIT = f"{NOM}.service"

#: Ou vit l'unite systeme. Chemin des unites locales, jamais `/lib/systemd` :
#: celui-la appartient aux paquets de la distribution.
DOSSIER_SYSTEME = Path("/etc/systemd/system")


@dataclass
class Etat:
    """Ce qui est en place, et ou."""

    mecanisme: str
    actif: bool
    chemin: Path | None = None
    detail: str = ""


def mecanisme(portee: str = "utilisateur") -> str:
    """Quel mecanisme cette machine sait utiliser, pour cette portee."""
    if portee == "systeme":
        # Windows aurait une tache planifiee au compte SYSTEM ; elle n'est pas
        # verifiee, et on ne propose pas un mecanisme qu'on n'a pas essaye.
        return "systemd-systeme" if shutil.which("systemctl") else "aucun"
    if sys.platform == "win32":
        return "demarrage-windows"
    if shutil.which("systemctl"):
        return "systemd-utilisateur"
    return "aucun"


# ------------------------------------------------------------------ Windows


def _dossier_demarrage() -> Path:
    """Dossier Demarrage de l'utilisateur courant.

    `APPDATA` est defini sur toute session Windows ; le chemin qui suit est fixe
    depuis Windows 7 et n'est pas localise, contrairement a son affichage dans
    l'explorateur.
    """
    import os

    return (
        Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        / "Microsoft/Windows/Start Menu/Programs/Startup"
    )


def _script_windows(commande: str) -> str:
    return (
        "@echo off\r\n"
        + t(
            "rem Genere par `plugarr autostart`. Supprimez ce fichier pour "
            "arreter\r\nrem le lancement automatique de la console "
            "d'administration.\r\n"
        )
        +         "title plugarr - console\r\n"
        f"{commande}\r\n"
    )


# ------------------------------------------------------------------ systemd


def _dossier_systemd() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _unite_systemd(commande: str, project_dir: Path, compte: str = "") -> str:
    """Unite systemd. `compte` non vide = unite SYSTEME, lancee sans session.

    `User=` porte le compte qui possede `stack.yml` : lui seul peut le lire, et
    faire tourner la console en root par commodite lui donnerait des droits
    dont elle n'a pas besoin.
    """
    corps = (
        "[Unit]\n"
        "Description=Console d'administration plugarr\n"
        "After=docker.service network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        f"WorkingDirectory={project_dir}\n"
        f"ExecStart={commande}\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
    )
    if compte:
        corps += f"User={compte}\n"
    # Une unite systeme demarre avec la MACHINE ; une unite utilisateur, a
    # l'ouverture de session.
    corps += "\n[Install]\n"
    corps += "WantedBy=multi-user.target\n" if compte else "WantedBy=default.target\n"
    return corps


def _systemctl(*args: str, systeme: bool = False) -> tuple[bool, str]:
    base = ["systemctl"] if systeme else ["systemctl", "--user"]
    proc = subprocess.run(
        [*base, *args], capture_output=True, text=True, timeout=60, check=False
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def _proprietaire(project_dir: Path) -> str:
    """Compte qui possede `stack.yml`, sous lequel l'unite systeme tournera.

    Chaine vide sans `pwd` (Windows) ou si le fichier manque : l'appelant
    refuse alors, plutot que de deviner un compte.
    """
    try:
        import pwd

        return pwd.getpwuid((Path(project_dir) / "stack.yml").stat().st_uid).pw_name
    except Exception:  # noqa: BLE001 - pas de pwd, fichier absent, uid inconnu
        return ""


# ------------------------------------------------------------------- actions


def commande(project_dir: Path, *, host: str, port: int) -> str:
    """Commande a lancer au demarrage.

    Reprend le chemin REELLEMENT utilise : quelqu'un qui a double-clique un
    executable n'a pas `plugarr` dans son PATH.

    `--no-open` est essentiel : ouvrir un navigateur a chaque ouverture de
    session serait insupportable.
    """
    cible = f'"{Path(project_dir).resolve()}"'
    # `sys.executable` tel quel, JAMAIS resolu : dans un environnement virtuel,
    # `bin/python3` est un lien vers l'interpreteur du systeme, et le resoudre
    # sort du venv. L'unite lancait alors `/usr/bin/python3 -m plugarr`, qui
    # repondait « No module named plugarr » — constate sur le banc le
    # 2026-09-20, le service redemarrait en boucle.
    base = f'"{sys.executable}"'
    if not getattr(sys, "frozen", False):
        base += " -m plugarr"
    return f"{base} serve --project-dir {cible} --host {host} --port {port} --no-open"


def status(project_dir: Path, portee: str = "utilisateur") -> Etat:
    """Le lancement automatique est-il en place ?"""
    quel = mecanisme(portee)
    if quel == "systemd-systeme":
        cible = DOSSIER_SYSTEME / UNIT
        actif, sortie = _systemctl("is-enabled", UNIT, systeme=True)
        return Etat(quel, cible.is_file() and actif, cible, sortie)
    if quel == "demarrage-windows":
        cible = _dossier_demarrage() / f"{NOM}.cmd"
        return Etat(quel, cible.is_file(), cible)
    if quel == "systemd-utilisateur":
        cible = _dossier_systemd() / UNIT
        actif, sortie = _systemctl("is-enabled", UNIT)
        return Etat(quel, cible.is_file() and actif, cible, sortie)
    return Etat(quel, False, None, t("aucun mecanisme connu sur cette plateforme"))


def enable(
    project_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 7373,
    portee: str = "utilisateur",
) -> tuple[bool, str]:
    """Installe le lancement automatique. Renvoie (succes, message)."""
    quel = mecanisme(portee)
    ligne = commande(project_dir, host=host, port=port)

    if quel == "systemd-systeme":
        import os

        if getattr(os, "geteuid", lambda: 0)() != 0:
            return False, t(
                "une unite systeme s'installe en root. Relancez avec sudo :\n"
                "  sudo {commande}",
                commande="plugarr autostart --systeme",
            )
        compte = _proprietaire(project_dir)
        if not compte:
            return False, t(
                "impossible de savoir a quel compte appartient stack.yml : "
                "l'unite tournerait sous un compte devine."
            )
        DOSSIER_SYSTEME.mkdir(parents=True, exist_ok=True)
        cible = DOSSIER_SYSTEME / UNIT
        cible.write_text(
            _unite_systemd(ligne, Path(project_dir).resolve(), compte), encoding="utf-8"
        )
        _systemctl("daemon-reload", systeme=True)
        ok, sortie = _systemctl("enable", "--now", UNIT, systeme=True)
        if not ok:
            return False, f"systemctl a refuse : {sortie[:300]}"
        return True, f"unite systeme installee et demarree ({compte}) : {cible}"

    if quel == "demarrage-windows":
        dossier = _dossier_demarrage()
        dossier.mkdir(parents=True, exist_ok=True)
        cible = dossier / f"{NOM}.cmd"
        cible.write_text(_script_windows(ligne), encoding="utf-8", newline="")
        return True, f"lancement automatique installe : {cible}"

    if quel == "systemd-utilisateur":
        dossier = _dossier_systemd()
        dossier.mkdir(parents=True, exist_ok=True)
        cible = dossier / UNIT
        cible.write_text(_unite_systemd(ligne, Path(project_dir).resolve()), encoding="utf-8")
        _systemctl("daemon-reload")
        ok, sortie = _systemctl("enable", "--now", UNIT)
        if not ok:
            return False, f"systemctl a refuse : {sortie[:300]}"
        return True, f"unite installee et demarree : {cible}"

    return False, t(
        "aucun mecanisme de lancement automatique connu sur cette plateforme. "
        "Lancez cette commande au demarrage de votre machine :\n  {commande}",
        commande=ligne,
    )


def disable(project_dir: Path, portee: str = "utilisateur") -> tuple[bool, str]:
    """Retire le lancement automatique."""
    quel = mecanisme(portee)

    if quel == "systemd-systeme":
        import os

        if getattr(os, "geteuid", lambda: 0)() != 0:
            return False, t("une unite systeme se retire en root. Relancez avec sudo.")
        cible = DOSSIER_SYSTEME / UNIT
        _systemctl("disable", "--now", UNIT, systeme=True)
        if cible.is_file():
            cible.unlink()
        _systemctl("daemon-reload", systeme=True)
        return True, f"unite systeme retiree : {cible}"

    if quel == "demarrage-windows":
        cible = _dossier_demarrage() / f"{NOM}.cmd"
        if not cible.is_file():
            return True, t("aucun lancement automatique installe")
        cible.unlink()
        return True, f"retire : {cible}"

    if quel == "systemd-utilisateur":
        cible = _dossier_systemd() / UNIT
        _systemctl("disable", "--now", UNIT)
        if cible.is_file():
            cible.unlink()
        _systemctl("daemon-reload")
        return True, f"unite retiree : {cible}"

    return True, t("aucun mecanisme installe sur cette plateforme")
