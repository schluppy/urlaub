"""Koordinaten aus einem Google-Maps-Link (oder kopierten Koordinaten) lesen.

Google Maps hat für Orte keine offene Schnittstelle; der geteilte Link enthält die Koordinaten aber:
  …/place/Name/@50.1110033,-3.2225803,17z/data=…!3d50.111!4d-3.22…
„!3d…!4d…“ ist die Stecknadel des Orts, „@…“ nur die Mitte des Kartenausschnitts (oft daneben).
Kurzlinks (maps.app.goo.gl) leiten auf die lange Adresse weiter; nur diese Weiterleitung wird abgerufen.
"""
import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import unquote, urlparse

import requests

KURZ_HOSTS = {"maps.app.goo.gl", "goo.gl"}
ZAHL = r"(-?\d{1,3}\.\d+)"
MUSTER = [
    re.compile(rf"!3d{ZAHL}!4d{ZAHL}"),                                  # Stecknadel des Orts
    re.compile(rf"[?&](?:q|query|ll|destination|center)={ZAHL},\+?{ZAHL}"),
    re.compile(rf"/(?:search|place|dir)/{ZAHL},\+?{ZAHL}"),
    re.compile(rf"/@{ZAHL},{ZAHL}"),                                     # Kartenmitte – zuletzt
]
NUR_KOORDINATEN = re.compile(rf"^\s*{ZAHL}\s*[,;]?\s+{ZAHL}\s*$|^\s*{ZAHL}\s*[,;]\s*{ZAHL}\s*$")
STELLEN = Decimal("0.000001")
GOOGLE_HOST = re.compile(r"^(www\.|maps\.)?google\.(com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$")


class KeineKoordinaten(ValueError):
    pass


def runden(wert):
    return Decimal(wert).quantize(STELLEN, rounding=ROUND_HALF_UP)


def _pruefen(breite, laenge):
    b, l = runden(breite), runden(laenge)
    if not (-90 <= b <= 90 and -180 <= l <= 180):
        raise KeineKoordinaten("Die Koordinaten liegen außerhalb des gültigen Bereichs.")
    return b, l


def _aufloesen(url, schritte=3):
    """Kurzlink → lange Google-Maps-Adresse (nur der Location-Header, keine Seite laden)."""
    for _ in range(schritte):
        teile = urlparse(url)
        if teile.scheme != "https" or teile.hostname not in KURZ_HOSTS:
            return url
        try:
            antwort = requests.get(url, allow_redirects=False, timeout=8,
                                   headers={"User-Agent": "Mozilla/5.0 (Urlaubsplaner)"})
        except requests.RequestException:
            raise KeineKoordinaten("Google Maps ist gerade nicht erreichbar. Bitte später erneut versuchen "
                                   "oder die Koordinaten von Hand eintragen.")
        ziel = antwort.headers.get("Location")
        if antwort.status_code not in (301, 302, 303, 307, 308) or not ziel:
            raise KeineKoordinaten("Der Kurzlink führt zu keinem Ort in Google Maps.")
        url = ziel
    return url


def koordinaten(text):
    """(Breite, Länge) mit 6 Nachkommastellen aus Link oder „50.1110033, -3.2225803“."""
    text = (text or "").strip()
    treffer = NUR_KOORDINATEN.match(text)
    if treffer:
        werte = [w for w in treffer.groups() if w is not None]
        return _pruefen(*werte)
    if not text.lower().startswith(("http://", "https://")):
        raise KeineKoordinaten("Bitte einen Link aus Google Maps oder Koordinaten wie „50.1110033, -3.2225803“ einfügen.")
    adresse = unquote(_aufloesen(text))
    if not GOOGLE_HOST.match(urlparse(adresse).hostname or ""):
        raise KeineKoordinaten("Das ist kein Link aus Google Maps.")
    for muster in MUSTER:
        treffer = muster.search(adresse)
        if treffer:
            return _pruefen(*treffer.groups())
    raise KeineKoordinaten("Im Link stehen keine Koordinaten. In Google Maps den Ort anklicken und dann "
                           "„Teilen → Link kopieren“ nutzen – oder die Koordinaten von Hand eintragen.")
