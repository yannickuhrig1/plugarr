"""PlugArr Administration : ce que le gestionnaire montre, ce qu'il permet, ce qu'il refuse.

Docker n'est pas sollicite : les appels a Compose sont remplaces, et une pile
distante est jouee par une fausse session SSH. Le serveur HTTP, lui, est le
vrai, interroge comme le fait la page.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import httpx
import pytest

from plugarr import (
    catalog,
    chemins,
    compose,
    distantes,
    gestionnaire,
    migrations,
    orchestrator,
    registre,
    remote_install,
)

WEB = Path(gestionnaire.__file__).parent / "web"


@pytest.fixture(autouse=True)
def _pas_de_docker(monkeypatch):
    """Le releve de fond interroge Docker : ici, une pile arretee sans bruit.

    Aussi `running_project_dir` : sur un poste ou tourne une vraie pile
    nommee `plugarr`, chaque installation d'essai serait sinon vue comme
    « lancee depuis un autre dossier ».
    """
    monkeypatch.setattr(gestionnaire, "running_project_dir", lambda nom: None)
    monkeypatch.setattr(
        gestionnaire.admin,
        "status_payload",
        lambda cfg, runner: {
            "services": [
                {"id": sid, "name": sid, "state": "exited", "status": "Exited", "up": False}
                for sid in cfg.services
            ],
            "engine_available": True,
        },
    )


def _config(tmp_path, **extra):
    cfg = orchestrator.build_config(
        services=["sonarr", "jellyfin"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    for champ, valeur in extra.items():
        setattr(cfg, champ, valeur)
    return cfg


@pytest.fixture
def gestion():
    ouvertes: list[str] = []
    g = gestionnaire.Gestionnaire(ouvrir=lambda url: ouvertes.append(url) or True, verifier_maj=False)
    g.ouvertes = ouvertes
    g.demarrer()
    yield g
    g.arreter()


def _client(g) -> httpx.Client:
    return httpx.Client(
        base_url=f"http://127.0.0.1:{g.serveur.server_port}",
        headers={"Authorization": f"Bearer {g.jeton}"},
        timeout=10,
    )


def _attendre(condition, delai=10.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.05)
    return False


# ------------------------------------------------------------------- securite


def test_la_page_et_ses_textes_se_servent_sans_jeton(gestion):
    with httpx.Client(base_url=f"http://127.0.0.1:{gestion.serveur.server_port}") as client:
        assert client.get("/").status_code == 200
        assert client.get("/gestionnaire.js").status_code == 200
        assert client.get("/wizard.css").status_code == 200
        assert "titre" in client.get("/api/textes").json()["textes"]


def test_l_etat_exige_le_jeton(gestion):
    with httpx.Client(base_url=f"http://127.0.0.1:{gestion.serveur.server_port}") as client:
        assert client.get("/api/etat").status_code == 401
        assert client.get("/api/etat", headers={"Authorization": "Bearer faux"}).status_code == 401
        assert client.post("/api/quitter").status_code == 401
    assert not gestion.arret.is_set()


def test_un_hote_etranger_est_refuse(gestion):
    """Rebond DNS : une page tierce qui resout son nom vers 127.0.0.1."""
    with _client(gestion) as client:
        reponse = client.get("/api/etat", headers={"Host": "exemple.org"})
    assert reponse.status_code == 403


def test_une_origine_etrangere_est_refusee(gestion):
    with _client(gestion) as client:
        reponse = client.post("/api/actualiser", headers={"Origin": "https://exemple.org"})
    assert reponse.status_code == 403


def test_la_politique_de_contenu_interdit_le_script_en_ligne(gestion):
    with httpx.Client(base_url=f"http://127.0.0.1:{gestion.serveur.server_port}") as client:
        entete = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in entete
    assert "unsafe-inline" not in entete


def test_un_corps_demesure_est_refuse(gestion):
    with _client(gestion) as client:
        reponse = client.post(
            "/api/instances/ssh-0123456789ab/connexion",
            content=b"x" * (gestionnaire.CORPS_MAX + 1),
            headers={"Content-Type": "application/json"},
        )
    assert reponse.status_code == 409


# --------------------------------------------------------------------- textes


def test_chaque_texte_demande_par_la_page_existe():
    """Un `T.cle` absent afficherait `undefined` dans un bouton."""
    js = (WEB / "gestionnaire.js").read_text(encoding="utf-8")
    html = (WEB / "gestionnaire.html").read_text(encoding="utf-8")
    textes = gestionnaire.textes()

    demandes = set(re.findall(r"\bT\.([A-Za-z]+)", js))
    demandes |= set(re.findall(r'data-t="([A-Za-z]+)"', html))
    assert demandes, "le releve ne trouve rien : il ne prouve plus rien"
    assert sorted(demandes - set(textes)) == []


def test_chaque_etat_et_chaque_tache_a_son_libelle():
    textes = gestionnaire.textes()
    js = (WEB / "gestionnaire.js").read_text(encoding="utf-8")
    bloc = re.search(r"const CLASSES = \{(.*?)\};", js, re.DOTALL).group(1)
    etats = re.findall(r"'?([a-z-]+)'?\s*:", bloc)
    assert "en-marche" in etats and "deconnectee" in etats
    for nom in etats:
        assert f"etat-{nom}" in textes, nom
    for statut in ("en-cours", "reussie", "echouee"):
        assert f"tache-{statut}" in textes
    for action in (*gestionnaire.ACTIONS_LOCALES, *gestionnaire.ACTIONS_DISTANTES):
        assert action in textes, action


def test_les_textes_suivent_la_langue():
    from plugarr import i18n

    i18n.utiliser("en")
    try:
        assert gestionnaire.textes()["nouvelle"] == "New installation"
    finally:
        i18n.utiliser("fr")


# ------------------------------------------------------------------ instances


def test_une_installation_locale_apparait_avec_son_pack(tmp_path, gestion):
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    gestion.relever()

    with _client(gestion) as client:
        assert _attendre(lambda: client.get("/api/etat").json()["instances"][0]["etat"] == "arretee")
        [vue] = client.get("/api/etat").json()["instances"]

    assert vue["type"] == "local"
    assert vue["lieu"] == str((tmp_path / "projet").resolve())
    assert vue["pack"] == {"retenus": [], "ecartes": []}
    assert vue["range"] is False


def test_une_installation_rangee_est_reconnue(tmp_path, gestion):
    compose.write_artifacts(_config(tmp_path), chemins.instance_par_defaut())

    [vue] = gestion.instances()

    assert vue["range"] is True


def test_le_pack_montre_ce_qui_avance(tmp_path, gestion):
    cfg = _config(tmp_path)
    image = catalog.get("sonarr").image
    depot, _, tag = image.partition("@")[0].rpartition(":")
    cfg.services["sonarr"].image = f"{depot}:0.0.1"
    compose.write_artifacts(cfg, tmp_path / "projet")

    [inst] = registre.lire()
    etat = gestionnaire.etat_local(inst)

    [retenu] = etat["pack"]["retenus"]
    assert retenu["service"] == "sonarr"
    assert retenu["installee"] == "0.0.1"
    assert retenu["catalogue"] == tag


def test_une_pile_du_meme_nom_lancee_ailleurs_n_est_pas_prise_pour_la_sienne(
    tmp_path, monkeypatch
):
    """Constate le 26/09/2026 : une vieille entree du registre affichait
    « 5 sur 5 en marche » avec les conteneurs d'une pile lancee depuis `dist\\`."""
    ailleurs = str(tmp_path / "dist")
    monkeypatch.setattr(gestionnaire, "running_project_dir", lambda nom: ailleurs)
    monkeypatch.setattr(
        gestionnaire.admin, "status_payload", lambda *a: pytest.fail("rien ne doit etre lu")
    )
    compose.write_artifacts(_config(tmp_path), tmp_path / "vieille")
    [inst] = registre.lire()

    etat = gestionnaire.etat_local(inst)
    assert etat["etat"] == "autre-dossier"
    assert etat["ailleurs"] == ailleurs

    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: pytest.fail("aucune console"),
        popen=lambda *a, **k: pytest.fail("aucune commande"),
        verifier_maj=False,
    )
    for action in gestionnaire.ACTIONS_LOCALES:
        with pytest.raises(gestionnaire.ActionRefusee, match="autre dossier"):
            g.action(inst.ident, action)
    with pytest.raises(gestionnaire.ActionRefusee, match="autre dossier"):
        g.ouvrir_console(inst.ident)


def test_un_releve_ne_demande_qu_une_fois_par_nom_de_pile(tmp_path, monkeypatch):
    questions: list[str] = []
    monkeypatch.setattr(
        gestionnaire, "running_project_dir", lambda nom: questions.append(nom) or None
    )
    for dossier in ("a", "b", "c"):
        compose.write_artifacts(_config(tmp_path), tmp_path / dossier)

    dossiers: dict = {}
    for inst in registre.lire():
        gestionnaire.etat_local(inst, dossiers)

    assert questions == ["plugarr"]


def test_sa_propre_pile_reste_pilotable(tmp_path, monkeypatch):
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)
    [inst] = registre.lire()
    # Docker ecrit le dossier a sa facon : casse et separateurs peuvent differer.
    monkeypatch.setattr(
        gestionnaire, "running_project_dir", lambda nom: str(inst.project_dir).upper()
        if sys.platform == "win32" else str(inst.project_dir)
    )

    assert gestionnaire.etat_local(inst)["etat"] == "arretee"


def test_une_installation_effacee_est_signalee(tmp_path, gestion):
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    (tmp_path / "projet" / "stack.yml").unlink()

    [inst] = registre.lire()

    assert gestionnaire.etat_local(inst) == {"etat": "introuvable"}


def test_une_distante_apparait_sans_secret_et_deconnectee(gestion):
    distantes.enregistrer(
        distantes.Distante(
            host="nas.local", port=22, user="yannick", empreinte="SHA256:abc",
            project_dir="/home/yannick/plugarr", console_port=7373,
        )
    )

    with _client(gestion) as client:
        [vue] = client.get("/api/etat").json()["instances"]

    assert vue["type"] == "ssh"
    assert vue["etat"] == "deconnectee"
    assert vue["connecte"] is False
    assert vue["a_console"] is True
    assert vue["empreinte"] == "SHA256:abc"


def test_renommer_puis_oublier_une_locale_ne_supprime_rien(tmp_path, gestion):
    projet = tmp_path / "projet"
    compose.write_artifacts(_config(tmp_path), projet)
    [inst] = registre.lire()

    with _client(gestion) as client:
        assert client.post(f"/api/instances/{inst.ident}/renommer", json={"nom": " Ce  PC "}).status_code == 200
        assert gestion.instances()[0]["nom"] == "Ce PC"
        assert client.post(f"/api/instances/{inst.ident}/oublier").status_code == 200

    assert registre.lire() == []
    assert (projet / "stack.yml").is_file()


def test_une_action_inconnue_est_refusee(tmp_path, gestion):
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    with _client(gestion) as client:
        reponse = client.post(f"/api/instances/{inst.ident}/supprimer-tout")

    assert reponse.status_code == 409


# --------------------------------------------------------------------- taches


class _Processus:
    def __init__(self, lignes: list[bytes], code: int):
        self.stdout = io.BytesIO(b"".join(lignes))
        self._code = code

    def wait(self):
        return self._code


def test_une_commande_longue_passe_par_plugarr_et_se_journalise(tmp_path):
    lances: list[list[str]] = []

    def popen(args, **options):
        lances.append(args)
        assert options["stdout"] is gestionnaire.subprocess.PIPE
        return _Processus([b"\x1b[32mOK\x1b[0m sonarr 4.0\n", "etape \xe9\n".encode()], 0)

    g = gestionnaire.Gestionnaire(ouvrir=lambda u: True, popen=popen, verifier_maj=False)
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    tache = g.action(inst.ident, "diagnostic")
    assert _attendre(lambda: tache.statut != "en-cours")

    assert tache.statut == "reussie"
    assert tache.lignes == ["OK sonarr 4.0", "etape \xe9"]
    assert lances == [[*chemins.moteur(), "doctor", "--project-dir", str(inst.project_dir)]]


def test_un_code_de_sortie_non_nul_fait_echouer_la_tache(tmp_path):
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, popen=lambda *a, **k: _Processus([b"erreur\n"], 2),
        verifier_maj=False,
    )
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    tache = g.action(inst.ident, "sauvegarder")
    assert _attendre(lambda: tache.statut != "en-cours")

    assert tache.statut == "echouee"
    assert "code 2" in tache.message


def test_une_seule_operation_a_la_fois_par_installation(tmp_path):
    import threading

    libere = threading.Event()

    class Lent(_Processus):
        def wait(self):
            libere.wait(10)
            return 0

    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, popen=lambda *a, **k: Lent([], 0), verifier_maj=False
    )
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    premiere = g.action(inst.ident, "pack")
    with pytest.raises(gestionnaire.ActionRefusee):
        g.action(inst.ident, "sauvegarder")
    libere.set()
    assert _attendre(lambda: premiere.statut == "reussie")
    assert g.action(inst.ident, "diagnostic")


def test_la_mise_a_jour_du_pack_passe_par_upgrade_sans_question(tmp_path):
    lances: list[list[str]] = []
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True,
        popen=lambda args, **k: lances.append(args) or _Processus([], 0),
        verifier_maj=False,
    )
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    tache = g.action(inst.ident, "pack")
    assert _attendre(lambda: tache.statut == "reussie")

    assert lances[0][-4:] == ["upgrade", "--project-dir", str(inst.project_dir), "--yes"]


# ------------------------------------------------------------------ deplacement


def test_ranger_deplace_les_fichiers_sans_rien_laisser_ni_supprimer(tmp_path, monkeypatch):
    """Le cas du double-clic dans Telechargements, rattrape apres coup."""
    appels: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        gestionnaire.Compose, "down", lambda self, **k: appels.append(("down", self.dir)) or (True, "")
    )
    monkeypatch.setattr(
        gestionnaire.Compose, "up", lambda self, **k: appels.append(("up", self.dir)) or (True, "")
    )
    telechargements = tmp_path / "Telechargements"
    telechargements.mkdir()
    (telechargements / "plugarr.exe").write_bytes(b"MZ")
    (telechargements / "photo.jpg").write_bytes(b"perso")
    cfg = _config(tmp_path, username="yannick")
    compose.write_artifacts(cfg, telechargements)
    compose.write_artifacts(cfg, telechargements)  # un historique, comme en vrai
    [inst] = registre.lire()

    g = gestionnaire.Gestionnaire(ouvrir=lambda u: True, verifier_maj=False)
    tache = g.action(inst.ident, "deplacer")
    assert _attendre(lambda: tache.statut != "en-cours"), tache.lignes
    assert tache.statut == "reussie", tache.lignes

    nouveau = chemins.instance_par_defaut()
    assert sorted(p.name for p in telechargements.iterdir()) == ["photo.jpg", "plugarr.exe"]
    assert (nouveau / "stack.yml").is_file()
    assert (nouveau / ".env").is_file()
    assert migrations.lire(nouveau / "stack.yml")[0].username == "yannick"
    assert str(nouveau) in (nouveau / ".env").read_text(encoding="utf-8")
    assert [e.project_dir for e in registre.lire()] == [nouveau.resolve()]
    assert appels == [("down", telechargements.resolve()), ("up", nouveau)]


def test_ranger_ne_deplace_rien_si_docker_refuse_l_arret(tmp_path, monkeypatch):
    monkeypatch.setattr(gestionnaire.Compose, "down", lambda self, **k: (False, "daemon absent"))
    projet = tmp_path / "Telechargements"
    compose.write_artifacts(_config(tmp_path), projet)
    [inst] = registre.lire()

    g = gestionnaire.Gestionnaire(ouvrir=lambda u: True, verifier_maj=False)
    tache = g.action(inst.ident, "deplacer")
    assert _attendre(lambda: tache.statut != "en-cours")

    assert tache.statut == "echouee"
    assert (projet / "stack.yml").is_file()
    assert not chemins.instance_par_defaut().exists()


# -------------------------------------------------------------------- distantes


class _FausseSession:
    """Un serveur SSH joue en memoire : une pile PlugArr, et `docker ps`."""

    def __init__(self, stack_yaml: str, empreinte: str = "SHA256:abc", conteneurs=()):
        self.fingerprint = empreinte
        self.stack_yaml = stack_yaml
        self.conteneurs = list(conteneurs)
        self.commandes: list[str] = []
        self.fermee = False

    def run(self, command, *, stdin=None):
        import base64
        import hashlib

        self.commandes.append(command)
        if command.startswith("docker ps"):
            return 0, "\n".join(json.dumps(c) for c in self.conteneurs), ""
        if "stack_b64" in command:
            donnees = self.stack_yaml.encode("utf-8")
            sortie = (
                "exists=1\n"
                f"stack_sha={hashlib.sha256(donnees).hexdigest()}\n"
                "managed=1\n"
                f"stack_b64={base64.b64encode(donnees).decode()}\n"
            )
            return 0, sortie, ""
        return 0, "", ""

    def transport(self):
        return None

    def close(self):
        self.fermee = True


def _distante_enregistree(**extra):
    valeurs = {
        "host": "nas.local", "port": 22, "user": "yannick", "empreinte": "SHA256:abc",
        "project_dir": "/home/yannick/plugarr", "console_port": 7373, "uid": 1000, "gid": 1000,
    }
    valeurs.update(extra)
    distante = distantes.Distante(**valeurs)
    distantes.enregistrer(distante)
    return distante


def test_une_empreinte_changee_refuse_la_connexion(tmp_path):
    distante = _distante_enregistree()
    session = _FausseSession(compose.render_stack(_config(tmp_path)), empreinte="SHA256:autre")
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, connecter=lambda t, c: session, verifier_maj=False
    )

    with pytest.raises(gestionnaire.ActionRefusee, match="empreinte SSH"):
        g.connecter(distante.ident, {"password": "secret"})

    assert session.fermee
    assert distante.ident not in g.connexions


def test_une_connexion_lit_la_pile_et_ne_divulgue_aucun_secret(tmp_path):
    cfg = _config(tmp_path)
    distante = _distante_enregistree()
    conteneurs = [
        {"Labels": "com.docker.compose.project=plugarr,com.docker.compose.service=sonarr",
         "State": "running", "Status": "Up 2 hours (healthy)"},
        {"Labels": "com.docker.compose.service=jellyfin,com.docker.compose.project=plugarr",
         "State": "running", "Status": "Up 1 minute (health: starting)"},
    ]
    session = _FausseSession(compose.render_stack(cfg), conteneurs=conteneurs)
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, connecter=lambda t, c: session, verifier_maj=False
    )

    g.connecter(distante.ident, {"password": "MotDePasseSSH-9"})
    g._relever_distante(distante.ident, g.connexions[distante.ident])
    [vue] = g.instances()

    assert vue["connecte"] is True
    assert vue["etat"] == "partielle"
    assert {s["id"]: s["up"] for s in vue["services"]} == {"sonarr": True, "jellyfin": False}
    publie = json.dumps(g.vue())
    assert "MotDePasseSSH-9" not in publie
    for instance in cfg.services.values():
        if instance.password:
            assert instance.password not in publie


def test_sans_mot_de_passe_ni_cle_rien_n_est_tente(tmp_path):
    distante = _distante_enregistree()
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True,
        connecter=lambda t, c: pytest.fail("aucune connexion ne doit etre tentee"),
        verifier_maj=False,
    )

    with pytest.raises(gestionnaire.ActionRefusee):
        g.connecter(distante.ident, {})


def test_le_pack_distant_redeploie_la_pile_du_serveur_avec_les_images_du_catalogue(
    tmp_path, monkeypatch
):
    cfg = _config(tmp_path, username="distant")
    depot = catalog.get("sonarr").image.partition("@")[0].rpartition(":")[0]
    cfg.services["sonarr"].image = f"{depot}:0.0.1"
    stack = compose.render_stack(cfg)
    distante = _distante_enregistree()
    session = _FausseSession(stack)
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, connecter=lambda t, c: session, verifier_maj=False
    )
    g.connecter(distante.ident, {"password": "x"})
    envoyes: list[remote_install.RemoteDeployment] = []

    def deploy(target, credentials, deployment, *, connect, on_event=None):
        envoyes.append(deployment)
        assert target.expected_fingerprint == "SHA256:abc"
        on_event({"kind": "step", "name": "Sonarr", "ok": True})
        return remote_install.RemoteDeployResult(status="done", events=())

    monkeypatch.setattr(gestionnaire.remote_install, "deploy", deploy)

    tache = g.action(distante.ident, "pack")
    assert _attendre(lambda: tache.statut != "en-cours")

    assert tache.statut == "reussie", tache.lignes
    [envoi] = envoyes
    assert envoi.replace_existing is True
    assert envoi.project_dir == "/home/yannick/plugarr"
    import hashlib

    assert envoi.expected_existing_sha == hashlib.sha256(stack.encode()).hexdigest()
    nouvelle, _ = migrations.lire_texte(envoi.stack_yaml)
    assert nouvelle.services["sonarr"].image == catalog.get("sonarr").image
    assert nouvelle.username == "distant"
    assert not session.fermee, "la session du gestionnaire doit survivre au deploiement"


def test_la_console_distante_exige_une_connexion(gestion):
    distante = _distante_enregistree()

    with pytest.raises(gestionnaire.ActionRefusee, match="Connectez-vous"):
        gestion.ouvrir_console(distante.ident)


def test_oublier_une_distante_ferme_sa_session(tmp_path):
    distante = _distante_enregistree()
    session = _FausseSession(compose.render_stack(_config(tmp_path)))
    g = gestionnaire.Gestionnaire(
        ouvrir=lambda u: True, connecter=lambda t, c: session, verifier_maj=False
    )
    g.connecter(distante.ident, {"password": "x"})

    g.oublier(distante.ident)

    assert session.fermee
    assert distantes.lire() == []


# --------------------------------------------------------------------- console


def test_la_console_locale_est_hebergee_et_rouverte_sans_doublon(tmp_path, gestion):
    compose.write_artifacts(_config(tmp_path), tmp_path / "projet")
    [inst] = registre.lire()

    premiere = gestion.ouvrir_console(inst.ident)
    seconde = gestion.ouvrir_console(inst.ident)

    assert premiere == seconde
    assert gestion.ouvertes == [premiere, premiere]
    assert re.fullmatch(r"http://127\.0\.0\.1:\d+/\?t=[\w-]+", premiere)
    assert httpx.get(premiere, timeout=10).status_code == 200
    assert httpx.get(premiere.split("?")[0], timeout=10).status_code == 401


# ------------------------------------------------------------------ cycle de vie


def test_une_seconde_fenetre_rejoint_le_gestionnaire_ouvert(gestion):
    gestionnaire._ecrire_verrou(gestion)

    assert gestionnaire.deja_ouvert() == gestion.url


def test_un_verrou_perime_ne_bloque_pas_le_demarrage(tmp_path):
    gestionnaire._chemin_verrou().parent.mkdir(parents=True, exist_ok=True)
    gestionnaire._chemin_verrou().write_text('{"port": 9, "jeton": "x"}', encoding="utf-8")

    assert gestionnaire.deja_ouvert() is None


def test_sans_activite_le_gestionnaire_se_ferme(monkeypatch):
    monkeypatch.setattr(gestionnaire, "INACTIVITE", 0.2)
    g = gestionnaire.Gestionnaire(ouvrir=lambda u: True, verifier_maj=False)
    g.demarrer()
    g.activite = time.monotonic() - 1

    assert g.arret.wait(10)


def test_quitter_depuis_la_page_arrete_le_gestionnaire(gestion):
    with _client(gestion) as client:
        assert client.post("/api/quitter").status_code == 200

    assert gestion.arret.wait(5)
