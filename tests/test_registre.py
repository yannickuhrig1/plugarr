"""Retrouver l'installation precedente, et ne plus jamais perdre son mot de passe.

Le defaut repare ici a ete constate sur une machine reelle, le 7 septembre 2026.
Une installation posee le 4 septembre, un `stack.yml` reecrit les jours
suivants, et Jellyfin qui refuse l'unique mot de passe que PlugArr croit
connaitre. Deux causes distinctes, toutes deux mortelles pour l'utilisateur :

1. **`stack.yml` n'etait cherche que dans le repertoire courant.** Lancer
   `plugarr.exe` depuis un autre dossier repartait de zero, sans un mot, avec
   des mots de passe neufs que les services refusaient ;
2. **`write_artifacts` ecrasait `stack.yml` avant que le cablage n'ait rien
   prouve.** Le seul exemplaire en clair du mot de passe d'un service qui, lui,
   ne garde qu'un hachage, disparaissait a la premiere relance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from plugarr import compose, orchestrator, registre, reprise
from plugarr.clients.base import WiringError


def _config(tmp_path, **extra):
    cfg = orchestrator.build_config(
        services=["sonarr", "jellyfin"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    for champ, valeur in extra.items():
        setattr(cfg, champ, valeur)
    return cfg


# ------------------------------------------------------------------ le registre


def test_une_installation_ecrite_est_notee(tmp_path):
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)

    connues = registre.lire()

    assert [e.project_dir for e in connues] == [projet.resolve()]
    assert connues[0].config_root == str(tmp_path / "config")


def test_le_registre_ne_porte_aucun_secret(tmp_path):
    """Il dit OU chercher, jamais QUOI. Les secrets restent dans stack.yml.

    Un index de chemins se recopie, se sauvegarde et se lit sans precaution.
    Y glisser un mot de passe en ferait un second fichier sensible, pose hors
    du projet et hors de tout `.gitignore`.
    """
    cfg = _config(tmp_path)
    compose.write_artifacts(cfg, tmp_path / "projet")

    contenu = registre.chemin().read_text(encoding="utf-8")

    for instance in cfg.services.values():
        for secret in (instance.password, instance.api_key):
            if secret:
                assert secret not in contenu


def test_le_config_root_designe_la_bonne_installation(tmp_path):
    """Deux installations sur la meme machine : c'est CONFIG_ROOT qui tranche.

    Il est saisi dans l'assistant et designe les services reellement en place ;
    la date d'ecriture, elle, ne dit rien de ce que l'utilisateur vise.
    """
    compose.write_artifacts(_config(tmp_path, config_root=str(tmp_path / "media")), tmp_path / "a")
    compose.write_artifacts(_config(tmp_path, config_root=str(tmp_path / "essai")), tmp_path / "b")

    trouvee = registre.retrouver(str(tmp_path / "media"))

    assert trouvee is not None
    assert trouvee.project_dir == (tmp_path / "a").resolve()


def test_une_installation_effacee_n_est_plus_proposee(tmp_path):
    """Un dossier supprime ou un disque debranche laissent une entree derriere.

    La proposer enverrait l'utilisateur vers un `stack.yml` qui n'existe plus.
    """
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)
    (projet / "stack.yml").unlink()

    assert registre.retrouver() is None


# ------------------------------------------------- retrouver depuis n'importe ou


def test_le_stack_est_retrouve_depuis_un_autre_dossier(tmp_path):
    """Le cas reel : l'executable lance ailleurs que la premiere fois.

    Sans cela, PlugArr repartait de zero en silence et annoncait des mots de
    passe que Jellyfin, autobrr et qui refusaient ensuite.
    """
    origine = tmp_path / "telechargements"
    compose.write_artifacts(_config(tmp_path, username="yannick"), origine)

    trouvee = reprise.trouver(tmp_path / "bureau", str(tmp_path / "config"))

    assert trouvee is not None
    assert trouvee.cfg.username == "yannick"
    assert trouvee.project_dir == origine.resolve()


def test_le_repertoire_courant_prime_sur_le_registre(tmp_path):
    """Un `stack.yml` sous la main est toujours le bon : c'est celui qu'on vise."""
    compose.write_artifacts(_config(tmp_path, username="ailleurs"), tmp_path / "ailleurs")
    ici = tmp_path / "ici"
    compose.write_artifacts(_config(tmp_path, username="ici"), ici)

    trouvee = reprise.trouver(ici)

    assert trouvee is not None
    assert trouvee.cfg.username == "ici"


def test_l_assistant_suit_l_installation_retrouvee(tmp_path):
    """Il ECRIT la ou elle est : une pile Docker ne vit pas dans deux dossiers.

    Docker identifie une pile par son nom, pas par son repertoire. Ecrire ici
    les artefacts d'une pile installee ailleurs donnerait deux repertoires
    concurrents, et le second recreerait les conteneurs du premier.
    """
    from plugarr.tui.app import PlugArrApp

    ailleurs = tmp_path / "telechargements"
    compose.write_artifacts(_config(tmp_path, username="yannick"), ailleurs)

    app = PlugArrApp(tmp_path / "bureau")
    app.selection = ["sonarr", "jellyfin"]
    app.config_root = str(tmp_path / "config")
    app.data_root = str(tmp_path / "data")
    cfg = app.build_config()

    assert cfg.username == "yannick"
    assert app.project_dir == ailleurs.resolve()
    assert app.reprise_depuis == ailleurs.resolve()


def test_refuser_la_reprise_ramene_au_repertoire_de_lancement(tmp_path):
    """Sinon « repartir de zero » ecrirait dans l'installation qu'on ecarte."""
    from plugarr.tui.app import PlugArrApp

    compose.write_artifacts(_config(tmp_path, username="yannick"), tmp_path / "telechargements")

    app = PlugArrApp(tmp_path / "bureau")
    app.selection = ["sonarr", "jellyfin"]
    app.config_root = str(tmp_path / "config")
    app.data_root = str(tmp_path / "data")
    app.build_config()
    app.reprendre = False
    cfg = app.build_config()

    assert cfg.username != "yannick"
    assert app.project_dir == tmp_path / "bureau"
    assert app.reprise_depuis is None


def _console_muette(monkeypatch):
    """Recueille ce que la commande dit, sans salir la console partagee."""
    from plugarr import cli

    dits: list[str] = []
    monkeypatch.setattr(
        cli.console, "print", lambda *a, **k: dits.append(" ".join(str(x) for x in a))
    )
    return dits


def test_un_service_repris_n_est_plus_signale_comme_perdu(tmp_path, monkeypatch):
    """L'avertissement se contredisait deux lignes sous « Identifiants conserves ».

    Constate en lancant une reinstallation reelle sur une pile de cinq
    services : PlugArr annoncait « Credentials kept : jellyfin, qbittorrent »
    puis, juste dessous, « leurs mots de passe ne se relisent pas : ceux qu'il
    va annoncer seront refuses ». Les deux ne peuvent pas etre vrais.

    Proposer d'effacer leur configuration etait pire que la contradiction :
    c'est une perte seche pour reparer quelque chose qui marche.
    """
    from plugarr import cli

    cfg = _config(tmp_path)
    dossier = Path(cfg.config_path("jellyfin"))
    dossier.mkdir(parents=True)
    (dossier / "data.db").write_text("x", encoding="utf-8")

    dits = _console_muette(monkeypatch)

    cli._traiter_config_existante(cfg, None, assume_yes=True, repris={"jellyfin"})

    assert dits == [], "un service repris n'a plus rien a signaler"


def test_un_service_non_repris_est_toujours_signale(tmp_path, monkeypatch):
    """Le garde-fou reste entier pour ce qui vient VRAIMENT d'ailleurs."""
    from plugarr import cli

    cfg = _config(tmp_path)
    dossier = Path(cfg.config_path("jellyfin"))
    dossier.mkdir(parents=True)
    (dossier / "data.db").write_text("x", encoding="utf-8")

    dits = _console_muette(monkeypatch)

    cli._traiter_config_existante(cfg, None, assume_yes=True, repris=set())

    assert any("jellyfin" in ligne for ligne in dits)


# ------------------------------------------------------------------ l'historique


def test_le_stack_precedent_est_garde(tmp_path):
    """C'est tout le correctif : une reecriture ne detruit plus le mot de passe.

    `write_artifacts` est appele trois fois par installation, dont une AVANT le
    demarrage des conteneurs. Une installation qui echoue ecrasait donc le seul
    exemplaire en clair d'un mot de passe qui, lui, fonctionnait.
    """
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path, username="avant"), projet)
    compose.write_artifacts(_config(tmp_path, username="apres"), projet)

    garde = yaml.safe_load((projet / "stack.yml.1").read_text(encoding="utf-8"))
    courant = yaml.safe_load((projet / "stack.yml").read_text(encoding="utf-8"))

    assert garde["username"] == "avant"
    assert courant["username"] == "apres"


def test_une_ecriture_identique_ne_chasse_pas_l_historique(tmp_path):
    """Regenerer plusieurs fois de suite ne doit pas vider les versions utiles.

    C'est le cas de `plugarr generate`, ou d'un `wire` rejoue : le meme
    `stack.yml` est reecrit a l'identique. Historiser chaque passage chasserait
    en cinq relances les seules versions qui portent encore un ancien mot de
    passe.
    """
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path, username="premier"), projet)
    inchangee = _config(tmp_path, username="second")
    for _ in range(5):
        compose.write_artifacts(inchangee, projet)

    gardes = [
        yaml.safe_load(chemin.read_text(encoding="utf-8"))["username"]
        for chemin in compose.historique(projet)
    ]

    # Une seule entree par contenu distinct : la version qui portait l'ancien
    # mot de passe est toujours la apres cinq relances.
    assert gardes == ["second", "premier"]


def test_l_historique_couvre_plusieurs_installations(tmp_path):
    """Une installation consomme QUATRE entrees, pas une. Mesure, pas suppose.

    `write_artifacts` est appele trois fois par `install` — avant le pre-semis,
    apres l'adoption des cles API, apres le cablage — puis une fois de plus par
    `wire`. Constate sur une installation reelle de cinq services : l'historique
    est monte a `stack.yml.4` en un seul passage.

    A cinq entrees, deux installations ratees de suite chassaient le mot de
    passe qui fonctionnait. Cet historique existe precisement pour l'empecher.
    """
    projet = tmp_path / "projet"
    par_installation = 4
    installations = 3
    ecritures = par_installation * installations

    for _ in range(ecritures):
        compose.write_artifacts(_config(tmp_path), projet)

    # La premiere ecriture n'historise rien : il n'y a pas encore de fichier a
    # preserver. N ecritures laissent donc N-1 entrees.
    assert compose.HISTORIQUE >= ecritures - 1
    assert len(compose.historique(projet)) == ecritures - 1


def test_l_historique_est_borne(tmp_path):
    projet = tmp_path / "projet"
    for numero in range(compose.HISTORIQUE + 4):
        compose.write_artifacts(_config(tmp_path, username=f"v{numero}"), projet)

    assert len(compose.historique(projet)) == compose.HISTORIQUE
    assert not (projet / f"stack.yml.{compose.HISTORIQUE + 1}").exists()


def test_l_historique_est_ignore_par_git(tmp_path):
    """Les fichiers gardes portent les memes secrets que l'original."""
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)

    assert "stack.yml.*" in (projet / ".gitignore").read_text(encoding="utf-8")


# ------------------------------------------------------- les mots de passe passes


def test_les_mots_de_passe_precedents_sont_retrouves(tmp_path):
    projet = tmp_path / "projet"
    premiere = _config(tmp_path)
    premiere.services["jellyfin"].password = "AncienMotDePasse1!"
    compose.write_artifacts(premiere, projet)

    seconde = _config(tmp_path)
    seconde.services["jellyfin"].password = "Nouveau2@"
    compose.write_artifacts(seconde, projet)

    connus = reprise.mots_de_passe_connus(projet, "jellyfin")

    assert connus[0] == "Nouveau2@"
    assert "AncienMotDePasse1!" in connus


def test_le_nombre_d_essais_est_borne(tmp_path):
    """Ce n'est pas une optimisation, c'est un garde-fou.

    qBittorrent bannit une adresse apres CINQ echecs d'authentification, une
    heure durant. Essayer les vingt installations d'un registre bien rempli
    transformerait le rattrapage en blocage.
    """
    projet = tmp_path / "projet"
    for numero in range(10):
        cfg = _config(tmp_path)
        cfg.services["jellyfin"].password = f"MotDePasse{numero}!"
        compose.write_artifacts(cfg, projet)

    assert len(reprise.mots_de_passe_connus(projet, "jellyfin")) == reprise.MAX_ESSAIS


def test_les_mots_de_passe_des_autres_installations_comptent(tmp_path):
    """Meme depuis un dossier vide : c'est le registre qui les rend accessibles."""
    ancienne = _config(tmp_path)
    ancienne.services["jellyfin"].password = "PoseeAilleurs3#"
    compose.write_artifacts(ancienne, tmp_path / "ailleurs")

    connus = reprise.mots_de_passe_connus(tmp_path / "vide", "jellyfin")

    assert "PoseeAilleurs3#" in connus


# ------------------------------------------------------------------ le rattrapage


class _Serveur:
    """Un service qui n'accepte qu'un seul mot de passe, comme Jellyfin."""

    def __init__(self, attendu: str):
        self.attendu = attendu
        self.essais: list[str] = []

    def __call__(self, mot: str) -> None:
        self.essais.append(mot)
        if mot != self.attendu:
            raise WiringError(
                "jellyfin: POST /Users/AuthenticateByName a echoue", "HTTP 401", ""
            )


def _wirer(tmp_path, projet):
    from plugarr.wiring import Wirer

    cfg = _config(tmp_path)
    cfg.project_dir = projet
    return Wirer(cfg, run_tests=False), cfg


def test_un_mot_de_passe_herite_est_essaye_et_adopte(tmp_path):
    """Le 401 de la capture d'ecran, resolu sans rien effacer.

    Jellyfin garde le mot de passe du 4 septembre ; PlugArr en annonce un neuf.
    Plutot que d'echouer, il essaie ceux de ses installations passees et adopte
    celui qui passe — c'est lui que la page d'acces affichera.
    """
    projet = tmp_path / "projet"
    ancienne = _config(tmp_path)
    ancienne.services["jellyfin"].password = "CeluiDeJellyfin4$"
    compose.write_artifacts(ancienne, projet)
    compose.write_artifacts(_config(tmp_path), projet)

    wirer, cfg = _wirer(tmp_path, projet)
    instance = cfg.services["jellyfin"]
    instance.password = "NeufEtRefuse5%"
    serveur = _Serveur("CeluiDeJellyfin4$")

    repris = wirer._connexion_rattrapee("jellyfin", instance, serveur)

    assert repris is True
    assert instance.password == "CeluiDeJellyfin4$"
    assert serveur.essais[0] == "NeufEtRefuse5%"
    assert wirer.recuperations == ["jellyfin"]


def test_le_mot_de_passe_annonce_est_essaye_en_premier(tmp_path):
    """Le cas courant ne doit rien couter : une requete, comme avant."""
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)

    wirer, cfg = _wirer(tmp_path, projet)
    instance = cfg.services["jellyfin"]
    instance.password = "CeluiQuiMarche6^"
    serveur = _Serveur("CeluiQuiMarche6^")

    assert wirer._connexion_rattrapee("jellyfin", instance, serveur) is False
    assert serveur.essais == ["CeluiQuiMarche6^"]
    assert wirer.recuperations == []


def test_aucun_mot_de_passe_accepte_leve_l_erreur_du_service(tmp_path):
    """L'utilisateur doit lire le refus du service, pas une phrase de PlugArr.

    C'est ce refus-la qui porte le nom de l'appel et le code HTTP : le
    remplacer par un message generique ferait perdre le seul element
    diagnostique de la trace.
    """
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)

    wirer, cfg = _wirer(tmp_path, projet)
    cfg.services["jellyfin"].password = "NeufEtRefuse5%"

    with pytest.raises(WiringError) as exc:
        wirer._connexion_rattrapee("jellyfin", cfg.services["jellyfin"], _Serveur("introuvable"))

    assert "AuthenticateByName" in str(exc.value)
