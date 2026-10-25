"""Version einer Android-App direkt aus der APK lesen – für den Update-Hinweis in den Handy-Apps.

Die APK ist ein ZIP mit einem binären AndroidManifest.xml (AXML). Gelesen werden nur die Attribute
versionCode und versionName des ersten Elements <manifest>; erkannt werden sie an ihrer Ressourcen-ID,
nicht am Namen. So muss beim Hochladen einer neuen APK nichts zusätzlich gepflegt werden.
"""
import struct
import zipfile
from functools import lru_cache

VERSION_CODE = 0x0101021B
VERSION_NAME = 0x0101021C
TYP_STRING = 0x03
TYP_INT_DEC = 0x10
TYP_INT_HEX = 0x11


def version(datei):
    """{"code": 5, "name": "1.4"} oder None, wenn die Datei fehlt oder nicht lesbar ist."""
    try:
        stand = datei.stat().st_mtime_ns
    except OSError:
        return None
    return _version(str(datei), stand)


@lru_cache(maxsize=8)
def _version(pfad, _stand):
    try:
        with zipfile.ZipFile(pfad) as apk:
            return _manifest(apk.read("AndroidManifest.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, struct.error, ValueError, IndexError):
        return None


def _strings(daten, start):
    anzahl, _, flags, beginn = struct.unpack_from("<IIII", daten, start + 8)
    utf8 = flags & 0x100
    offsets = struct.unpack_from(f"<{anzahl}I", daten, start + 28)
    ergebnis = []
    for o in offsets:
        p = start + beginn + o
        if utf8:
            p += 2 if daten[p] & 0x80 else 1           # Länge in Zeichen
            laenge = daten[p]
            if laenge & 0x80:
                laenge = ((laenge & 0x7F) << 8) | daten[p + 1]
                p += 1
            ergebnis.append(daten[p + 1:p + 1 + laenge].decode("utf-8"))
        else:
            laenge = struct.unpack_from("<H", daten, p)[0]
            if laenge & 0x8000:
                laenge = ((laenge & 0x7FFF) << 16) | struct.unpack_from("<H", daten, p + 2)[0]
                p += 2
            ergebnis.append(daten[p + 2:p + 2 + 2 * laenge].decode("utf-16-le"))
    return ergebnis


def _manifest(daten):
    strings, ids = [], []
    pos = struct.unpack_from("<HHI", daten, 0)[1]       # hinter dem Kopf der Datei
    while pos < len(daten):
        typ, kopf, groesse = struct.unpack_from("<HHI", daten, pos)
        if typ == 0x0001:                                # Zeichenketten
            strings = _strings(daten, pos)
        elif typ == 0x0180:                              # Ressourcen-IDs der Attributnamen
            ids = list(struct.unpack_from(f"<{(groesse - kopf) // 4}I", daten, pos + kopf))
        elif typ == 0x0102:                              # erstes Element: <manifest>
            beginn, groesse_attr, anzahl = struct.unpack_from("<HHH", daten, pos + kopf + 8)
            werte = {}
            for i in range(anzahl):
                a = pos + kopf + beginn + i * groesse_attr
                name, roh, _, _, datentyp, wert = struct.unpack_from("<IIHBBI", daten, a + 4)
                rid = ids[name] if name < len(ids) else None
                if rid == VERSION_CODE and datentyp in (TYP_INT_DEC, TYP_INT_HEX):
                    werte["code"] = wert
                elif rid == VERSION_NAME:
                    index = wert if datentyp == TYP_STRING else roh
                    if index != 0xFFFFFFFF:
                        werte["name"] = strings[index]
            return {"code": werte["code"], "name": werte.get("name", "")} if "code" in werte else None
        pos += groesse
    return None
