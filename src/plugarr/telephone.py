"""Configuration du telephone : exports Arr Control, nzb360, qbRemote et QR code.

Portage fidele de `web/remote.js`, pour que le TUI offre la meme chose que
l'assistant web (demande du 26/09/2026). Les formats sont ceux releves dans des
sauvegardes reelles des applications ; chaque fonction garde le nom de son
equivalent JavaScript en commentaire, et `tests/test_telephone.py` compare les
deux sorties octet par octet quand elles sont deterministes.

Les donnees d'entree ont la forme du rapport de fin : un dict avec `services`
(id, name, url, local_url, remote_url, username, password, api_key), `demo` et
`remote` (le mode d'acces distant).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import zlib
from datetime import UTC, datetime
from urllib.parse import urlsplit

#: Applications dont PlugArr gere l'acces distant.
IDS = ("sonarr", "radarr", "qbittorrent")
#: Fiches du telephone : ces applications, plus celles sans acces distant.
MOBILE_IDS = (*IDS, "sabnzbd", "lidarr", "seerr", "transmission")

#: Schema version 1 des exports serveur d'Arr Control (arrServices).
ARR_SERVICES = {
    "sonarr": {"category": "library", "notifications": ["onGrab", "onDownload", "onUpgrade", "onHealthIssue"]},
    "radarr": {"category": "library", "notifications": ["onGrab", "onDownload", "onUpgrade", "onHealthIssue"]},
    "prowlarr": {"category": "indexers", "notifications": ["onHealthIssue", "onApplicationUpdate"]},
    "seerr": {"category": "requests", "notifications": ["pending", "approved", "available", "failed"]},
    "qbittorrent": {"category": "downloads", "notifications": []},
}


class ErreurMotDePasse(ValueError):
    """Mot de passe absent ou faux pour une archive chiffree (ZipPasswordError)."""


# ---------------------------------------------------------------- adresses


def _present(valeur) -> bool:
    return isinstance(valeur, str) and len(valeur) > 0 and valeur != "-"


def _url(adresse):
    """`new URL(adresse)` limite a http(s), sans identifiants dans l'adresse."""
    if not isinstance(adresse, str) or not adresse:
        return None
    try:
        morceaux = urlsplit(adresse)
        port = morceaux.port
    except ValueError:
        return None
    if morceaux.scheme.lower() not in ("http", "https") or not morceaux.hostname:
        return None
    if morceaux.username or morceaux.password:
        return None
    return morceaux, port


def _href_sans_slash(adresse) -> str:
    """`url.href.replace(/\\/$/, '')`, normalisation WHATWG des cas utiles."""
    lu = _url(adresse)
    if lu is None:
        return ""
    morceaux, port = lu
    schema = morceaux.scheme.lower()
    hote = morceaux.hostname.lower()
    if ":" in hote:
        hote = f"[{hote}]"
    defaut = 443 if schema == "https" else 80
    netloc = hote + (f":{port}" if port is not None and port != defaut else "")
    href = f"{schema}://{netloc}{morceaux.path or '/'}"
    if morceaux.query:
        href += f"?{morceaux.query}"
    if morceaux.fragment:
        href += f"#{morceaux.fragment}"
    return href.removesuffix("/")


def _service(data, sid):
    return next((s for s in data.get("services", []) if s.get("id") == sid), None)


# -------------------------------------------------------------- Arr Control


def arr_control(data: dict, network: str = "local", now: int | None = None) -> tuple[dict, list[str]]:
    """buildArrControlExport : profil serveur a restaurer dans Arr Control."""
    if network not in ("local", "remote"):
        raise ValueError("Unknown export network")
    now = int(datetime.now(UTC).timestamp() * 1000) if now is None else now
    services, omis = [], []
    for service in data.get("services", []):
        spec = ARR_SERVICES.get(service.get("id"))
        if spec is None:
            continue
        adresse = service.get("remote_url") if network == "remote" else (service.get("local_url") or service.get("url"))
        if _url(adresse) is None:
            omis.append(service.get("name"))
            continue
        qb = service["id"] == "qbittorrent"
        if (not _present(service.get("username")) or not _present(service.get("password"))) if qb else not _present(service.get("api_key")):
            omis.append(service.get("name"))
            continue
        champs = (
            {"username": service["username"], "password": service["password"], "localUrl": adresse}
            if qb
            else {"apiKey": service["api_key"], "localUrl": adresse}
        )
        services.append({
            "categoryId": spec["category"],
            "serviceId": service["id"],
            "name": service.get("name"),
            "url": adresse,
            "apiKey": None if qb else service["api_key"],
            "config": {
                "fields": champs, "remoteAccess": False, "remoteUrl": "", "secureHeaders": False,
                "headerType": "custom", "headers": [], "networkMode": "auto", "retryRemoteOnAuthError": False,
                "notifications": {cle: True for cle in spec["notifications"]},
            },
        })
    serveur = f"PlugArr{' DEMO' if data.get('demo') else ''} ({'remote' if network == 'remote' else 'local'})"
    return {"version": 1, "exportedAt": now, "server": serveur, "services": services}, omis


def arr_control_json(payload: dict) -> bytes:
    """`JSON.stringify(payload, null, 2)`."""
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


# ------------------------------------------------ serialisation Java (nzb360)

JAVA_NUMBERS = {
    "I": ("java.lang.Integer", "12e2a0a4f7818738"),
    "J": ("java.lang.Long", "3b8be490cc8f23df"),
    "F": ("java.lang.Float", "daedc9a2db3cf0ec"),
    "D": ("java.lang.Double", "80b3c24a296bfb04"),
}


def _unites(texte: str) -> list[int]:
    """Unites UTF-16, comme `charCodeAt` : une paire pour un emoji."""
    brut = texte.encode("utf-16-be", "surrogatepass")
    return [struct.unpack(">H", brut[i : i + 2])[0] for i in range(0, len(brut), 2)]


def java_preferences(preferences: dict) -> bytes:
    """javaPreferences : HashMap serialise, types releves dans nzb360 24.4.1."""
    out = bytearray()

    def be(valeur: int, n: int) -> None:
        out.extend((valeur & ((1 << (8 * n)) - 1)).to_bytes(n, "big"))

    def utf(valeur: str) -> None:
        octets = bytearray()
        for c in _unites(valeur):
            if 1 <= c <= 127:
                octets.append(c)
            elif c <= 2047:
                octets.extend((192 | (c >> 6), 128 | (c & 63)))
            else:
                octets.extend((224 | (c >> 12), 128 | ((c >> 6) & 63), 128 | (c & 63)))
        if len(octets) > 65535:
            raise ValueError("nzb360: champ trop long / field too long")
        be(len(octets), 2)
        out.extend(octets)

    def desc(nom, uid, flags, champs, parent=None):
        out.append(0x72)
        utf(nom)
        out.extend(bytes.fromhex(uid))
        out.append(flags)
        be(len(champs), 2)
        for type_, nom_champ in champs:
            out.append(ord(type_))
            utf(nom_champ)
        out.append(0x78)
        if parent:
            parent()
        else:
            out.append(0x70)

    def number():
        desc("java.lang.Number", "86ac951d0b94e08b", 2, [])

    entrees = list(preferences.items())
    if len(entrees) > 4096:
        raise ValueError("Too many preferences")
    out.extend((0xAC, 0xED, 0, 5, 0x73))
    desc("java.util.HashMap", "0507dac1c31660d1", 3, [("F", "loadFactor"), ("I", "threshold")])
    capacite = 16
    while capacite * 0.75 < len(entrees):
        capacite *= 2
    out.extend((0x3F, 0x40, 0, 0))
    be(int(capacite * 0.75), 4)
    out.extend((0x77, 8))
    be(capacite, 4)
    be(len(entrees), 4)
    for cle, valeur in entrees:
        out.append(0x74)
        utf(cle)
        if isinstance(valeur, str):
            out.append(0x74)
            utf(valeur)
        elif isinstance(valeur, bool):
            out.append(0x73)
            desc("java.lang.Boolean", "cd207280d59cfaee", 2, [("Z", "value")])
            out.append(1 if valeur else 0)
        elif isinstance(valeur, dict) and valeur.get("t") in JAVA_NUMBERS:
            nom, uid = JAVA_NUMBERS[valeur["t"]]
            out.append(0x73)
            desc(nom, uid, 2, [(valeur["t"], "value")], number)
            out.extend(struct.pack({"I": ">i", "J": ">q", "F": ">f", "D": ">d"}[valeur["t"]], valeur["v"]))
        elif isinstance(valeur, dict) and valeur.get("t") == "set":
            elements = valeur.get("v")
            if not isinstance(elements, list) or not all(isinstance(v, str) for v in elements):
                raise ValueError("Unsupported set")
            capacite_set = 16
            while capacite_set * 0.75 < len(elements):
                capacite_set *= 2
            out.append(0x73)
            desc("java.util.HashSet", "ba44859596b8b734", 3, [])
            out.extend((0x77, 12))
            be(capacite_set, 4)
            out.extend((0x3F, 0x40, 0, 0))
            be(len(elements), 4)
            for element in elements:
                out.append(0x74)
                utf(element)
            out.append(0x78)
        else:
            raise ValueError("Unsupported preference type")
    out.append(0x78)
    return bytes(out)


def lire_java_preferences(octets: bytes) -> dict:
    """readJavaPreferences : lecture passive, tout type inconnu est refuse."""
    handles: list = []
    pos = 0

    def need(n):
        if pos + n > len(octets):
            raise ValueError("Truncated stream")

    def u1():
        nonlocal pos
        need(1)
        pos += 1
        return octets[pos - 1]

    def u2():
        nonlocal pos
        need(2)
        pos += 2
        return struct.unpack(">H", octets[pos - 2 : pos])[0]

    def i4():
        nonlocal pos
        need(4)
        pos += 4
        return struct.unpack(">i", octets[pos - 4 : pos])[0]

    def modified_utf(n):
        nonlocal pos
        need(n)
        fin = pos + n
        unites = []
        while pos < fin:
            a = octets[pos]
            pos += 1
            if a < 0x80:
                unites.append(a)
            elif (a & 0xE0) == 0xC0:
                b = octets[pos]
                pos += 1
                unites.append(((a & 0x1F) << 6) | (b & 0x3F))
            elif (a & 0xF0) == 0xE0:
                b, c = octets[pos], octets[pos + 1]
                pos += 2
                unites.append(((a & 0x0F) << 12) | ((b & 0x3F) << 6) | (c & 0x3F))
            else:
                raise ValueError("Bad string")
        if pos != fin:
            raise ValueError("Bad string")
        return b"".join(struct.pack(">H", u) for u in unites).decode("utf-16-be", "surrogatepass")

    def reference():
        h = i4() - 0x7E0000
        if h < 0 or h >= len(handles):
            raise ValueError("Bad reference")
        return handles[h]

    def class_desc():
        nonlocal pos
        tc = u1()
        if tc == 0x70:
            return None
        if tc == 0x71:
            return reference()
        if tc != 0x72:
            raise ValueError("Unsupported class descriptor")
        d = {"name": modified_utf(u2()), "fields": []}
        need(8)
        pos += 8
        handles.append(d)
        d["flags"] = u1()
        for _ in range(u2()):
            type_ = chr(u1())
            nom = modified_utf(u2())
            if type_ in ("L", "["):
                content()
            d["fields"].append((type_, nom))
        if u1() != 0x78:
            raise ValueError("Unsupported class annotation")
        d["parent"] = class_desc()
        return d

    def primitive(type_):
        nonlocal pos
        if type_ == "Z":
            return u1() != 0
        if type_ == "I":
            return i4()
        formats = {"J": (">q", 8), "F": (">f", 4), "D": (">d", 8)}
        if type_ not in formats:
            raise ValueError("Unsupported field type")
        fmt, n = formats[type_]
        need(n)
        pos += n
        return struct.unpack(fmt, octets[pos - n : pos])[0]

    def content():
        nonlocal pos
        tc = u1()
        if tc == 0x74:
            s = modified_utf(u2())
            handles.append(s)
            return s
        if tc == 0x71:
            return reference()
        if tc == 0x70:
            return None
        if tc != 0x73:
            raise ValueError("Unsupported content")
        d = class_desc()
        handle = len(handles)
        handles.append(None)
        chaine = []
        c = d
        while c:
            chaine.insert(0, c)
            c = c["parent"]
        valeurs, objets = {}, []
        for c in chaine:
            for type_, nom in c["fields"]:
                valeurs[nom] = primitive(type_)
            if c["flags"] & 1:
                while True:
                    need(1)
                    if octets[pos] == 0x78:
                        pos += 1
                        break
                    if octets[pos] == 0x77:
                        pos += 1
                        n = u1()
                        need(n)
                        pos += n
                    else:
                        objets.append(content())
        if d["name"] == "java.util.HashMap":
            if len(objets) % 2:
                raise ValueError("Bad map")
            valeur = {}
            for k in range(0, len(objets), 2):
                if not isinstance(objets[k], str):
                    raise ValueError("Bad key")  # noqa: TRY004 - une sauvegarde illisible est une ValueError pour les appelants
                valeur[objets[k]] = objets[k + 1]
        elif d["name"] == "java.util.HashSet":
            if not all(isinstance(o, str) for o in objets):
                raise ValueError("Unsupported set")
            valeur = {"t": "set", "v": objets}
        elif d["name"] == "java.lang.Boolean":
            valeur = valeurs["value"]
        else:
            type_ = next((k for k, (nom, _uid) in JAVA_NUMBERS.items() if nom == d["name"]), None)
            if type_ is None:
                raise ValueError("Unsupported type " + d["name"])
            valeur = {"t": type_, "v": valeurs["value"]}
        handles[handle] = valeur
        return valeur

    if len(octets) < 4 or octets[:4] != b"\xac\xed\x00\x05":
        raise ValueError("Not a Java stream")
    pos = 4
    carte = content()
    if not isinstance(carte, dict) or carte.get("t") == "set":
        raise ValueError("Not a map")
    if pos != len(octets):
        raise ValueError("Trailing data")
    return carte


# ---------------------------------------------------------------------- ZIP


def zip_stored(fichiers: list[tuple[str, bytes]]) -> bytes:
    """zipStored : entrees stockees, sans compression, lisibles hors ligne."""
    out, central = bytearray(), bytearray()
    for nom, donnees in fichiers:
        nom_octets = nom.encode("latin-1")
        offset = len(out)
        crc = zlib.crc32(donnees) & 0xFFFFFFFF
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 33, crc, len(donnees), len(donnees), len(nom_octets), 0)
        out += nom_octets + donnees
        central += struct.pack(
            "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 33, crc, len(donnees), len(donnees),
            len(nom_octets), 0, 0, 0, 0, 0, offset,
        )
        central += nom_octets
    debut = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(fichiers), len(fichiers), len(central), debut, 0)
    return bytes(out)


def _entrees_zip(octets: bytes) -> list[dict]:
    """zipEntries : repertoire central, y compris l'extension WinZip AES."""
    fin = -1
    for p in range(len(octets) - 22, max(-1, len(octets) - 65558), -1):
        if p >= 0 and octets[p : p + 4] == b"PK\x05\x06":
            fin = p
            break
    if fin < 0:
        raise ValueError("Not a ZIP file")
    entrees = []
    p = struct.unpack("<I", octets[fin + 16 : fin + 20])[0]
    for _ in range(struct.unpack("<H", octets[fin + 10 : fin + 12])[0]):
        if p + 46 > len(octets) or octets[p : p + 4] != b"PK\x01\x02":
            raise ValueError("Bad ZIP directory")
        flags, methode = struct.unpack("<HH", octets[p + 8 : p + 12])
        crc, taille = struct.unpack("<II", octets[p + 16 : p + 24])
        l_nom, l_extra, l_comm = struct.unpack("<HHH", octets[p + 28 : p + 34])
        offset = struct.unpack("<I", octets[p + 42 : p + 46])[0]
        nom = octets[p + 46 : p + 46 + l_nom].decode("utf-8", "replace")
        extra = octets[p + 46 + l_nom : p + 46 + l_nom + l_extra]
        if offset + 30 > len(octets) or octets[offset : offset + 4] != b"PK\x03\x04":
            raise ValueError("Bad ZIP entry")
        debut = offset + 30 + sum(struct.unpack("<HH", octets[offset + 26 : offset + 30]))
        if debut + taille > len(octets):
            raise ValueError("Truncated ZIP")
        aes = None
        q = 0
        while q + 4 <= len(extra):
            ident, longueur = struct.unpack("<HH", extra[q : q + 4])
            if ident == 0x9901 and longueur >= 7:
                aes = {
                    "version": struct.unpack("<H", extra[q + 4 : q + 6])[0],
                    "strength": extra[q + 8],
                    "method": struct.unpack("<H", extra[q + 9 : q + 11])[0],
                }
            q += 4 + longueur
        entrees.append({"name": nom, "flags": flags, "method": methode, "crc": crc, "aes": aes, "data": octets[debut : debut + taille]})
        p += 46 + l_nom + l_extra + l_comm
    return entrees


def _cles_aes(mot_de_passe: str, sel: bytes, longueur: int) -> tuple[bytes, bytes, bytes]:
    """aesKeys : PBKDF2-HMAC-SHA1 x1000."""
    bits = hashlib.pbkdf2_hmac("sha1", mot_de_passe.encode("utf-8"), sel, 1000, 2 * longueur + 2)
    return bits[:longueur], bits[longueur : 2 * longueur], bits[2 * longueur :]


def _aes_ctr(cle: bytes, donnees: bytes) -> bytes:
    """aesCtr : compteur petit-boutiste qui part de 1 (WinZip AES)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    chiffreur = Cipher(algorithms.AES(cle), modes.ECB()).encryptor()
    sortie = bytearray()
    for bloc, debut in enumerate(range(0, len(donnees), 16), start=1):
        flux = chiffreur.update(bloc.to_bytes(16, "little"))
        morceau = donnees[debut : debut + 16]
        sortie += bytes(a ^ b for a, b in zip(morceau, flux, strict=False))
    return bytes(sortie)


def lire_zip(octets: bytes, mot_de_passe: str = "") -> list[tuple[str, bytes]]:
    """readZipFiles : stocke, deflate et WinZip AES."""
    fichiers = []
    for entree in _entrees_zip(octets):
        donnees, methode = entree["data"], entree["method"]
        if methode == 99:
            longueur = {1: 16, 2: 24, 3: 32}.get((entree["aes"] or {}).get("strength"))
            if not longueur:
                raise ValueError("Unknown ZIP encryption")
            if not mot_de_passe:
                raise ErreurMotDePasse("Password required")
            l_sel = longueur // 2
            if len(donnees) < l_sel + 12:
                raise ValueError("Truncated entry")
            cle, cle_mac, controle = _cles_aes(mot_de_passe, donnees[:l_sel], longueur)
            if controle != donnees[l_sel : l_sel + 2]:
                raise ErreurMotDePasse("Wrong password")
            chiffre = donnees[l_sel + 2 : len(donnees) - 10]
            if hmac.new(cle_mac, chiffre, hashlib.sha1).digest()[:10] != donnees[-10:]:
                raise ValueError("Corrupted entry")
            donnees, methode = _aes_ctr(cle, chiffre), entree["aes"]["method"]
        elif entree["flags"] & 1:
            raise ValueError("Unsupported ZIP encryption")
        if methode == 8:
            donnees = zlib.decompress(donnees, -15)
        elif methode != 0:
            raise ValueError("Unsupported compression")
        if not (entree["aes"] and entree["aes"]["version"] == 2) and (zlib.crc32(donnees) & 0xFFFFFFFF) != entree["crc"]:
            raise ValueError("Corrupted entry")
        fichiers.append((entree["name"], donnees))
    return fichiers


def zip_aes(fichiers: list[tuple[str, bytes | str]], mot_de_passe: str, now: datetime | None = None, *, sel=None) -> bytes:
    """zipAes : en-tetes copies de la sauvegarde qbRemote (version 20, 0x801, AE-1)."""
    now = now or datetime.now().astimezone()  # heure locale, comme le ZIP de qbRemote
    heure = (now.hour << 11) | (now.minute << 5) | (now.second >> 1)
    date = ((now.year - 1980) << 9) | (now.month << 5) | now.day
    extra = bytes((0x01, 0x99, 0x07, 0x00, 0x01, 0x00, 0x41, 0x45, 0x03, 0x08, 0x00))
    out, central = bytearray(), bytearray()
    for nom, contenu in fichiers:
        clair = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
        nom_octets = nom.encode("utf-8")
        offset = len(out)
        compresseur = zlib.compressobj(9, zlib.DEFLATED, -15)
        compresse = compresseur.compress(clair) + compresseur.flush()
        grain = sel() if callable(sel) else os.urandom(16)
        cle, cle_mac, controle = _cles_aes(mot_de_passe, grain, 32)
        chiffre = _aes_ctr(cle, compresse)
        mac = hmac.new(cle_mac, chiffre, hashlib.sha1).digest()[:10]
        taille, crc = 16 + 2 + len(chiffre) + 10, zlib.crc32(clair) & 0xFFFFFFFF
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x801, 99, heure, date, crc, taille, len(clair), len(nom_octets), len(extra))
        out += nom_octets + extra + grain + controle + chiffre + mac
        central += struct.pack(
            "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0x801, 99, heure, date, crc, taille, len(clair),
            len(nom_octets), len(extra), 0, 0, 0, 0x01A40000, offset,
        )
        central += nom_octets + extra
    debut = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(fichiers), len(fichiers), len(central), debut, 0)
    return bytes(out)


# ------------------------------------------------------------------ nzb360

NZB360_FILE = "com.kevinforeman.nzb360_preferences.xml"
NZB360_PRIMARY = {
    "sonarr": "nzbdrone_server_primary_connectionstring_preference",
    "radarr": "radarr_server_primary_connectionstring_preference",
    "torrent": "torrent_server_primary_connectionstring_preference",
    "sabnzbd": "sabnzbd_server_primary_connectionstring_preference",
    "lidarr": "lidarr_server_primary_connectionstring_preference",
    "seerr": "overseerr_server_primary_connectionstring_preference",
}
NZB360_ENABLED = {
    "sonarr": "nzbdrone_server_enabled_preference",
    "radarr": "radarr_server_enabled_preference",
    "torrent": "torrent_server_enabled_preference",
    "sabnzbd": "server_enabled_preference",
    "lidarr": "lidarr_server_enabled_preference",
    "seerr": "overseerr_server_enabled_preference",
}
NZB360_NAMES = {
    "sonarr": "Sonarr", "radarr": "Radarr", "qbittorrent": "qBittorrent", "transmission": "Transmission",
    "sabnzbd": "SABnzbd", "lidarr": "Lidarr", "seerr": "Seerr",
}


def nzb_slot(sid: str) -> str:
    return "torrent" if sid in ("qbittorrent", "transmission") else sid


def nzb360_groups(data: dict, network: str = "local", ssid: str = "") -> tuple[dict, list[str], set[str]]:
    """nzb360Groups : cles ecrites par PlugArr, regroupees par application."""
    payload, omis = arr_control(
        {**data, "services": [s for s in data.get("services", []) if s.get("id") in IDS]}, network
    )
    maison = ssid if network == "remote" and ssid else ""
    groupes, bascule = {}, set()

    def adresse_locale(sid):
        service = _service(data, sid) or {}
        return _href_sans_slash(service.get("local_url") or service.get("url"))

    for service in payload["services"]:
        prefixe = {"sonarr": "nzbdrone", "radarr": "radarr", "qbittorrent": "torrent"}[service["serviceId"]]
        local = adresse_locale(service["serviceId"]) if maison else ""
        if local:
            bascule.add(service["serviceId"])
        groupe = {
            f"{prefixe}_server_enabled_preference": True,
            f"{prefixe}_server_primary_connectionstring_preference": service["url"],
            f"{prefixe}_server_local_connectionstring_preference": local,
            f"{prefixe}_server_SSID_preference": maison if local else "",
            f"{prefixe}_localconnectionswitch_preference": bool(local),
        }
        if service["serviceId"] == "qbittorrent":
            groupe.update({
                "torrent_client_preference": "qbittorrent",
                "torrent_username": service["config"]["fields"]["username"],
                "torrent_password": service["config"]["fields"]["password"],
                "torrent_rpc_path": "",
            })
        else:
            groupe[f"{prefixe}_apikey_preference"] = service["apiKey"]
        groupes[service["serviceId"]] = groupe

    sab = _service(data, "sabnzbd")
    if sab:
        adresse = _href_sans_slash(sab.get("remote_url") if network == "remote" else (sab.get("local_url") or sab.get("url")))
        cle = sab.get("api_key") if isinstance(sab.get("api_key"), str) and sab.get("api_key") != "-" else ""
        if adresse and cle:
            local = adresse_locale("sabnzbd") if maison else ""
            if local:
                bascule.add("sabnzbd")
            groupes["sabnzbd"] = {
                "server_enabled_preference": True,
                "sabnzbd_server_primary_connectionstring_preference": adresse,
                "sabnzbd_server_local_connectionstring_preference": local,
                "server_SSID_preference": maison if local else "",
                "sabapi_preference": cle,
            }
        else:
            omis.append(sab.get("name"))

    for sid, prefixe in (("lidarr", "lidarr"), ("seerr", "overseerr"), ("transmission", "torrent")):
        service = _service(data, sid)
        if not service or (sid == "transmission" and "qbittorrent" in groupes):
            continue
        adresse = _href_sans_slash(
            service.get("remote_url") if network == "remote" else (service.get("local_url") or service.get("url"))
        )
        requis = [service.get("username"), service.get("password")] if sid == "transmission" else [service.get("api_key")]
        if not adresse or not all(_present(v) for v in requis):
            omis.append(service.get("name"))
            continue
        secrets = (
            {"torrent_client_preference": "transmission", "torrent_username": service["username"],
             "torrent_password": service["password"], "torrent_rpc_path": ""}
            if sid == "transmission"
            else {f"{prefixe}_apikey_preference": service["api_key"]}
        )
        local = adresse_locale(sid) if maison else ""
        if local:
            bascule.add(sid)
        groupes[sid] = {
            f"{prefixe}_server_enabled_preference": True,
            f"{prefixe}_server_primary_connectionstring_preference": adresse,
            f"{prefixe}_server_local_connectionstring_preference": local,
            f"{prefixe}_server_SSID_preference": maison if local else "",
            f"{prefixe}_localconnectionswitch_preference": bool(local),
            **secrets,
        }
    return groupes, omis, bascule


def nzb360_export(data: dict, network: str = "local", ssid: str = "") -> dict:
    """buildNzb360Export : sauvegarde nzb360 24.4.1 sans fusion."""
    groupes, omis, bascule = nzb360_groups(data, network, ssid)
    preferences = {
        "version": "24.4.1", "nzbdrone_server_enabled_preference": False, "radarr_server_enabled_preference": False,
        "torrent_server_enabled_preference": False, "server_enabled_preference": False,
        "lidarr_server_enabled_preference": False, "overseerr_server_enabled_preference": False,
    }
    for groupe in groupes.values():
        preferences.update(groupe)
    fichiers = [
        (NZB360_FILE, java_preferences(preferences)),
        ("nzb360prefs.xml", java_preferences({"version": "24.4.1"})),
        ("servers.xml", java_preferences({})),
    ]
    return {"bytes": zip_stored(fichiers), "count": len(groupes), "omitted": omis, "switching": len(bascule)}


def nzb360_examiner(octets: bytes) -> dict:
    """inspectNzb360Backup : ce que la sauvegarde de l'utilisateur contient deja."""
    fichiers = lire_zip(octets)
    principal = next((contenu for nom, contenu in fichiers if nom == NZB360_FILE), None)
    if principal is None:
        raise ValueError("Not an nzb360 backup")
    preferences = lire_java_preferences(principal)
    configures = [
        {"id": sid, "url": preferences.get(cle), "enabled": preferences.get(NZB360_ENABLED[sid]) is True}
        for sid, cle in NZB360_PRIMARY.items()
        if isinstance(preferences.get(cle), str) and preferences.get(cle)
    ]
    profil_actif = "*"
    try:
        app = next((contenu for nom, contenu in fichiers if nom == "nzb360prefs.xml"), None)
        valeur = app and lire_java_preferences(app).get("lastActiveProfile")
        if isinstance(valeur, str) and valeur:
            profil_actif = valeur
    except ValueError:
        pass
    return {"files": fichiers, "preferences": preferences, "configured": configures, "activeProfile": profil_actif}


def nzb_profils(base: dict) -> tuple[dict, list[dict]]:
    """nzbProfiles : servers.xml associe "servers" a un HashSet "<3 chiffres><nom>"."""
    import re

    fichier = next((contenu for nom, contenu in base["files"] if nom == "servers.xml"), None)
    carte = lire_java_preferences(fichier) if fichier else {}
    ensemble = carte.get("servers")
    if ensemble is not None and not (isinstance(ensemble, dict) and ensemble.get("t") == "set"):
        raise ValueError("Unsupported servers.xml")
    entrees = []
    for entree in ensemble["v"] if ensemble else []:
        m = re.match(r"^(\d{3})(.*)$", entree, re.DOTALL)
        if not m:
            raise ValueError("Unknown profile entry")
        entrees.append({"entry": entree, "id": m.group(1), "name": m.group(2).removesuffix("*"), "main": m.group(2).endswith("*")})
    return carte, entrees


def nzb360_fusion_profil(base: dict, data: dict, network="local", ssid="", nom="PlugArr") -> dict:
    """mergeNzb360Profile : profil « PlugArr » separe, rien n'est remplace."""
    groupes, omis, bascule = nzb360_groups(data, network, ssid)
    carte, entrees = nzb_profils(base)
    if not entrees:
        entrees.append({"entry": "000Default*", "id": "000", "name": "Default", "main": True})
    existant = next((e for e in entrees if not e["main"] and e["name"] == nom), None)
    ident = existant["id"] if existant else str(max([0, *[int(e["id"]) for e in entrees]]) + 1).zfill(3)
    if int(ident) > 999:
        raise ValueError("Too many profiles")
    if not existant:
        entrees.append({"entry": ident + nom, "id": ident, "name": nom, "main": False})
    carte["servers"] = {"t": "set", "v": [e["entry"] for e in entrees]}
    reglages = {}
    for groupe in groupes.values():
        reglages.update(groupe)
    ecrits = {"servers.xml": java_preferences(carte), f"{ident}.xml": java_preferences(reglages)}
    fichiers = [(f, ecrits.get(f, c)) for f, c in base["files"]]
    for f, c in ecrits.items():
        if not any(nom_f == f for nom_f, _ in fichiers):
            fichiers.append((f, c))
    return {
        "bytes": zip_stored(fichiers), "added": list(groupes), "omitted": omis, "switching": len(bascule),
        "profile": {"id": ident, "name": nom, "updated": bool(existant), "others": [e["name"] for e in entrees if e["id"] != ident]},
    }


def nzb360_fusion(base: dict, data: dict, network="local", ssid="", remplacer=()) -> dict:
    """mergeNzb360 : dans le profil Default, application par application."""
    groupes, omis, bascule = nzb360_groups(data, network, ssid)
    preferences = dict(base["preferences"])
    ajoutes, remplaces, gardes = [], [], []
    for sid, groupe in groupes.items():
        present = any(c["id"] == nzb_slot(sid) for c in base["configured"])
        if present and nzb_slot(sid) not in remplacer:
            gardes.append(nzb_slot(sid))
            continue
        preferences.update(groupe)
        (remplaces if present else ajoutes).append(sid)
    fichiers = [(nom, java_preferences(preferences) if nom == NZB360_FILE else contenu) for nom, contenu in base["files"]]
    return {
        "bytes": zip_stored(fichiers), "added": ajoutes, "replaced": remplaces, "kept": gardes, "omitted": omis,
        "switching": len([sid for sid in bascule if nzb_slot(sid) not in gardes]),
    }


# ----------------------------------------------------------------- qbRemote

QB_APP_VERSION = "1.8.0(73)"
QB_PASSWORD_MIN = 4


def _iso(now: datetime) -> str:
    """`Date.toISOString()` : UTC, millisecondes, suffixe Z."""
    utc = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _json_compact(valeur) -> str:
    """`JSON.stringify(valeur)`."""
    return json.dumps(valeur, ensure_ascii=False, separators=(",", ":"))


def qbremote_serveur(data: dict, network: str = "local", ssid: str = "") -> dict | None:
    """buildQbRemoteServer : schema releve dans une sauvegarde qbRemote 1.8.0."""
    if network not in ("local", "remote"):
        raise ValueError("Unknown export network")
    service = _service(data, "qbittorrent")
    if not service or not _present(service.get("username")) or not _present(service.get("password")):
        return None

    def analyse(adresse):
        lu = _url(adresse)
        if lu is None:
            return None
        morceaux, port = lu
        schema = morceaux.scheme.lower()
        hote = morceaux.hostname.lower()
        return {
            "scheme": schema,
            "host": f"[{hote}]" if ":" in hote else hote,
            "port": str(port) if port is not None and port != (443 if schema == "https" else 80) else ("443" if schema == "https" else "80"),
            "path": morceaux.path if morceaux.path and morceaux.path != "/" else None,
        }

    principal = analyse(service.get("remote_url") if network == "remote" else (service.get("local_url") or service.get("url")))
    if not principal:
        return None
    local = analyse(service.get("local_url") or service.get("url")) if network == "remote" and ssid else None
    return {
        "id": 1, "name": f"PlugArr{' DEMO' if data.get('demo') else ''}", "scheme": principal["scheme"],
        "host": principal["host"], "port": principal["port"], "path": principal["path"], "trustCertificates": False,
        "username": service["username"], "password": service["password"], "customHeaders": None,
        "localSsid": ssid if local else None, "localScheme": local["scheme"] if local else None,
        "localHost": local["host"] if local else None, "localPort": local["port"] if local else None,
        "localPath": local["path"] if local else None, "localTrustCertificates": False if local else None,
        "localDisableAuthentication": None, "apiKey": None, "basicAuthEnabled": None, "basicAuthUsername": None,
        "basicAuthPassword": None, "macAddress": None, "wolBroadcastAddress": None, "wolPort": None,
        "notifyOnComplete": None, "apiVersion": None, "networkStackOverride": "inherit",
        "defaultTls": {"trustMode": "system"}, "localTls": {"trustMode": "system"}, "clientIdentity": {"type": "none"},
    }


def qbremote_export(data: dict, network: str, ssid: str, mot_de_passe: str, now: datetime | None = None) -> bytes | None:
    """buildQbRemoteExport : manifest.json et servers.json, chiffres AES-256."""
    serveur = qbremote_serveur(data, network, ssid)
    if not serveur:
        return None
    now = now or datetime.now(UTC)
    manifeste = {"version": 1, "createdAt": _iso(now), "appVersion": QB_APP_VERSION}
    return zip_aes([("manifest.json", _json_compact(manifeste)), ("servers.json", _json_compact([serveur]))], mot_de_passe, now)


def qbremote_fusion(octets: bytes, mot_de_passe: str, data: dict, network="local", ssid="", now: datetime | None = None) -> dict | None:
    """mergeQbRemote : ajoute le serveur PlugArr a la sauvegarde de l'utilisateur."""
    serveur = qbremote_serveur(data, network, ssid)
    if not serveur:
        return None
    now = now or datetime.now(UTC)
    fichiers = [list(f) for f in lire_zip(octets, mot_de_passe)]
    index = next((i for i, (nom, _c) in enumerate(fichiers) if nom == "servers.json"), -1)
    serveurs = [] if index < 0 else json.loads(fichiers[index][1].decode("utf-8"))
    if not isinstance(serveurs, list):
        raise ValueError("Unexpected servers.json")  # noqa: TRY004 - meme contrat que la lecture de l'archive
    meme = next((i for i, s in enumerate(serveurs) if isinstance(s, dict) and s.get("name") == serveur["name"]), -1)
    if meme >= 0:
        serveur["id"] = serveurs[meme].get("id")
        serveurs[meme] = serveur
    else:
        serveur["id"] = max([0, *[int(s.get("id") or 0) for s in serveurs if isinstance(s, dict)]]) + 1
        serveurs.append(serveur)
    contenu = _json_compact(serveurs)
    if index < 0:
        fichiers.append(["servers.json", contenu])
    else:
        fichiers[index] = ["servers.json", contenu]
    if not any(nom == "manifest.json" for nom, _c in fichiers):
        fichiers.insert(0, ["manifest.json", _json_compact({"version": 1, "createdAt": _iso(now), "appVersion": QB_APP_VERSION})])
    return {
        "bytes": zip_aes([tuple(f) for f in fichiers], mot_de_passe, now),
        "kept": len(serveurs) - 1,
        "updated": meme >= 0,
    }


# ------------------------------------------------------------------- QR code

# ISO/IEC 18004, mode octet, correction M, versions 1 a 10 (QR_BLOCKS...).
QR_BLOCKS = [None, [[1, 16]], [[1, 28]], [[1, 44]], [[2, 32]], [[2, 43]], [[4, 27]], [[4, 31]], [[2, 38], [2, 39]], [[3, 36], [2, 37]], [[4, 43], [1, 44]]]
QR_ECC = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
QR_ALIGN = [None, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]]


def _qr_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _qr_ecc(donnees: list[int], degre: int) -> list[int]:
    diviseur = [0] * (degre - 1) + [1]
    racine = 1
    for _ in range(degre):
        for j in range(len(diviseur)):
            diviseur[j] = _qr_mul(diviseur[j], racine)
            if j + 1 < len(diviseur):
                diviseur[j] ^= diviseur[j + 1]
        racine = _qr_mul(racine, 2)
    resultat = [0] * degre
    for b in donnees:
        facteur = b ^ resultat.pop(0)
        resultat.append(0)
        for i, c in enumerate(diviseur):
            resultat[i] ^= _qr_mul(c, facteur)
    return resultat


def qr_matrice(texte: str, masque_force: int | None = None) -> dict:
    """qrMatrix : renvoie {"version", "mask", "modules"} (lignes de booleens)."""
    octets = list(texte.encode("utf-8"))

    def capacite(v):
        return sum(n * taille for n, taille in QR_BLOCKS[v])

    version = 1
    while version <= 10 and 4 + (8 if version < 10 else 16) + 8 * len(octets) > 8 * capacite(version):
        version += 1
    if version > 10:
        raise ValueError("Too long for a QR code")
    bits: list[int] = []

    def put(valeur, n):
        for i in range(n - 1, -1, -1):
            bits.append((valeur >> i) & 1)

    put(4, 4)
    put(len(octets), 8 if version < 10 else 16)
    for b in octets:
        put(b, 8)
    total = 8 * capacite(version)
    put(0, min(4, total - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad = 0xEC
    while len(bits) < total:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    donnees = [int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8)]
    blocs, offset = [], 0
    for n, taille in QR_BLOCKS[version]:
        for _ in range(n):
            blocs.append(donnees[offset : offset + taille])
            offset += taille
    corrections = [_qr_ecc(bloc, QR_ECC[version]) for bloc in blocs]
    mots = []
    for i in range(max(len(b) for b in blocs)):
        for bloc in blocs:
            if i < len(bloc):
                mots.append(bloc[i])
    for i in range(QR_ECC[version]):
        for ecc in corrections:
            mots.append(ecc[i])
    taille = 17 + 4 * version
    modules = [[False] * taille for _ in range(taille)]
    reserve = [[False] * taille for _ in range(taille)]

    def pose(x, y, fonce):
        modules[y][x] = fonce
        reserve[y][x] = True

    for i in range(taille):
        pose(6, i, i % 2 == 0)
        pose(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (taille - 4, 3), (3, taille - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y, d = cx + dx, cy + dy, max(abs(dx), abs(dy))
                if 0 <= x < taille and 0 <= y < taille:
                    pose(x, y, d not in (2, 4))
    alignement = QR_ALIGN[version]
    dernier = len(alignement) - 1
    for i in range(len(alignement)):
        for j in range(len(alignement)):
            if (i == 0 and j == 0) or (i == 0 and j == dernier) or (i == dernier and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    pose(alignement[i] + dx, alignement[j] + dy, max(abs(dx), abs(dy)) != 1)

    def format_(masque):
        valeur = (0 << 3) | masque
        reste = valeur
        for _ in range(10):
            reste = (reste << 1) ^ ((reste >> 9) * 0x537)
        f = ((valeur << 10) | reste) ^ 0x5412

        def bit(i):
            return ((f >> i) & 1) == 1

        for i in range(6):
            pose(8, i, bit(i))
        pose(8, 7, bit(6))
        pose(8, 8, bit(7))
        pose(7, 8, bit(8))
        for i in range(9, 15):
            pose(14 - i, 8, bit(i))
        for i in range(8):
            pose(taille - 1 - i, 8, bit(i))
        for i in range(8, 15):
            pose(8, taille - 15 + i, bit(i))
        pose(8, taille - 8, True)

    format_(0)
    if version >= 7:
        reste = version
        for _ in range(12):
            reste = (reste << 1) ^ ((reste >> 11) * 0x1F25)
        v = (version << 12) | reste
        for i in range(18):
            fonce = ((v >> i) & 1) == 1
            a, b = taille - 11 + i % 3, i // 3
            pose(a, b, fonce)
            pose(b, a, fonce)
    index = 0
    droite = taille - 1
    while droite >= 1:
        if droite == 6:
            droite = 5
        for vert in range(taille):
            for j in range(2):
                x = droite - j
                y = taille - 1 - vert if ((droite + 1) & 2) == 0 else vert
                if not reserve[y][x] and index < len(mots) * 8:
                    modules[y][x] = ((mots[index >> 3] >> (7 - (index & 7))) & 1) == 1
                    index += 1
        droite -= 2
    masques = [
        lambda x, y: (x + y) % 2 == 0,
        lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: x * y % 2 + x * y % 3 == 0,
        lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    ]

    def applique(masque):
        for y in range(taille):
            for x in range(taille):
                if not reserve[y][x] and masques[masque](x, y):
                    modules[y][x] = not modules[y][x]

    def penalite():
        score, fonces = 0, 0
        lignes = [*modules, *[[modules[y][x] for y in range(taille)] for x in range(taille)]]
        for ligne in lignes:
            serie = 1
            for i in range(1, taille + 1):
                if i < taille and ligne[i] == ligne[i - 1]:
                    serie += 1
                else:
                    if serie >= 5:
                        score += serie - 2
                    serie = 1
            t = "".join("1" if m else "0" for m in ligne)
            for motif in ("10111010000", "00001011101"):
                i = t.find(motif)
                while i >= 0:
                    score += 40
                    i = t.find(motif, i + 1)
        for y in range(taille):
            for x in range(taille):
                if modules[y][x]:
                    fonces += 1
                if x < taille - 1 and y < taille - 1:
                    c = modules[y][x]
                    if c == modules[y][x + 1] and c == modules[y + 1][x] and c == modules[y + 1][x + 1]:
                        score += 3
        return score + 10 * (abs(fonces * 20 - taille * taille * 10) // (taille * taille))

    meilleur = -1 if masque_force is None else masque_force
    if meilleur < 0:
        plus_bas = None
        for masque in range(8):
            applique(masque)
            format_(masque)
            score = penalite()
            if plus_bas is None or score < plus_bas:
                plus_bas, meilleur = score, masque
            applique(masque)
    applique(meilleur)
    format_(meilleur)
    return {"version": version, "mask": meilleur, "modules": modules}


def qr_terminal(texte: str):
    """Le QR en demi-blocs, noir sur blanc impose : un terminal sombre
    l'inverserait, et tous les lecteurs ne lisent pas un QR inverse."""
    from rich.text import Text

    modules = qr_matrice(texte)["modules"]
    marge = 2
    taille = len(modules) + 2 * marge

    def fonce(x, y):
        x, y = x - marge, y - marge
        return 0 <= y < len(modules) and 0 <= x < len(modules) and modules[y][x]

    rendu = Text()
    for y in range(0, taille, 2):
        for x in range(taille):
            haut, bas = fonce(x, y), fonce(x, y + 1)
            # Blanc VIF : le « white » de base est un gris clair dans bien des
            # terminaux, et le contraste compte pour l'appareil photo.
            rendu.append("▀", style=f"{'black' if haut else 'bright_white'} on {'black' if bas else 'bright_white'}")
        rendu.append("\n")
    return rendu


# --------------------------------------------------------- donnees du rapport


def donnees_rapport(cfg, *, resultat_distant: dict | None = None, demo: bool = False) -> dict:
    """Les donnees que le rapport web donne a ces exports, calculees ici."""
    from . import catalog, dashboard, orchestrator, remote_access

    hote_local = dashboard.resolve_host(cfg)[0]
    urls = (resultat_distant or {}).get("urls", {})
    services = []
    for sid, inst in orchestrator.iter_selected(cfg):
        services.append({
            "id": sid,
            "name": catalog.get(sid).display_name,
            "url": inst.url(cfg.host) if inst.has_web_ui else "",
            "remote_url": urls.get(sid, ""),
            "local_url": inst.url(hote_local) if inst.has_web_ui else "",
            "username": inst.username or "-",
            "password": inst.password or "-",
            "api_key": inst.api_key or "-",
        })
    return {"services": services, "demo": demo, "remote": resultat_distant or remote_access.summary(cfg)}
