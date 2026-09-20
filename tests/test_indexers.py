"""Tests de la saisie d'indexeurs. Aucun reseau, aucun tracker contacte.

La forme des donnees reproduit ce que renvoie reellement Prowlarr 2.5.2 :
`baseUrl` de type `select` sans valeur ni options, URL portees par `indexerUrls`
au niveau de la definition, champs de reglage prefixes, textes d'aide en `info`.
"""

from __future__ import annotations

import pytest

from plugarr.clients.prowlarr import (
    CREDENTIAL_NAMES,
    IndexerDefinition,
    ProwlarrIndexers,
    is_credential,
    is_tuning,
)


def definition(name: str, fields: list[dict], urls: list[str] | None = None, **extra):
    raw = {
        "name": name,
        "implementation": name,
        "privacy": extra.get("privacy", "private"),
        "protocol": extra.get("protocol", "torrent"),
        "indexerUrls": urls or [],
        "description": extra.get("description", ""),
        "fields": fields,
    }
    return IndexerDefinition(
        name=name,
        implementation=name,
        privacy=raw["privacy"],
        protocol=raw["protocol"],
        language="en-US",
        description=raw["description"],
        raw=raw,
    )


class FakeClient:
    """Remplace ArrClient : renvoie des donnees fixes, ne fait aucun appel."""

    def __init__(self, schema=None, configured=None, fail: str | None = None):
        self._schema = schema or []
        self._configured = configured or []
        self._fail = fail
        self.posted: list[tuple[str, dict]] = []

    def get(self, resource):
        if resource == "indexer/schema":
            return self._schema
        if resource == "indexer":
            return self._configured
        if resource == "appprofile":
            return [{"id": 7, "name": "Standard"}]
        return []

    def post(self, resource, payload, *, timeout=None):
        from plugarr.clients.base import WiringError

        self.posted.append((resource, payload))
        if self._fail:
            raise WiringError("prowlarr: POST indexer a echoue", self._fail)
        return {"id": 1, **payload}

    def profile_id(self, resource, preferred):
        from plugarr.clients.arr import ArrClient

        return ArrClient.profile_id(self, resource, preferred)  # type: ignore[arg-type]


# ------------------------------------------------------- reperage des champs


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "apiKey", "privacy": "apiKey", "type": "textbox"},
        {"name": "password", "privacy": "password", "type": "password"},
        {"name": "username", "privacy": "userName", "type": "textbox"},
        # Les definitions Cardigann laissent leurs cles en privacy "normal" :
        # le marqueur seul ne suffit pas, d'ou la liste de noms connus.
        {"name": "passkey", "privacy": "normal", "type": "textbox"},
        {"name": "cookie", "privacy": "normal", "type": "textbox"},
    ],
)
def test_credential_fields_are_recognised(raw):
    assert is_credential(raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "baseSettings.queryLimit", "type": "number"},
        {"name": "torrentBaseSettings.seedRatio", "type": "number"},
        {"name": "info_activity", "type": "info"},
        {"name": "freeleech", "type": "checkbox"},
        {"name": "sort", "type": "select"},
    ],
)
def test_tuning_and_help_fields_are_not_credentials(raw):
    assert not is_credential(raw)


def test_tuning_prefixes_cover_the_three_families():
    assert is_tuning("baseSettings.x")
    assert is_tuning("torrentBaseSettings.x")
    assert is_tuning("usenetBaseSettings.x")
    assert is_tuning("info_help")
    assert not is_tuning("apiKey")


def test_credential_names_are_lowercase():
    """La comparaison se fait en minuscules : une entree capitalisee ne matcherait jamais."""
    assert all(n == n.lower() for n in CREDENTIAL_NAMES)


# --------------------------------------------------------- champs a afficher


def test_only_credentials_and_base_url_are_shown():
    d = definition(
        "Exemple",
        [
            {"name": "baseUrl", "type": "select", "label": "Base Url", "value": None},
            {"name": "apiKey", "type": "textbox", "label": "API Key", "privacy": "apiKey"},
            {"name": "freeleech", "type": "checkbox", "label": "Freeleech"},
            {"name": "info_tpp", "type": "info", "label": "Torrents par page"},
            {"name": "baseSettings.queryLimit", "type": "number", "label": "Limite"},
        ],
        urls=["https://exemple.test/"],
    )
    assert [f.name for f in d.editable_fields()] == ["baseUrl", "apiKey"]


def test_base_url_falls_back_to_indexer_urls():
    """600 des 626 definitions ont un baseUrl `select` VIDE : sans cette reprise,
    l'utilisateur devrait deviner l'adresse du tracker."""
    d = definition(
        "Exemple",
        [{"name": "baseUrl", "type": "select", "label": "Base Url", "value": None}],
        urls=["https://miroir-un.test/", "https://miroir-deux.test/"],
    )
    assert d.editable_fields()[0].prefill == "https://miroir-un.test/"
    assert d.urls[1] == "https://miroir-deux.test/"


def test_explicit_base_url_value_wins_over_indexer_urls():
    d = definition(
        "Exemple",
        [{"name": "baseUrl", "type": "textbox", "value": "https://choisi.test"}],
        urls=["https://ignore.test"],
    )
    assert d.editable_fields()[0].prefill == "https://choisi.test"


def test_secret_fields_are_flagged_for_masking():
    d = definition(
        "Exemple",
        [
            {"name": "username", "type": "textbox", "privacy": "userName"},
            {"name": "password", "type": "password", "privacy": "password"},
        ],
    )
    secrets = {f.name: f.secret for f in d.editable_fields()}
    assert secrets == {"username": False, "password": True}


# ------------------------------------------------------------------ recherche


def _indexers(names: list[str], configured=None, fail=None) -> ProwlarrIndexers:
    schema = [definition(n, [{"name": "apiKey", "privacy": "apiKey"}]).raw for n in names]
    return ProwlarrIndexers(FakeClient(schema=schema, configured=configured, fail=fail))


def test_search_is_case_insensitive_and_substring():
    idx = _indexers(["NZBgeek", "abNZB", "TorrentDay"])
    assert {d.name for d in idx.search("nzb")} == {"NZBgeek", "abNZB"}


def test_exact_prefix_matches_come_first():
    """Taper "nzbgeek" ne doit pas remonter "abNZBgeek" en premier."""
    idx = _indexers(["abNZBgeek", "NZBgeek"])
    assert [d.name for d in idx.search("nzbgeek")] == ["NZBgeek", "abNZBgeek"]


def test_empty_search_returns_nothing_rather_than_everything():
    idx = _indexers(["A", "B", "C"])
    assert idx.search("") == []
    assert idx.search("   ") == []


def test_search_respects_the_limit():
    idx = _indexers([f"Tracker{i}" for i in range(50)])
    assert len(idx.search("tracker", limit=5)) == 5


def test_definitions_are_fetched_once_and_cached():
    """5,7 Mo : refaire l'appel a chaque frappe serait inutilisable."""
    client = FakeClient(schema=[definition("A", []).raw])
    idx = ProwlarrIndexers(client)
    calls = []
    original = client.get
    client.get = lambda r: (calls.append(r), original(r))[1]
    idx.definitions()
    idx.definitions()
    assert calls.count("indexer/schema") == 1


def test_unknown_name_gives_an_actionable_error():
    idx = _indexers(["NZBgeek"])
    with pytest.raises(Exception, match="search"):
        idx.find("Inexistant")


# ----------------------------------------------------------------------- ajout


def test_adding_an_already_configured_indexer_is_a_noop():
    idx = _indexers(["NZBgeek"], configured=[{"name": "NZBgeek"}])
    ok, message = idx.add(idx.find("NZBgeek"), {"apiKey": "x"})
    assert ok and message == "deja configure"
    assert idx._client.posted == []  # aucun appel, donc aucun contact de l'indexeur


def test_add_resolves_the_app_profile_instead_of_hardcoding_it():
    """Prowlarr refuse appProfileId=0, et l'identifiant n'est pas stable."""
    idx = _indexers(["NZBgeek"])
    idx.add(idx.find("NZBgeek"), {"apiKey": "secret"})
    _resource, payload = idx._client.posted[0]
    assert payload["appProfileId"] == 7


def test_add_injects_the_user_values_into_the_schema_fields():
    idx = _indexers(["NZBgeek"])
    idx.add(idx.find("NZBgeek"), {"apiKey": "ma-cle"})
    _resource, payload = idx._client.posted[0]
    assert {f["name"]: f.get("value") for f in payload["fields"]} == {"apiKey": "ma-cle"}
    assert payload["enable"] is True


def test_failure_returns_a_readable_message_not_a_stack_trace():
    idx = _indexers(["NZBgeek"], fail="Unable to connect to indexer. DNS/SSL issues")
    ok, message = idx.add(idx.find("NZBgeek"), {"apiKey": "x"})
    assert not ok
    assert "Unable to connect" in message
    assert "\n" not in message


# ------------------------------------------------- regle structurelle (audit)


@pytest.mark.parametrize(
    ("raw", "expected", "why"),
    [
        # Trouves par l'audit des 626 definitions : aucun marqueur, aucun nom
        # connu, mais ce sont bien des identifiants.
        ({"name": "mamId", "type": "textbox", "privacy": "normal", "value": ""}, True, "MyAnonamouse"),
        ({"name": "2facode", "type": "textbox", "privacy": "normal", "value": None}, True, "2FA"),
        ({"name": "staffpass", "type": "textbox", "privacy": "normal", "value": None}, True, "cle"),
        ({"name": "useragent", "type": "textbox", "privacy": "normal", "value": None}, True, "UA lie a la session"),
        # Reglages de comportement : jamais des textbox vides.
        ({"name": "useFreeleechToken", "type": "select", "value": 0}, False, "liste"),
        ({"name": "authorisedOnly", "type": "checkbox", "value": False}, False, "case a cocher"),
        ({"name": "passid", "type": "select", "value": 0}, False, "liste malgre son nom"),
        # Une zone de texte DEJA remplie n'attend rien de l'utilisateur.
        ({"name": "apiPath", "type": "textbox", "value": "/api"}, False, "valeur par defaut"),
    ],
)
def test_structural_rule_catches_what_no_name_list_could(raw, expected, why):
    """Un textbox sans valeur par defaut est, par construction, quelque chose que
    seul l'utilisateur peut fournir."""
    assert is_credential(raw) is expected, why


@pytest.mark.parametrize("name", ["vipExpiration", "additionalParameters", "thankyou", "sub_lang"])
def test_known_free_text_fields_are_not_treated_as_credentials(name):
    """Ce sont des textbox vides comme les identifiants : sans liste explicite,
    la regle structurelle les remonterait et noierait le formulaire."""
    assert not is_credential({"name": name, "type": "textbox", "value": None})


def test_no_credential_name_is_also_listed_as_a_credential():
    """Les deux listes doivent rester disjointes, sinon l'ordre des regles decide."""
    from plugarr.clients.prowlarr import NON_CREDENTIAL_NAMES

    assert not (CREDENTIAL_NAMES & NON_CREDENTIAL_NAMES)


def test_non_credential_names_are_lowercase():
    from plugarr.clients.prowlarr import NON_CREDENTIAL_NAMES

    assert all(n == n.lower() for n in NON_CREDENTIAL_NAMES)


def test_a_private_indexer_without_credentials_stays_possible():
    """BitMagnet, comicat, MioBT et ConCen sont prives mais n'exigent aucun
    compte : ne pas leur inventer de champ."""
    d = definition(
        "IndexLocal",
        [
            {"name": "definitionFile", "type": "textbox", "value": "local.yml"},
            {"name": "baseUrl", "type": "select", "value": None},
            {"name": "baseSettings.queryLimit", "type": "number", "value": None},
        ],
        urls=["https://local.invalid/"],
    )
    assert [f.name for f in d.editable_fields()] == ["baseUrl"]
