"""PlugArr parle anglais, et deux langues cohabitent sans se confondre.

Demande a l'usage, en deux morceaux : « ajoute la traduction anglaise a
l'application avec un menu de selection de la langue » et « ajoute aussi la
possibilite de choisir la langue de configuration de la suite arr ».

Le second existait deja depuis la 0.1.11 — mais il etait SEUL, et donc
ambigu : l'ecran disait « langue des interfaces » sans dire lesquelles. Les
deux reglages sont desormais distincts et nommes.

**Le garde-fou est mecanique.** Une phrase ajoutee en francais et oubliee dans
le catalogue ne casse rien : elle s'affiche simplement en francais a quelqu'un
qui a demande l'anglais, sans erreur ni avertissement. Seul un controle
automatique attrape ca, et `scripts/audit_traductions.py` le fait dans les deux
sens — phrase sans traduction, et entree qui ne correspond plus a rien.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from plugarr import i18n
from plugarr.traductions import EN

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _langue_restauree():
    """La langue est un etat de processus : la rendre comme on l'a trouvee."""
    avant = i18n.langue()
    yield
    i18n.utiliser(avant)


# ------------------------------------------------------------------ le socle


def test_le_francais_est_la_langue_source():
    """Une phrase sans traduction retombe sur elle-meme, jamais sur une cle.

    C'est ce qui rend l'oubli benin : au pire l'utilisateur lit du francais,
    pas `ecran.accueil.titre`.
    """
    i18n.utiliser("en")

    assert i18n.t("phrase que personne n'a traduite") == "phrase que personne n'a traduite"


def test_une_langue_inconnue_ne_leve_pas():
    """`LANG=C.UTF-8` ne doit pas empecher l'assistant de demarrer."""
    assert i18n.utiliser("klingon") == "fr"
    assert i18n.utiliser(None) == "fr"


def test_les_champs_sont_remplis_apres_traduction():
    """L'inverse chercherait au catalogue une cle contenant deja les valeurs,
    qui n'y figure par construction jamais."""
    i18n.utiliser("en")

    assert i18n.t("[b]Liens a cabler[/b] {nombre}", nombre=12).endswith("12")


def test_une_traduction_aux_mauvais_champs_ne_tue_pas_l_assistant():
    """Elle rend le francais, qui lui est bon."""
    i18n.utiliser("en")
    i18n._CATALOGUES["en"]["essai {bon}"] = "attempt {faute_de_frappe}"
    try:
        assert i18n.t("essai {bon}", bon="x") == "essai x"
    finally:
        del i18n._CATALOGUES["en"]["essai {bon}"]


@pytest.mark.parametrize(
    ("environnement", "locale_systeme", "attendu"),
    [
        ({"LANG": "fr_FR.UTF-8"}, None, "fr"),
        ({"LANG": "en_US.UTF-8"}, None, "en"),
        ({"LC_ALL": "en_GB.UTF-8", "LANG": "fr_FR.UTF-8"}, None, "en"),
        # Une langue que PlugArr ne parle pas : on retombe sur la locale de la
        # machine, puis sur le francais si elle ne dit rien.
        ({"LANG": "de_DE.UTF-8"}, None, "fr"),
        ({"LANG": "de_DE.UTF-8"}, "en_US", "en"),
        ({"LANG": "de_DE.UTF-8"}, "fr_FR", "fr"),
    ],
)
def test_la_langue_par_defaut_vient_du_systeme(
    monkeypatch, environnement, locale_systeme, attendu
):
    """Un francophone trouve PlugArr en francais sans rien regler, tout le monde
    d'autre en anglais. C'est le defaut le plus utile pour un projet qui vise
    les deux publics.

    **La locale de la MACHINE est simulee, pas subie.** Le test ne remplacait
    que les variables d'environnement et laissait `locale.getlocale()` repondre
    ce qu'il voulait : le cas `de_DE` passait sur un poste francais et echouait
    sur un poste anglais. Constate en lancant la suite sur un LXC Debian en
    `en_US`. Un test dont le verdict depend de la machine ne verifie pas le
    code.
    """
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(variable, raising=False)
    for variable, valeur in environnement.items():
        monkeypatch.setenv(variable, valeur)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda *a: (locale_systeme, "UTF-8"))

    assert i18n.langue_du_systeme() == attendu


# ---------------------------------------------------------------- le catalogue


def test_aucune_phrase_n_echappe_au_catalogue():
    """Le controle qui compte. Il tourne aussi en CI.

    Sans lui, une phrase ajoutee a un ecran resterait francaise en anglais, et
    personne ne le verrait avant un utilisateur.
    """
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "scripts" / "audit_traductions.py")],
        capture_output=True,
        text=True,
        cwd=RACINE,
        check=False,
    )

    assert resultat.returncode == 0, resultat.stdout + resultat.stderr


def test_les_balises_de_mise_en_forme_sont_reportees():
    """Une balise ouverte et jamais fermee s'affiche en clair au milieu du
    texte. Rich ne signale rien."""
    ecarts = []
    for francais, anglais in EN.items():
        for balise in ("[b]", "[dim]", "[green]", "[yellow]", "[red]", "[cyan]"):
            if francais.count(balise) != anglais.count(balise):
                ecarts.append(f"{balise} dans {francais[:50]!r}")
            fermante = balise.replace("[", "[/")
            if francais.count(fermante) != anglais.count(fermante):
                ecarts.append(f"{fermante} dans {francais[:50]!r}")

    assert not ecarts, ecarts


def test_les_champs_nommes_sont_reportes():
    """Un champ perdu dans la traduction laisserait un trou dans la phrase ;
    un champ invente leverait une KeyError a l'affichage."""
    import re

    ecarts = []
    for francais, anglais in EN.items():
        champs = re.compile(r"\{(\w+)\}")
        if set(champs.findall(francais)) != set(champs.findall(anglais)):
            ecarts.append(francais[:60])

    assert not ecarts, ecarts


def test_le_catalogue_ne_traduit_pas_par_l_identite():
    """Une entree identique au francais est presque toujours un oubli.

    Les exceptions sont reelles mais rares : « Service », « URL », « Image »
    s'ecrivent pareil dans les deux langues.
    """
    identiques = {fr for fr, en in EN.items() if fr == en}

    assert identiques <= {
        # Mots identiques dans les deux langues. La liste est volontairement
        # close : elle doit etre allongee sciemment, pas par accident.
        "Service",
        "Services",
        "Image",
        "URL",
        "Administration",
        "Preflight",
        "Detail",
        "diagnostic",
        "[green]Configuration complete.[/green]",
        # Des commandes a taper : les traduire les rendrait fausses.
        "  plugarr admin-password",
        "  loginctl enable-linger $USER",
        # Des mots identiques dans les deux langues, ou des marqueurs de sortie.
        "cause",
        "action",
        ", test OK",
        "Date",
        "Volumes",
        "Catalogue",
        "VPN ({fournisseur})",
    }, identiques


# -------------------------------------------------- les widgets qui traduisent


def test_le_widget_traduit_son_libelle():
    """C'est ce qui evite d'avoir a envelopper cent-cinquante phrases a la
    main, et donc d'en oublier."""
    from plugarr.tui.widgets import Button

    i18n.utiliser("en")

    assert str(Button("Continuer").label) == "Continue"


def test_le_widget_laisse_passer_ce_qui_n_est_pas_une_phrase():
    """Textual accepte aussi des objets Rich : les traduire n'aurait pas de
    sens, et `t()` leverait sur un objet non hachable."""
    from rich.text import Text

    from plugarr.tui.widgets import _traduit

    objet = Text("Continuer")

    assert _traduit(objet) is objet


def test_l_audit_couvre_tous_les_widgets_traduisants():
    """Un widget ajoute a `widgets.py` et absent de la liste de l'audit
    sortirait du controle en silence : ses phrases ne seraient plus verifiees,
    et rien ne le dirait."""
    import ast

    sys.path.insert(0, str(RACINE / "scripts"))
    from audit_traductions import WIDGETS_TRADUISANTS

    source = (RACINE / "src" / "plugarr" / "tui" / "widgets.py").read_text(encoding="utf-8")
    definis = {
        noeud.name
        for noeud in ast.parse(source).body
        if isinstance(noeud, ast.ClassDef)
    }

    assert definis - {"Input"} <= set(WIDGETS_TRADUISANTS), definis


# ----------------------------------------------- les deux langues sont distinctes


def test_stack_yml_porte_les_deux_langues():
    """Celle de PlugArr et celle des services vivent separement : on peut
    vouloir l'outil en anglais et sa mediatheque en francais."""
    from plugarr import orchestrator

    cfg = orchestrator.build_config(services=["sonarr"], language="fr")
    cfg.ui_language = "en"

    assert cfg.language == "fr"
    assert cfg.ui_language == "en"


def test_une_installation_retrouve_sa_langue(tmp_path, monkeypatch):
    """`plugarr serve` sur un serveur dont la session est en anglais doit
    repondre en francais a quelqu'un qui a installe en francais."""
    import yaml

    from plugarr import cli, orchestrator

    cfg = orchestrator.build_config(services=["sonarr"])
    cfg.ui_language = "en"
    (tmp_path / "stack.yml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json")), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "_LANGUE_EXPLICITE", False)
    i18n.utiliser("fr")

    cli._load_config(tmp_path)

    assert i18n.langue() == "en"


def test_une_langue_donnee_a_la_main_prime_sur_le_fichier(tmp_path, monkeypatch):
    """Une option ecrite explicitement ne doit jamais etre annulee par un
    fichier trouve sur le disque."""
    import yaml

    from plugarr import cli, orchestrator

    cfg = orchestrator.build_config(services=["sonarr"])
    cfg.ui_language = "en"
    (tmp_path / "stack.yml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json")), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "_LANGUE_EXPLICITE", True)
    i18n.utiliser("fr")

    cli._load_config(tmp_path)

    assert i18n.langue() == "fr"


def test_la_langue_des_services_part_de_celle_de_plugarr():
    """Le cas courant. Les deux restent separables a l'ecran des chemins, mais
    proposer l'anglais des services a quelqu'un qui vient de choisir le
    francais serait un pas de plus pour rien."""
    from plugarr.tui.screens import PathsScreen

    i18n.utiliser("en")
    assert PathsScreen._langue_par_defaut() == "en"
    i18n.utiliser("fr")
    assert PathsScreen._langue_par_defaut() == "fr"


def test_une_langue_que_les_services_ignorent_retombe_sur_l_anglais():
    """`langues.PROPOSEES` est plus courte que ce que PlugArr sait parler : une
    valeur absente ferait refuser la liste et l'ecran ne se monterait pas.

    C'est exactement le defaut qui a tue l'assistant au premier essai reel, sur
    l'autre liste : `Select` attend (libelle, valeur) et recevait (valeur,
    libelle).
    """
    from plugarr import langues
    from plugarr.tui.screens import PathsScreen

    i18n._langue = "ml"  # connue des *arr, absente de la liste proposee
    try:
        assert PathsScreen._langue_par_defaut() == "en"
    finally:
        i18n.utiliser("fr")
    assert all(lang.code != "ml" for lang in langues.PROPOSEES)


def test_la_liste_des_langues_est_dans_le_bon_ordre_pour_textual():
    """`Select` attend (libelle, valeur). Inverser les deux rendait le code
    « fr » illegal et tuait l'assistant au montage de l'accueil."""
    from plugarr.tui.screens import WelcomeScreen

    source = __import__("inspect").getsource(WelcomeScreen.content)

    assert "[(nom, code) for code, nom in i18n.DISPONIBLES]" in source
