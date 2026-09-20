"""Tests de la configuration Recyclarr.

Le fragment de template reproduit ici est copie tel quel d'un conteneur
`ghcr.io/recyclarr/recyclarr:8.7.1` : c'est lui qui fixe la forme des marqueurs.
Si une version future changeait leur libelle, ces tests le signaleraient avant
qu'une installation ne parte avec une configuration a moitie remplie.
"""

from __future__ import annotations

from pathlib import Path

from plugarr import catalog, compose
from plugarr.clients import recyclarr
from plugarr.orchestrator import build_config
from plugarr.wiring import Wirer

TEMPLATE = """\
# yaml-language-server: $schema=https://schemas.recyclarr.dev/v8/config-schema.json
################################################################################
## TRaSH Guides: WEB-1080p
##
## https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/#web-1080p
################################################################################

sonarr:
  web-1080p:
    base_url: Put your Sonarr URL here
    api_key: Put your API key here

    quality_definition:
      type: series

    quality_profiles:
      - name: WEB-1080p
"""


#: Sortie reelle de `recyclarr sync`, relevee sur un conteneur 8.7.1. C'est elle
#: qui est analysee pour annoncer les profils crees a la fin du cablage.
SYNC_OUTPUT = """\
[INF] hd-bluray-web: Processing Radarr server hd-bluray-web
[INF] hd-bluray-web: Total of 40 custom formats were synced
[INF] hd-bluray-web: Created 1 Profiles: ["HD Bluray + WEB"]
[INF] web-1080p: Total of 37 custom formats were synced
[INF] web-1080p: Created 1 Profiles: ["WEB-1080p"]
"""


def _template(tmp_path: Path, text: str = TEMPLATE, name: str = "web-1080p.yml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ----------------------------------------------------------------- remplissage


def test_fill_ecrit_adresse_et_cle(tmp_path):
    path = _template(tmp_path)
    result = recyclarr.fill(path, "http://sonarr:8989", "abc123", "sonarr")

    assert result.ok
    text = path.read_text(encoding="utf-8")
    assert "    base_url: http://sonarr:8989\n" in text
    assert "    api_key: abc123\n" in text
    assert "Put your" not in text


def test_fill_ne_touche_a_rien_d_autre(tmp_path):
    """Tout le contenu vient des TRaSH Guides et doit rester intact.

    C'est la garantie centrale du module : plugarr cable, il ne redige pas les
    profils. Une seule ligne modifiee ailleurs serait une reimplementation
    silencieuse du guide.
    """
    path = _template(tmp_path)
    recyclarr.fill(path, "http://sonarr:8989", "abc123", "sonarr")

    before = TEMPLATE.splitlines()
    after = path.read_text(encoding="utf-8").splitlines()

    # Meme nombre de lignes : les lignes vides autour des marqueurs sont du
    # contenu, pas du remplissage. Un `\s*$` gourmand les avalerait.
    assert len(after) == len(before)
    for index, (was, now) in enumerate(zip(before, after)):
        if "Put your" in was:
            assert now.startswith("    ") and "Put your" not in now
        else:
            assert now == was, f"ligne {index} modifiee"


def test_fill_accepte_un_antislash_dans_l_url(tmp_path):
    """Une url_base saisie a la main peut contenir un antislash.

    Passe tel quel a re.sub comme chaine de remplacement, il ferait lever
    « bad escape » et l'installation s'arreterait sur une erreur incomprehensible.
    """
    path = _template(tmp_path)
    result = recyclarr.fill(path, r"http://host:8989/sonarr\g<0>", "a\\b", "sonarr")

    assert result.ok
    text = path.read_text(encoding="utf-8")
    assert r"base_url: http://host:8989/sonarr\g<0>" in text
    assert "api_key: a\\b" in text


def test_fill_sur_un_fichier_deja_rempli_ne_signale_rien(tmp_path):
    """Rejouer le cablage ne doit pas ecraser une valeur choisie par l'utilisateur."""
    path = _template(tmp_path, TEMPLATE.replace("Put your Sonarr URL here", "http://moi:8989"))
    result = recyclarr.fill(path, "http://sonarr:8989", "abc123", "sonarr")

    assert not result.url_written and result.key_written
    assert "http://moi:8989" in path.read_text(encoding="utf-8")


# ------------------------------------------------------------------- lecture


def test_target_service_lit_le_yaml_pas_le_nom_de_fichier(tmp_path):
    """`hd-bluray-web` est un titre de template, pas un nom de service.

    Se fier au nom de fichier enverrait la cle de Radarr dans un fichier Sonarr.
    """
    path = _template(tmp_path, TEMPLATE, name="un-nom-qui-ne-dit-rien.yml")
    assert recyclarr.target_service(path) == "sonarr"

    radarr = _template(tmp_path, TEMPLATE.replace("sonarr:", "radarr:"), name="web-1080p.yml")
    assert recyclarr.target_service(radarr) == "radarr"


def test_target_service_repond_none_sur_un_fichier_muet(tmp_path):
    assert recyclarr.target_service(_template(tmp_path, "# vide\n")) is None
    assert recyclarr.target_service(tmp_path / "absent.yml") is None


def test_pending_markers_repere_un_marqueur_oublie(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "rempli.yml").write_text(
        TEMPLATE.replace("Put your Sonarr URL here", "http://sonarr:8989").replace(
            "Put your API key here", "abc"
        ),
        encoding="utf-8",
    )
    (configs / "oublie.yml").write_text(TEMPLATE, encoding="utf-8")

    assert [p.name for p in recyclarr.pending_markers(tmp_path)] == ["oublie.yml"]


def test_pending_markers_sans_dossier(tmp_path):
    assert recyclarr.pending_markers(tmp_path) == []


MANIFEST = """{
  "radarr": [
    {"template": "radarr/templates/hd-bluray-web.yml", "id": "hd-bluray-web"},
    {"template": "radarr/templates/german-hd-bluray-web.yml", "id": "radarr-german-hd-bluray-web"},
    {"template": "radarr/templates/sqp/sqp-1-1080p.yml", "id": "sqp-1-1080p"}
  ],
  "sonarr": [
    {"template": "sonarr/templates/web-1080p.yml", "id": "web-1080p"},
    {"template": "sonarr/templates/german-hd-bluray-web.yml", "id": "sonarr-german-hd-bluray-web"}
  ]
}"""


def _with_manifest(tmp_path: Path, text: str = MANIFEST) -> Path:
    manifest = tmp_path / recyclarr.MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(text, encoding="utf-8")
    return tmp_path


def test_un_nom_de_fichier_n_est_pas_un_identifiant(tmp_path):
    """C'est le manifeste qui fait foi, pas le contenu du dossier `templates/`.

    `sonarr/templates/german-hd-bluray-web.yml` s'appelle
    `sonarr-german-hd-bluray-web` pour `config create`, parce que Radarr a un
    fichier du meme nom. Lister les fichiers proposerait des noms refuses, et
    raterait au passage les templates ranges dans `sqp/`.
    """
    _with_manifest(tmp_path)

    assert recyclarr.template_names(tmp_path, "sonarr") == [
        "sonarr-german-hd-bluray-web",
        "web-1080p",
    ]
    assert "sqp-1-1080p" in recyclarr.template_names(tmp_path, "radarr")
    assert "german-hd-bluray-web" not in recyclarr.template_names(tmp_path, "radarr")


def test_template_names_sans_manifeste(tmp_path):
    """Recyclarr n'a pas encore tourne : rien sur disque, et surtout pas d'erreur."""
    assert recyclarr.template_names(tmp_path, "sonarr") == []


def test_un_manifeste_illisible_degrade_sans_interrompre(tmp_path):
    for garbage in ("", "pas du json", "[]", '{"sonarr": "web-1080p"}', '{"sonarr": [1, 2]}'):
        assert recyclarr.parse_manifest(garbage) == {}


def test_available_templates_prefere_le_disque(tmp_path, monkeypatch):
    """Ce que cette installation connait vaut mieux que ce que le depot publie."""
    _with_manifest(tmp_path)
    monkeypatch.setattr(
        recyclarr, "fetch_manifest", lambda **kw: (_ for _ in ()).throw(AssertionError("reseau"))
    )

    names, problem = recyclarr.available_templates(tmp_path)

    assert problem is None
    assert names["sonarr"] == ["sonarr-german-hd-bluray-web", "web-1080p"]


def test_available_templates_bascule_sur_le_reseau(tmp_path, monkeypatch):
    """Avant la premiere installation, le disque est vide : on demande au depot.

    C'est ce qui evite d'imposer le telechargement de l'image Recyclarr, puis une
    minute de clonage, avant meme le recapitulatif de l'assistant.
    """
    monkeypatch.setattr(recyclarr, "fetch_manifest", lambda **kw: ({"sonarr": ["web-2160p"]}, None))

    names, problem = recyclarr.available_templates(tmp_path)

    assert problem is None and names == {"sonarr": ["web-2160p"]}


# -------------------------------------------------------------------- cablage


def _cfg(tmp_path, services=("sonarr", "radarr", "recyclarr")):
    cfg = build_config(
        services=list(services),
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    cfg.project_dir = tmp_path
    return cfg


class FakeCompose:
    """Remplace `docker compose run` : ecrit ce que Recyclarr aurait ecrit."""

    def __init__(self, config_dir: Path, ok: bool = True, sync_ok: bool = True):
        self.config_dir = config_dir
        self.ok = ok
        self.sync_ok = sync_ok
        self.calls: list[list[str]] = []

    def creations(self) -> list[list[str]]:
        """Appels a `config create` seulement, hors synchronisations."""
        return [c for c in self.calls if c[:2] == ["config", "create"]]

    def __call__(self, project_dir, project_name):
        return self

    def run_once(self, service, args, timeout=600):
        self.calls.append(args)
        if args and args[0] == "sync":
            if not self.sync_ok:
                return False, "[ERR] Sonarr injoignable"
            return True, SYNC_OUTPUT
        if not self.ok:
            return False, "recyclarr: template inconnu"
        configs = self.config_dir / "configs"
        configs.mkdir(parents=True, exist_ok=True)
        for index, name in enumerate(args):
            if name != "--template":
                continue
            title = args[index + 1]
            body = TEMPLATE if "1080p" in title else TEMPLATE.replace("sonarr:", "radarr:")
            (configs / f"{title}.yml").write_text(body, encoding="utf-8")
        return True, ""


def _patch_compose(monkeypatch, fake):
    monkeypatch.setattr("plugarr.runner.Compose", fake)


def test_step_recyclarr_remplit_chaque_fichier(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    config_dir = Path(cfg.config_path("recyclarr"))
    _patch_compose(monkeypatch, FakeCompose(config_dir))

    result = Wirer(cfg).step_recyclarr()

    assert result.ok, result.warnings
    assert "web-1080p -> sonarr" in result.detail
    assert "hd-bluray-web -> radarr" in result.detail

    sonarr = (config_dir / "configs" / "web-1080p.yml").read_text(encoding="utf-8")
    assert f"api_key: {cfg.services['sonarr'].api_key}" in sonarr
    assert "base_url: http://sonarr:8989" in sonarr

    radarr = (config_dir / "configs" / "hd-bluray-web.yml").read_text(encoding="utf-8")
    assert f"api_key: {cfg.services['radarr'].api_key}" in radarr
    assert "base_url: http://radarr:7878" in radarr


def test_step_recyclarr_n_ecrit_que_pour_les_services_installes(tmp_path, monkeypatch):
    """Sans Radarr, aucun template Radarr ne doit etre demande."""
    cfg = _cfg(tmp_path, services=("sonarr", "recyclarr"))
    _patch_compose(monkeypatch, FakeCompose(Path(cfg.config_path("recyclarr"))))

    result = Wirer(cfg).step_recyclarr()

    assert result.ok
    assert "radarr" not in result.detail


def test_step_recyclarr_signale_un_echec_de_generation(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _patch_compose(monkeypatch, FakeCompose(Path(cfg.config_path("recyclarr")), ok=False))

    result = Wirer(cfg).step_recyclarr()

    assert not result.ok
    assert "template inconnu" in result.warnings[0]


def test_step_recyclarr_signale_un_fichier_orphelin(tmp_path, monkeypatch):
    """Un template laisse par une installation precedente garde ses marqueurs.

    Cas reel : l'utilisateur avait Radarr, il l'a retire. Le fichier reste dans
    `configs/`, plugarr ne le remplit pas puisque le service n'existe plus, et
    `recyclarr sync` echoue dessus avec un message obscur. On le dit ici, avec le
    nom du fichier.
    """
    cfg = _cfg(tmp_path, services=("sonarr", "recyclarr"))
    config_dir = Path(cfg.config_path("recyclarr"))
    inner = FakeCompose(config_dir)

    class WithOrphan(FakeCompose):
        def run_once(self, service, args, timeout=600):
            ok, message = inner.run_once(service, args, timeout)
            (config_dir / "configs" / "hd-bluray-web.yml").write_text(
                TEMPLATE.replace("sonarr:", "radarr:"), encoding="utf-8"
            )
            return ok, message

    _patch_compose(monkeypatch, WithOrphan(config_dir))
    result = Wirer(cfg).step_recyclarr()

    assert not result.ok
    assert any("hd-bluray-web.yml" in w for w in result.warnings)
    # Le fichier orphelin n'a pas ete rempli au passage : Radarr n'est pas la.
    assert "Put your" in (config_dir / "configs" / "hd-bluray-web.yml").read_text(encoding="utf-8")


def test_step_recyclarr_sans_template_ne_fait_rien(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.recyclarr_templates = {"sonarr": "", "radarr": ""}
    _patch_compose(monkeypatch, FakeCompose(Path(cfg.config_path("recyclarr"))))

    result = Wirer(cfg).step_recyclarr()

    assert result.ok and not result.created


def test_recyclarr_est_cable_avant_autobrr(tmp_path):
    """L'ordre compte peu fonctionnellement, mais un profil pose avant qu'autobrr
    ne pousse des releases evite un premier passage a vide."""
    cfg = _cfg(tmp_path, services=("sonarr", "radarr", "recyclarr", "autobrr", "prowlarr"))
    names = [step.name for step in Wirer(cfg).build_plan()]

    assert names.index("recyclarr/profils") < names.index("autobrr/clients")


# ------------------------------------------------------------------- catalogue


def test_recyclarr_ne_publie_aucun_port(tmp_path):
    """Recyclarr n'a pas d'interface web : lui publier un port bloquerait un port
    de l'hote pour rien, et ferait echouer le preflight sur une machine chargee."""
    cfg = _cfg(tmp_path)
    document = compose.build_compose(cfg)

    assert "ports" not in document["services"]["recyclarr"]
    assert catalog.get("recyclarr").internal_port == 0


def test_recyclarr_tourne_sous_le_compte_de_l_utilisateur(tmp_path):
    """Son image tourne en 1000:1000 EN DUR et ne lit pas PUID.

    Tant que l'installation se faisait sous un compte a 1000, la coincidence
    tenait. Une installation en `sudo` — obligatoire sous `/volume1`, qui
    appartient a root — creait le dossier en root, et Recyclarr se faisait jeter
    a l'ecriture, sans interface pour le dire.

    Verifie sur le banc le 2026-09-20 avec l'image 8.7.1 : dossier a root et
    conteneur en 1000:1000, `config create` sort en code 1 sur une exception
    .NET ; dossier a 1000:10 et conteneur force en 1000:10, il sort en code 0 et
    ecrit `configs/web-1080p.yml`.
    """
    cfg = _cfg(tmp_path)
    cfg.puid, cfg.pgid = 1000, 10

    bloc = compose.build_compose(cfg)["services"]["recyclarr"]

    assert bloc["user"] == "1000:10"
    # Et son dossier doit lui revenir : le `user` seul ne suffit pas si le
    # dossier reste a root.
    from plugarr.layout import SANS_PUID

    assert "recyclarr" in SANS_PUID


def test_recyclarr_tire_un_arr():
    """Seul, Recyclarr n'a rien a synchroniser."""
    assert "sonarr" in catalog.resolve_dependencies(["recyclarr"])
    # Radarr suffit aussi : la dependance est un « au moins un ».
    resolved = catalog.resolve_dependencies(["recyclarr", "radarr"])
    assert "sonarr" not in resolved and "radarr" in resolved


# --------------------------------------------------------------- page d'acces


def test_la_page_d_acces_ne_propose_pas_de_lien_vers_le_port_0(tmp_path):
    """Recyclarr n'a pas d'interface web.

    Une carte cliquable menant a `http://hote:0` ferait conclure au lecteur que
    l'installation a echoue, alors qu'elle a reussi. Constate sur une vraie page
    generee : le lien etait la, sous une note disant « Aucune interface web ».
    """
    from plugarr import dashboard

    cfg = _cfg(tmp_path)
    cfg.host = "192.168.1.10"
    page = dashboard.render(cfg)

    # Viser le lien, pas la page entiere : elle porte un horodatage, et « 08:02 »
    # contient « :0 ». Une assertion trop large echouait une minute sur dix.
    assert "192.168.1.10:0" not in page
    assert "Recyclarr" in page
    assert "tache de fond, sans interface" in page
    # Sonarr, lui, garde son lien.
    assert 'href="http://192.168.1.10:8989"' in page


# ---------------------------------------------------------------- idempotence


def test_step_recyclarr_rejoue_ne_redemande_rien(tmp_path, monkeypatch):
    """`wire` est idempotent, et Recyclarr refuse d'ecraser un fichier existant.

    Constate en conditions reelles : rejouer le cablage apres une installation
    echouait sur « The file /config/configs/hd-bluray-web.yml already exists ».
    Le refus de Recyclarr est legitime, le fichier a pu etre modifie a la main.
    C'est a plugarr de ne demander que ce qui manque.
    """
    cfg = _cfg(tmp_path)
    fake = FakeCompose(Path(cfg.config_path("recyclarr")))
    _patch_compose(monkeypatch, fake)

    first = Wirer(cfg).step_recyclarr()
    second = Wirer(cfg).step_recyclarr()

    assert first.ok and second.ok
    assert len(fake.creations()) == 1, "le second passage a redemande une generation"
    assert "2 deja configures" in second.detail
    assert not second.created


def test_step_recyclarr_ne_regenere_que_ce_qui_manque(tmp_path, monkeypatch):
    """Radarr ajoute apres coup : seul son template doit etre demande."""
    cfg = _cfg(tmp_path)
    config_dir = Path(cfg.config_path("recyclarr"))
    fake = FakeCompose(config_dir)
    _patch_compose(monkeypatch, fake)

    Wirer(cfg).step_recyclarr()
    (config_dir / "configs" / "hd-bluray-web.yml").unlink()
    Wirer(cfg).step_recyclarr()

    assert fake.creations()[1] == ["config", "create", "--template", "hd-bluray-web"]
    # Le fichier Sonarr n'a pas ete regenere : son contenu rempli est intact.
    sonarr = (config_dir / "configs" / "web-1080p.yml").read_text(encoding="utf-8")
    assert "Put your" not in sonarr


def test_le_rapport_n_affiche_pas_d_url_pour_un_service_sans_interface(tmp_path):
    """`http://hote:0` dans le tableau final se lit comme une adresse a ouvrir."""
    from rich.console import Console

    from plugarr import report

    cfg = _cfg(tmp_path)
    cfg.host = "192.168.1.10"
    recorder = Console(record=True, width=200, force_terminal=False)
    original, report.console = report.console, recorder
    try:
        report.print_summary(cfg)
    finally:
        report.console = original
    text = recorder.export_text()

    assert "192.168.1.10:0" not in text
    assert "tache de fond" in text
    assert "192.168.1.10:8989" in text


# ------------------------------------------------- premiere synchronisation


def test_le_cablage_declenche_la_premiere_synchronisation(tmp_path, monkeypatch):
    """Recyclarr ne synchronise qu'a sa planification quotidienne.

    Sans ce premier passage, l'utilisateur ouvre Sonarr juste apres
    l'installation, n'y voit aucun profil TRaSH et en conclut que rien n'a
    marche. La fonctionnalite doit etre visible a la fin du cablage.
    """
    cfg = _cfg(tmp_path)
    fake = FakeCompose(Path(cfg.config_path("recyclarr")))
    _patch_compose(monkeypatch, fake)

    result = Wirer(cfg).step_recyclarr()

    assert ["sync"] in fake.calls
    assert fake.calls[-1] == ["sync"], "la synchro doit venir APRES la generation"
    # Les profils reellement crees sont annonces, lus dans la sortie de Recyclarr.
    assert "synchronise" in result.detail
    assert "WEB-1080p" in result.detail and "HD Bluray + WEB" in result.detail


def test_une_synchro_echouee_avertit_sans_faire_echouer_le_cablage(tmp_path, monkeypatch):
    """Les fichiers sont ecrits et la planification quotidienne reessaiera.

    Faire echouer le cablage pour cela afficherait « 10/11 liens » alors que les
    onze liens sont bien poses.
    """
    cfg = _cfg(tmp_path)
    _patch_compose(monkeypatch, FakeCompose(Path(cfg.config_path("recyclarr")), sync_ok=False))

    result = Wirer(cfg).step_recyclarr()

    assert result.ok, "le cablage lui-meme a reussi"
    assert any("synchronisation echouee" in w for w in result.warnings)
    assert any("reessaiera" in w for w in result.warnings)


def test_pas_de_synchro_si_rien_n_a_ete_cable(tmp_path, monkeypatch):
    """Sans configuration remplie, synchroniser n'aurait aucun sens."""
    cfg = _cfg(tmp_path)
    cfg.recyclarr_templates = {"sonarr": "", "radarr": ""}
    fake = FakeCompose(Path(cfg.config_path("recyclarr")))
    _patch_compose(monkeypatch, fake)

    Wirer(cfg).step_recyclarr()

    assert fake.calls == []


# ------------------------------------------------- la cause, quand ca echoue


#: Sortie REELLE de `recyclarr:8.7.1 config create --template web-1080p` avec un
#: dossier qui n'appartient pas au conteneur. Relevee sur le banc le 2026-09-20,
#: en reproduisant le cas remonte par un membre sur Synology.
SORTIE_REELLE_ECHEC = (
    "[ERR] Exiting due to fatal error: An exception was thrown while activating "
    "Recyclarr.Cli.Migration.MigrationExecutor\n"
    "Fatal error: An exception was thrown while activating \n"
    "Recyclarr.Cli.Migration.MigrationExecutor -> \n"
    "λ:Autofac.Features.Metadata.Meta`1[[Recyclarr.Cli.Migration.Steps.IMigrationStep\n"
    ", recyclarr, Version=8.7.1.0, Culture=neutral, PublicKeyToken=null]][] -> \n"
    "λ:System.Object -> Recyclarr.Cli.Migration.Steps.DeleteRepoDirMigrationStep -> \n"
    "λ:Recyclarr.Platform.IAppPaths.\n"
)


def test_la_cause_ne_se_prend_plus_le_dernier_fragment_de_trace():
    """Le defaut remonte le 2026-09-20, reproduit sur le banc.

    Tout est dans la PREMIERE ligne, tagguee [ERR]. Les six suivantes deroulent
    une chaine de types .NET coupee au milieu, et c'est la derniere que PlugArr
    affichait : exacte, et sans le moindre interet pour qui doit reparer.
    """
    ancien = SORTIE_REELLE_ECHEC.splitlines()[-1]
    assert ancien == "λ:Recyclarr.Platform.IAppPaths."
    assert "error" not in ancien.lower()

    obtenu = recyclarr.cause(SORTIE_REELLE_ECHEC)

    assert obtenu.startswith("[ERR]")
    assert "fatal error" in obtenu.lower()


def test_la_cause_survit_a_une_ligne_vide_finale():
    """L'autre facon de ne rien dire : un dernier element vide."""
    sortie = "[ERR] Access to the path '/config' is denied.\n\n"

    assert sortie.splitlines()[-1] == ""
    assert "denied" in recyclarr.cause(sortie)


def test_la_cause_prefere_les_lignes_graves():
    """Recyclarr raconte beaucoup ; seules [ERR] et [FTL] disent pourquoi il
    s'arrete."""
    sortie = (
        "[INF] Loaded config\n"
        "[ERR] Permission denied\n"
        "[INF] Cleaning up\n"
        "[INF] Done\n"
    )

    obtenu = recyclarr.cause(sortie)

    assert obtenu == "[ERR] Permission denied"
    assert "Cleaning up" not in obtenu


def test_la_cause_retombe_sur_les_dernieres_lignes_utiles():
    """Une panne peut ne porter aucun niveau : une trace .NET, par exemple."""
    sortie = "Unhandled exception.\nSystem.UnauthorizedAccessException: denied\n\n"

    obtenu = recyclarr.cause(sortie)

    assert "UnauthorizedAccessException" in obtenu


def test_le_bruit_de_docker_ne_passe_pas_pour_une_cause():
    """`docker compose run` encadre la sortie de lignes qui n'apprennent rien.
    Si elles arrivaient les dernieres, elles volaient la place de la vraie."""
    sortie = "[ERR] Permission denied\nPull complete\nStatus: Downloaded newer image\n"

    assert recyclarr.cause(sortie) == "[ERR] Permission denied"


def test_une_sortie_vide_le_dit_au_lieu_de_ne_rien_dire():
    for sortie in ("", "   ", "\n\n"):
        assert recyclarr.cause(sortie).strip(), f"vide pour {sortie!r}"


def test_l_echec_de_generation_porte_desormais_la_cause(tmp_path, monkeypatch):
    """Le bout en bout : ce que l'utilisateur lit dans son rapport."""
    cfg = _cfg(tmp_path)
    faux = FakeCompose(Path(cfg.config_path("recyclarr")), ok=False)
    faux.run_once = lambda service, args, timeout=600: (
        False,
        "[INF] Creating config file\n[ERR] Access to the path '/config/configs' is denied.\n",
    )
    _patch_compose(monkeypatch, faux)

    result = Wirer(cfg).step_recyclarr()

    assert not result.ok
    assert "denied" in result.warnings[0], result.warnings
