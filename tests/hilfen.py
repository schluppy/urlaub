"""Gemeinsame Testhilfen."""
import struct
import zipfile

from freigaben import apk
from konten.models import Familie


def fam(name="Muster", bundesland="SH"):
    """Testfamilie – derselbe Name wie bei `beispieldaten`."""
    return Familie.objects.get_or_create(name=name, defaults={"bundesland": bundesland})[0]


def apk_bauen(datei, code, name):
    """Eine APK, die nur aus einem binären Manifest mit versionCode und versionName besteht."""
    def block(typ, kopf, inhalt):
        return struct.pack("<HHI", typ, 8 + len(kopf), 8 + len(kopf) + len(inhalt)) + kopf + inhalt

    texte = ["versionCode", "versionName", name, "manifest"]
    roh, offsets = b"", []
    for t in texte:
        offsets.append(len(roh))
        roh += struct.pack("<H", len(t)) + t.encode("utf-16-le") + b"\0\0"
    roh += b"\0" * (-len(roh) % 4)
    pool = block(0x0001, struct.pack("<IIIII", len(texte), 0, 0, 28 + 4 * len(texte), 0),
                 struct.pack(f"<{len(texte)}I", *offsets) + roh)
    ids = block(0x0180, b"", struct.pack("<II", apk.VERSION_CODE, apk.VERSION_NAME))
    attribute = (struct.pack("<IIIHBBI", 0xFFFFFFFF, 0, 0xFFFFFFFF, 8, 0, apk.TYP_INT_DEC, code)
                 + struct.pack("<IIIHBBI", 0xFFFFFFFF, 1, 2, 8, 0, apk.TYP_STRING, 2))
    element = block(0x0102, struct.pack("<II", 1, 0xFFFFFFFF),
                    struct.pack("<IIHHHHHH", 0xFFFFFFFF, 3, 20, 20, 2, 0, 0, 0) + attribute)
    with zipfile.ZipFile(datei, "w") as z:
        z.writestr("AndroidManifest.xml", block(0x0003, b"", pool + ids + element))
