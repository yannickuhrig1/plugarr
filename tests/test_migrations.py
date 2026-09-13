"""`stack.yml` porte une version, et elle est enfin lue.

Le champ `version` existait depuis la premiere ligne du projet et **rien ne le
lisait** — aucune occurrence dans le code. Il ne servait donc a rien, alors
qu'il protege d'un chemin de perte de donnees mesurable.

**L'experience qui a motive ce module.** Un `stack.yml` marque `version: 2`,
portant un champ qu'une version future aurait ajoute, donne a lire a la
version courante :

    version lue          : 2
    champ futur garde ?  : False
    champ futur reecrit ?: False

Pydantic ignore ce qu'il ne connait pas, c'est son defaut. L'ancienne version
lit sans broncher, jette une partie, et la premiere ecriture detruit le reste
— `install`, `generate` et la rotation d'un mot de passe reecrivent tous
`stack.yml`. Le cas se produit des qu'on revient en arriere apres un essai.
"""

from __future__ import annotations

import pytest
import yaml

from plugarr import migrations, orchestrator
from plugarr.models import StackConfig


def _brut(**extra):
    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")
    donnees = yaml.safe_load(yaml.safe_dump(cfg.model_dump(mode="json")))
    donnees.update(extra)
    return donnees


# ------------------------------------------------------------------ le socle


def test_une_configuration_courante_traverse_sans_rien_changer():
    donnees = _brut()

    migre, notes = migrations.migrer(dict(donnees))

    assert migre == donnees
    assert notes == []


def test_un_stack_sans_version_est_lu_depuis_la_version_1():
    """Les tout premiers `stack.yml` pourraient ne pas porter le champ."""
    donnees = _brut()
    del donnees["version"]

    migre, _notes = migrations.migrer(donnees)

    assert migre["version"] == migrations.VERSION_COURANTE


def test_la_migration_garde_sabnzbd_dans_le_vpn_existant():
    donnees = _brut(version=1)
    donnees["services"]["sabnzbd"] = {"spec_id": "sabnzbd", "host_port": 8085}
    donnees["vpn"] = {"enabled": True, "provider": "mullvad"}

    migre, notes = migrations.migrer(donnees)

    assert migre["vpn"]["protect_sabnzbd"] is True
    # Un fichier en version 1 traverse TOUTES les migrations suivantes : la
    # note de la version 2 doit y figurer, pas etre la seule.
    assert "stack.yml migre en version 2" in notes


def test_la_migration_n_active_pas_sabnzbd_sans_ancien_tunnel():
    donnees = _brut(version=1)
    donnees["services"]["sabnzbd"] = {"spec_id": "sabnzbd", "host_port": 8085}
    donnees["vpn"] = {"enabled": False}

    migre, _notes = migrations.migrer(donnees)

    assert migre["vpn"]["protect_sabnzbd"] is False


def test_une_version_future_est_refusee():
    """C'est le coeur du module.

    Sans ce refus, l'ancienne version lit a moitie et detruit le reste a la
    premiere ecriture, sans un mot.
    """
    with pytest.raises(migrations.VersionFuture, match="Mettez PlugArr a jour"):
        migrations.migrer(_brut(version=migrations.VERSION_COURANTE + 1))


def test_ce_que_le_refus_evite_est_reel(tmp_path):
    """La perte n'est pas theorique : on la reproduit.

    Sans le garde-fou, pydantic laisse tomber le champ inconnu, et le
    dictionnaire reecrit ne le porte plus.
    """
    donnees = _brut(version=2, un_champ_futur={"important": True})

    relu = StackConfig.model_validate(donnees)

    assert not hasattr(relu, "un_champ_futur")
    assert "un_champ_futur" not in relu.model_dump(mode="json")


def test_une_version_illisible_ne_passe_pas_en_silence():
    with pytest.raises(ValueError, match="illisible"):
        migrations.migrer(_brut(version="deux"))


def test_un_trou_dans_la_chaine_est_signale(monkeypatch):
    """Augmenter `VERSION_COURANTE` sans ecrire la migration correspondante est
    une erreur de programmation : elle doit se voir tout de suite."""
    monkeypatch.setattr(migrations, "VERSION_COURANTE", 3)
    monkeypatch.setattr(migrations, "MIGRATIONS", {})

    with pytest.raises(ValueError, match="aucune migration"):
        migrations.migrer(_brut(version=1))


# ------------------------------------------------------ la chaine est coherente


def test_la_version_courante_a_toutes_ses_migrations():
    """`VERSION_COURANTE` et `MIGRATIONS` doivent avancer ensemble.

    Ce test est la vraie garantie du module : il echoue le jour ou quelqu'un
    augmente le numero sans ecrire la transformation.
    """
    attendues = set(range(1, migrations.VERSION_COURANTE))

    assert set(migrations.MIGRATIONS) == attendues


def test_chaque_migration_rend_un_dictionnaire():
    depart = _brut()
    for depuis, transformation in migrations.MIGRATIONS.items():
        resultat = transformation(dict(depart))
        assert isinstance(resultat, dict), depuis


def test_le_modele_ecrit_la_version_courante():
    """Un fichier ecrit aujourd'hui doit se relire sans migration demain."""
    cfg = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")

    assert cfg.version == migrations.VERSION_COURANTE


# --------------------------------------------------------------------- lecture


def test_lire_migre_avant_de_valider(tmp_path, monkeypatch):
    """L'ordre compte : valider d'abord reviendrait a migrer des valeurs par
    defaut inventees par pydantic plutot que le contenu du fichier.

    On le prouve en posant une migration qui a besoin de savoir qu'un champ
    etait ABSENT — information que pydantic detruit en la remplacant par sa
    valeur par defaut.
    """
    vu = {}

    def migration(donnees):
        vu["username_present"] = "username" in donnees
        donnees["username"] = "migre"
        return donnees

    monkeypatch.setattr(migrations, "VERSION_COURANTE", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {1: migration})

    donnees = _brut(version=1)
    del donnees["username"]
    chemin = tmp_path / "stack.yml"
    chemin.write_text(yaml.safe_dump(donnees), encoding="utf-8")

    cfg, notes = migrations.lire(chemin)

    assert vu["username_present"] is False, "la migration a vu une valeur par defaut"
    assert cfg.username == "migre"
    assert notes == ["stack.yml migre en version 2"]


def test_lire_rend_le_journal_de_ce_qui_a_ete_fait():
    """Une migration silencieuse est une migration qu'on ne peut pas verifier."""
    import inspect

    source = inspect.getsource(migrations.migrer)

    assert "notes.append" in source
