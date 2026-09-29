"""Mise a jour du pack : aligner une installation ancienne sur cette version.

PlugArr savait mettre a jour UN service. Il ne savait pas mettre a jour **sa
propre installation** quand c'est PlugArr qui change : quelqu'un qui a installe
il y a six mois et telecharge le binaire du jour n'avait aucune commande a
lancer.

La regle qui prime sur tout le reste : **on ne redescend jamais**. Le tag
deploye vit dans `stack.yml` et non dans le code, precisement pour qu'on puisse
mettre Sonarr a jour sans attendre une version de PlugArr, ou rester
delibrement sur une version ancienne. Un `upgrade` qui ramenerait tout au
catalogue annulerait ce choix sans le dire.
"""

from __future__ import annotations

from plugarr import catalog, orchestrator, pack


def _cfg(**images):
    cfg = orchestrator.build_config(
        services=["sonarr", "radarr"], config_root="/c", data_root="/d"
    )
    for sid, image in images.items():
        cfg.services[sid].image = image
    return cfg


# ------------------------------------------------------------------ ce qu'on retient


def test_une_installation_a_jour_n_a_aucun_ecart():
    retenus, ecartes = pack.ecarts(_cfg())

    assert retenus == []
    assert ecartes == []


def test_une_image_plus_ancienne_est_proposee():
    reference = catalog.get("sonarr").image
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:3.0.10")

    retenus, _ecartes = pack.ecarts(cfg)

    assert [e.service for e in retenus] == ["sonarr"]
    assert retenus[0].catalogue == reference


def test_une_image_plus_recente_n_est_JAMAIS_redescendue():
    """Le cas de quelqu'un qui a mis a jour lui-meme.

    C'est le seul ou aligner sur le catalogue serait une REGRESSION, et le tag
    vit dans `stack.yml` justement pour permettre ce choix.
    """
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:9.9.9")

    retenus, ecartes = pack.ecarts(cfg)

    assert retenus == []
    assert any("9.9.9" in raison for raison in ecartes)


def test_la_comparaison_se_fait_sur_des_nombres_pas_des_chaines():
    """`4.9.5` vient AVANT `4.16.1`, ce que l'ordre alphabetique inverse."""
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:4.9.5")
    reference = catalog.get("sonarr").image

    retenus, _ecartes = pack.ecarts(cfg)

    # Le catalogue epingle 4.0.19 : 4.9.5 est donc PLUS RECENT, et rien ne doit
    # etre propose — meme si « 4.9.5 » < « 4.0.19 » alphabetiquement est faux
    # dans les deux sens selon qu'on lit des chaines ou des nombres.
    installe = (4, 9, 5)
    from plugarr import updates

    catalogue = updates.parse_version(reference.rpartition(":")[2].partition("@")[0])
    attendu_propose = catalogue is not None and catalogue > installe
    assert bool(retenus) is attendu_propose


def test_un_tag_incomparable_est_ecarte_avec_sa_raison():
    """Un tag maison ne se compare pas. On ne devine pas : on le dit."""
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:maison")

    retenus, ecartes = pack.ecarts(cfg)

    assert retenus == []
    assert any("maison" in raison for raison in ecartes)


def test_le_meme_tag_re_epingle_est_propose_sans_question():
    """Meme version, digest different : c'est le meme logiciel, re-epingle en
    amont. Rien a decider."""
    reference = catalog.get("sonarr").image
    ancien = reference.partition("@")[0] + "@sha256:" + "0" * 64
    cfg = _cfg(sonarr=ancien)

    retenus, ecartes = pack.ecarts(cfg)

    assert [e.service for e in retenus] == ["sonarr"]
    assert retenus[0].meme_tag is True
    assert ecartes == []


def test_un_service_absent_de_l_installation_est_ignore():
    """Le catalogue grandit ; `upgrade` n'installe pas de nouveaux services,
    c'est le role de « ajouter un service »."""
    cfg = _cfg()

    retenus, _ecartes = pack.ecarts(cfg)

    assert all(cfg.enabled(e.service) for e in retenus)


def test_un_service_adopte_n_est_pas_recree_par_upgrade():
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:3.0.10")
    cfg.services["sonarr"].adopted = True
    retenus, ecartes = pack.ecarts(cfg)
    assert not any(e.service == "sonarr" for e in retenus)
    assert any("sonarr" in reason and "adopte" in reason for reason in ecartes)


# ------------------------------------------------------------------ ce qu'on ecrit


def test_appliquer_ne_touche_que_la_configuration_en_memoire():
    """Une fonction qui calcule ne doit pas ecrire par surprise : c'est
    l'appelant qui sait s'il est en `--dry-run`."""
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:3.0.10")
    retenus, _ = pack.ecarts(cfg)

    poses = pack.appliquer(cfg, retenus)

    assert poses == ["sonarr"]
    assert cfg.services["sonarr"].image == catalog.get("sonarr").image


def test_appliquer_laisse_les_autres_services_intacts():
    radarr_avant = _cfg().services["radarr"].image
    cfg = _cfg(sonarr="lscr.io/linuxserver/sonarr:3.0.10")

    pack.appliquer(cfg, pack.ecarts(cfg)[0])

    assert cfg.services["radarr"].image == radarr_avant


# ------------------------------------------------------------------ la commande


def test_le_cablage_passe_apres_les_images():
    """Une etape de cablage ajoutee depuis peut dependre d'une image plus
    recente ; l'inverse jamais. L'ordre n'est donc pas arbitraire."""
    import inspect

    from plugarr import cli

    source = inspect.getsource(cli.upgrade)

    assert source.index("runner.recreate") < source.index("Wirer(cfg)")


def test_rien_n_est_ecrit_avant_le_recapitulatif():
    """Meme regle que `install` : on montre, puis on demande."""
    import inspect

    from plugarr import cli

    source = inspect.getsource(cli.upgrade)

    assert source.index("console.print(table)") < source.index("write_artifacts")
    assert source.index("typer.confirm") < source.index("write_artifacts")


def test_les_services_ecartes_sont_affiches():
    """Un `upgrade` qui saute un service en silence donne l'impression d'avoir
    tout aligne."""
    import inspect

    from plugarr import cli

    source = inspect.getsource(cli.upgrade)

    assert "for raison in ecartes" in source
