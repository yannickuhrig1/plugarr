"""Authentification de la console d'administration.

Le jeton tire a chaque demarrage convient tant qu'on lance `plugarr serve` a
la main : il s'affiche dans le terminal, juste au-dessus de l'URL. Il ne
convient plus des que la console tourne en permanence — personne n'ira lire un
journal de conteneur pour retrouver un jeton a chaque redemarrage, et un jeton
qui vit dans l'URL finit dans l'historique du navigateur.

D'ou un mot de passe, et tout ce que cela impose : empreinte plutot que valeur
en clair, limitation des tentatives, sessions expirables.
"""

from __future__ import annotations

import http.client
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from plugarr import admin, adminauth, i18n, orchestrator

MOT_DE_PASSE = "unmotdepassecorrect"
IP = "10.0.0.1"


# ------------------------------------------------------------------ empreinte


def test_le_mot_de_passe_n_apparait_pas_dans_l_empreinte():
    """`stack.yml` est le fichier qu'on ouvre pour retrouver un port."""
    empreinte = adminauth.hash_password(MOT_DE_PASSE)

    assert MOT_DE_PASSE not in empreinte
    assert empreinte.startswith("pbkdf2-sha256$600000$")


def test_le_bon_mot_de_passe_est_reconnu():
    assert adminauth.verify_password(MOT_DE_PASSE, adminauth.hash_password(MOT_DE_PASSE))


def test_un_autre_mot_de_passe_est_refuse():
    assert not adminauth.verify_password("autre", adminauth.hash_password(MOT_DE_PASSE))


def test_deux_empreintes_du_meme_mot_de_passe_different():
    """Sel aleatoire : deux comptes au meme mot de passe ne doivent pas se voir."""
    a = adminauth.hash_password(MOT_DE_PASSE)
    b = adminauth.hash_password(MOT_DE_PASSE)

    assert a != b
    assert adminauth.verify_password(MOT_DE_PASSE, a)
    assert adminauth.verify_password(MOT_DE_PASSE, b)


@pytest.mark.parametrize(
    "cassee",
    ["", "nimportequoi", "pbkdf2-sha256$", "autre-algo$600000$c2Vs$ZW1wcmVpbnRl", "a$b$c$d"],
)
def test_une_empreinte_cassee_refuse_au_lieu_de_lever(cassee):
    """Une `stack.yml` modifiee a la main ne doit pas empecher la console de
    repondre : elle doit empecher d'entrer."""
    assert adminauth.verify_password(MOT_DE_PASSE, cassee) is False


# ------------------------------------------------------------------ sessions


def test_une_session_ouverte_est_valide():
    sessions = adminauth.Sessions()
    jeton = sessions.open()

    assert sessions.valid(jeton)


def test_un_jeton_inconnu_est_refuse():
    sessions = adminauth.Sessions()

    assert not sessions.valid("inventé")
    assert not sessions.valid("")


def test_une_session_expire():
    horloge = [1000.0]
    sessions = adminauth.Sessions(now=lambda: horloge[0])
    jeton = sessions.open()

    horloge[0] += adminauth.SESSION_SECONDS + 1

    assert not sessions.valid(jeton)


def test_la_deconnexion_ferme_la_session():
    sessions = adminauth.Sessions()
    jeton = sessions.open()
    sessions.close(jeton)

    assert not sessions.valid(jeton)


# --------------------------------------------------------------- tentatives


def _epuiser(sessions, ip=IP):
    for _ in range(adminauth.MAX_ATTEMPTS):
        assert sessions.reserve_attempt(ip)


def test_les_tentatives_sont_limitees():
    """Des que la console sort de 127.0.0.1, un mot de passe se devine en
    quelques heures sans cette limite."""
    sessions = adminauth.Sessions()
    _epuiser(sessions)

    assert not sessions.reserve_attempt(IP)
    assert sessions.retry_in(IP) > 0


def test_le_blocage_se_leve_avec_le_temps():
    horloge = [1000.0]
    sessions = adminauth.Sessions(now=lambda: horloge[0])
    _epuiser(sessions)
    assert not sessions.reserve_attempt(IP)

    horloge[0] += adminauth.LOCKOUT_SECONDS + 1

    assert sessions.retry_in(IP) == 0
    assert sessions.reserve_attempt(IP)


def test_l_attente_annoncee_n_est_jamais_nulle_tant_que_c_est_bloque():
    """« Reessayez dans 0 s » serait faux, et 0 veut dire que l'essai est permis."""
    horloge = [1000.0]
    sessions = adminauth.Sessions(now=lambda: horloge[0])
    _epuiser(sessions)

    horloge[0] += adminauth.LOCKOUT_SECONDS - 0.5

    assert sessions.retry_in(IP) == 1
    assert not sessions.reserve_attempt(IP)


def test_une_connexion_reussie_remet_le_compteur_a_zero():
    sessions = adminauth.Sessions()
    for _ in range(adminauth.MAX_ATTEMPTS - 1):
        sessions.reserve_attempt(IP)
    sessions.clear_failures(IP)

    _epuiser(sessions)


def test_une_connexion_reussie_ne_lave_que_son_adresse():
    """Sinon l'administrateur qui se connecte rendrait ses essais a l'attaquant."""
    sessions = adminauth.Sessions()
    _epuiser(sessions, "10.0.0.66")

    sessions.reserve_attempt(IP)
    sessions.clear_failures(IP)

    assert not sessions.reserve_attempt("10.0.0.66")


def test_un_appareil_bloque_ne_bloque_pas_les_autres():
    """Avec un compteur unique, dix essais depuis n'importe quel appareil du
    reseau local empechaient aussi l'administrateur d'entrer."""
    sessions = adminauth.Sessions()
    _epuiser(sessions, "10.0.0.66")

    assert sessions.retry_in(IP) == 0
    assert sessions.reserve_attempt(IP)


def test_multiplier_les_adresses_ne_multiplie_pas_les_essais():
    """Seule, la limite par adresse se multiplierait par le nombre d'adresses."""
    sessions = adminauth.Sessions()

    permis = sum(
        sessions.reserve_attempt(f"10.0.0.{n}")
        for n in range(256)
        for _ in range(adminauth.MAX_ATTEMPTS)
    )

    assert permis == adminauth.MAX_ATTEMPTS_TOTAL
    assert sessions.retry_in("192.0.2.1") > 0


def test_la_memoire_des_essais_reste_bornee():
    """Une console joignable ne doit pas grossir a chaque adresse inconnue."""
    horloge = [1000.0]
    sessions = adminauth.Sessions(now=lambda: horloge[0])
    for n in range(5000):
        sessions.reserve_attempt(f"10.0.{n >> 8}.{n & 255}")

    assert sum(map(len, sessions._failures.values())) == adminauth.MAX_ATTEMPTS_TOTAL

    horloge[0] += adminauth.LOCKOUT_SECONDS + 1
    sessions.retry_in(IP)

    assert sessions._failures == {}


# ------------------------------------------------------------------- serveur


@pytest.fixture
def console(monkeypatch):
    """Une console reelle, sur un port libre, arretee a la fin.

    Empreinte a 1 000 iterations : ces tests portent sur la console, pas sur le
    cout du hachage. Aux 600 000 reelles, les douze essais du test de blocage
    prenaient 2,7 s au repos (mesure), et pouvaient approcher le delai de 10 s
    par appel sous la charge d'une suite complete.
    """
    monkeypatch.setattr(adminauth, "ITERATIONS", 1_000)
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root="/c", data_root="/d"
    )
    cfg.admin_password_hash = adminauth.hash_password(MOT_DE_PASSE)
    serveur = admin.build_server(cfg, Path("."), host="127.0.0.1", port=0, token="jetondetest")
    port = serveur.server_address[1]
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    for _ in range(50):
        # La sonde se REFERME. Laissee ouverte, elle occupait un fil du serveur,
        # bloque a lire une requete qui ne venait jamais ; et comme la console
        # tourne avec `daemon_threads = False`, ce fil survivait au test.
        sonde = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            sonde.connect()
            break
        except OSError:
            time.sleep(0.02)
        finally:
            sonde.close()
    yield port
    # `shutdown` arrete la boucle, il ne FERME PAS la socket d'ecoute : sans
    # `server_close`, chaque test de ce fichier laissait un port pris et des
    # fils en vie jusqu'a la fin de la suite. D'ou des `ConnectionAbortedError`
    # intermittentes, jamais seules, jamais reproductibles isolement.
    serveur.shutdown()
    serveur.server_close()


def appel(port, methode, chemin, corps=None, cookie=None):
    connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    entetes = {}
    if cookie:
        entetes["Cookie"] = cookie
    if corps is not None:
        corps = urllib.parse.urlencode(corps)
        entetes["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        connexion.request(methode, chemin, body=corps, headers=entetes)
        reponse = connexion.getresponse()
        return (reponse.status, reponse.getheader("Set-Cookie"),
                reponse.read().decode("utf-8", "replace"))
    finally:
        connexion.close()


def test_sans_rien_le_formulaire_est_propose(console):
    code, _cookie, page = appel(console, "GET", "/")

    assert code == 401
    assert 'name="password"' in page


def test_le_jeton_ouvre_toujours_la_console(console):
    """Lancer `plugarr serve` a la main ne doit pas imposer d'inventer un mot
    de passe pour regarder l'etat de ses services."""
    code, _cookie, page = appel(console, "GET", "/?t=jetondetest")

    assert code == 200
    assert "Votre stack media" in page


def test_le_bon_mot_de_passe_ouvre_une_session(console):
    code, cookie, page = appel(console, "POST", "/login", {"password": MOT_DE_PASSE})

    assert code == 200
    assert "Votre stack media" in page
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie


def test_la_session_vaut_pour_les_appels_suivants(console):
    _code, cookie, _page = appel(console, "POST", "/login", {"password": MOT_DE_PASSE})
    jeton = cookie.split(";")[0]

    code, _c, corps = appel(console, "GET", "/api/status", cookie=jeton)

    assert code == 200
    assert corps.startswith("{")


def test_un_mauvais_mot_de_passe_est_refuse(console):
    code, _cookie, page = appel(console, "POST", "/login", {"password": "faux"})

    assert code == 401
    assert "refuse" in page


def test_un_cookie_accentue_ne_tue_pas_la_requete(console):
    """`compare_digest` refuse les chaines non-ASCII et leve `TypeError`. Un
    cookie accentue suffisait donc a tuer le fil de traitement, sans la moindre
    authentification."""
    code, _cookie, _page = appel(console, "GET", "/api/status", cookie="plugarr_token=inventé")

    assert code == 401


def test_la_deconnexion_invalide_la_session(console):
    _code, cookie, _page = appel(console, "POST", "/login", {"password": MOT_DE_PASSE})
    jeton = cookie.split(";")[0]
    appel(console, "POST", "/logout", cookie=jeton)

    code, _c, _corps = appel(console, "GET", "/api/status", cookie=jeton)

    assert code == 401


def test_les_tentatives_repetees_finissent_bloquees(console):
    for _ in range(adminauth.MAX_ATTEMPTS + 2):
        appel(console, "POST", "/login", {"password": "faux"})

    code, _cookie, page = appel(console, "POST", "/login", {"password": MOT_DE_PASSE})

    # Ce test, et d'autres de ce fichier, echouaient de loin en loin en passe
    # COMPLETE, jamais seuls, sur une `ConnectionAbortedError` cote client.
    # Cause trouvee le 2026-09-20 : la fixture n'appelait pas `server_close`, et
    # la sonde de disponibilite ne se refermait pas. Mesure : apres un seul
    # cycle sans `server_close`, le port refuse un nouveau `bind` ; avec, il est
    # libre. Chaque test de ce fichier laissait donc une socket d'ecoute vivante
    # jusqu'a la fin de la suite. Les assertions ci-dessous gardent de quoi
    # trancher si cela devait retomber malgre tout. La langue d'abord : la page
    # est verifiee sur une phrase francaise, et un autre test qui la basculerait
    # ferait echouer celle-la sans que le blocage soit en cause.
    assert i18n.langue() == "fr", f"langue={i18n.langue()}"
    assert code == 429, f"page={page[:300]!r}"
    assert "Trop de tentatives" in page, f"code={code} page={page[:300]!r}"


def test_une_rafale_ne_depasse_pas_la_limite(console):
    """Compter apres le hachage laissait passer les requetes paralleles : 22 essais
    verifies sur 40 envoyes ensemble, pour une limite de dix (mesure)."""
    def essayer(_):
        try:
            return appel(console, "POST", "/login", {"password": "faux"})[0]
        except OSError:
            # La file d'attente du serveur (5 places) a deborde : rien n'a ete essaye.
            return None

    with ThreadPoolExecutor(max_workers=40) as pool:
        codes = list(pool.map(essayer, range(40)))
    # Jusqu'au blocage : les essais perdus ne doivent pas masquer un depassement.
    while (code := essayer(None)) != 429:
        codes.append(code)

    assert codes.count(401) == adminauth.MAX_ATTEMPTS


def test_le_refus_pour_trop_de_tentatives_arrive_entier(console):
    """Refuser sans lire le corps fait repondre un RST a la pile TCP : le navigateur
    affichait une connexion coupee au lieu de la phrase qui donne l'attente. Cinq Mo
    pour que l'echec soit certain : un petit corps tient dans les tampons reseau."""
    for _ in range(adminauth.MAX_ATTEMPTS):
        appel(console, "POST", "/login", {"password": "faux"})

    code, _, page = appel(
        console, "POST", "/login", {"password": "faux", "bourrage": "x" * 5_000_000}
    )

    assert code == 429
    assert "Trop de tentatives" in page


def test_les_entetes_de_securite_sont_poses(console):
    connexion = http.client.HTTPConnection("127.0.0.1", console, timeout=10)
    try:
        connexion.request("GET", "/?t=jetondetest")
        reponse = connexion.getresponse()
        entetes = {nom: reponse.getheader(nom) for nom in
                   ("Content-Security-Policy", "Referrer-Policy", "X-Content-Type-Options")}
    finally:
        connexion.close()

    # Une console qui affiche des mots de passe n'a rien a faire dans un cadre.
    assert "frame-ancestors 'none'" in entetes["Content-Security-Policy"]
    assert entetes["Referrer-Policy"] == "no-referrer"
    assert entetes["X-Content-Type-Options"] == "nosniff"


def test_sans_mot_de_passe_configure_aucun_formulaire_n_est_propose():
    """Un formulaire sans mot de passe pose serait cruel : rien a y taper."""
    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")
    serveur = admin.build_server(cfg, Path("."), host="127.0.0.1", port=0, token="jetondetest")
    port = serveur.server_address[1]
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        code, _cookie, page = appel(port, "GET", "/")
        assert code == 401
        assert 'name="password"' not in page
        assert "plugarr serve" in page

        # Et le mot de passe ne peut pas ouvrir de session : il n'y en a pas.
        code, _cookie, _page = appel(port, "POST", "/login", {"password": MOT_DE_PASSE})
        assert code == 401
    finally:
        serveur.shutdown()
        serveur.server_close()
