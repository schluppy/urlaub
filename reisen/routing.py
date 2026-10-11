"""TomTom-Anbindung: Geocoding für Orte und Routing für Etappen.

Alles, was TomTom-spezifisch ist, steht hier – ein späterer Wechsel auf
Orbis (Routing v3) betrifft nur diese Datei. Verwendet wird die Routing API v1,
weil nur sie Länge, Breite, Höhe, Achslast und Achszahl kennt.
Doku: https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone

BASIS = "https://api.tomtom.com"
TIMEOUT = 60


class TomTomFehler(Exception):
    """Fehler mit verständlicher Meldung für die Oberfläche."""


def _key(familie, art):
    """Schlüssel der Familie (oder Standardschlüssel aus .env); jeder Abruf wird gezählt."""
    from konten.models import ApiNutzung

    if familie is not None:
        key, eintrag = familie.tomtom()
    else:
        key, eintrag = settings.TOMTOM_API_KEY, None
    if not key:
        raise TomTomFehler("Kein TomTom-API-Schlüssel hinterlegt (TOMTOM_API_KEY in .env).")
    ApiNutzung.zaehlen(familie, eintrag, art)
    return key


def _abrufen(url, params, body=None, familie=None, art="routing"):
    """GET, oder POST mit JSON-Body, wenn `body` angegeben ist."""
    params = {"key": _key(familie, art), **params}
    try:
        if body is None:
            antwort = requests.get(url, params=params, timeout=TIMEOUT)
        else:
            antwort = requests.post(url, params=params, json=body, timeout=TIMEOUT)
    except requests.Timeout:
        raise TomTomFehler("TomTom antwortet nicht (Zeitüberschreitung). Bitte später erneut versuchen.")
    except requests.RequestException as e:
        raise TomTomFehler(f"TomTom nicht erreichbar: {e.__class__.__name__}")
    if antwort.status_code == 200:
        return antwort.json()
    try:
        j = antwort.json()
        detail = (j.get("error") or {}).get("description") or (j.get("detailedError") or {}).get("message") or ""
    except ValueError:
        detail = ""
    meldung = {
        400: "Anfrage ungültig. Häufigste Ursache: Start oder Ziel liegt nicht an einer befahrbaren "
             "Straße – Koordinaten des Orts prüfen.",
        401: "TomTom-API-Schlüssel ungültig.",
        403: "TomTom-API-Schlüssel ohne Berechtigung für diese API.",
        429: "Zu viele Anfragen an TomTom. Bitte in einer Minute erneut versuchen.",
        500: "TomTom konnte die Route nicht berechnen (Rechenzeit überschritten o. ä.).",
    }.get(antwort.status_code, f"TomTom meldet Fehler {antwort.status_code}.")
    raise TomTomFehler(f"{meldung} (TomTom: {detail})" if detail else meldung)


# --- Kartenkacheln (Map Display API) -----------------------------------------


def kachel(z, x, y, familie=None):
    """Rasterkachel 256 px. Wird über den eigenen Server ausgeliefert, damit der API-Key
    nicht im Browser landet (die Domain-Sperre von TomTom wirkt nur über CORS, nicht bei Bildern)."""
    if not (0 <= z <= 20 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError("Kachel außerhalb der Karte")
    try:
        antwort = requests.get(f"{BASIS}/map/1/tile/basic/main/{z}/{x}/{y}.png",
                               params={"key": _key(familie, "kachel"), "view": "Unified", "language": "de-DE"},
                               timeout=15)
    except requests.RequestException as e:
        raise TomTomFehler(f"Kachel nicht abrufbar: {e.__class__.__name__}")
    if antwort.status_code != 200:
        raise TomTomFehler(f"Kachel: TomTom meldet {antwort.status_code}")
    return antwort.content


# --- Geocoding ---------------------------------------------------------------


@dataclass
class Fundstelle:
    breite: Decimal
    laenge: Decimal
    adresse: str
    land: str
    genauigkeit: str


def geocode(adresse, familie=None):
    """Adresse → Koordinaten. Nimmt den besten Treffer."""
    daten = _abrufen(f"{BASIS}/search/2/geocode/{quote(adresse)}.json", {"limit": 1, "language": "de-DE"},
                     familie=familie, art="geocoding")
    if not daten.get("results"):
        raise TomTomFehler(f"Adresse nicht gefunden: {adresse}")
    t = daten["results"][0]
    return Fundstelle(
        breite=Decimal(str(t["position"]["lat"])).quantize(Decimal("0.000001")),
        laenge=Decimal(str(t["position"]["lon"])).quantize(Decimal("0.000001")),
        adresse=t["address"].get("freeformAddress", ""),
        land=t["address"].get("countryCode", ""),
        genauigkeit=t.get("type", ""),
    )


def ort_geocodieren(ort, speichern=True):
    """Setzt Koordinaten (und ggf. Land) eines Orts aus seiner Adresse."""
    if not ort.adresse:
        raise TomTomFehler(f"„{ort}“ hat keine Adresse.")
    f = geocode(ort.adresse, familie=ort.familie)
    ort.breite, ort.laenge = f.breite, f.laenge
    if not ort.land:
        ort.land = f.land
    if speichern:
        ort.save(update_fields=["breite", "laenge", "land"])
    return f


# --- Routing -----------------------------------------------------------------


def fahrzeug_parameter(profil):
    """Fahrzeugprofil → TomTom-Parameter; leere Felder werden nicht gesendet."""
    if profil is None:
        return {}
    werte = {
        "vehicleLength": profil.laenge_m,
        "vehicleWidth": profil.breite_m,
        "vehicleHeight": profil.hoehe_m,
        "vehicleWeight": profil.gesamtgewicht_kg,
        "vehicleAxleWeight": profil.achslast_kg,
        "vehicleNumberOfAxles": profil.achszahl,
        "vehicleMaxSpeed": profil.hoechstgeschwindigkeit_kmh,
    }
    params = {k: v for k, v in werte.items() if v}
    if profil.verbrauchskurve:
        params["vehicleEngineType"] = "combustion"
        params["constantSpeedConsumptionInLitersPerHundredkm"] = profil.verbrauchskurve
    return params


@dataclass
class Route:
    entfernung_km: Decimal
    fahrzeit: timedelta
    verkehr: timedelta = timedelta()
    laender: list = field(default_factory=list)
    vignetten: list = field(default_factory=list)
    faehre: bool = False
    verbrauch_l: Decimal | None = None
    abfahrt: str = ""
    wirksam: dict = field(default_factory=dict)
    linie: list = field(default_factory=list)    # vereinfachter Streckenverlauf [[lat, lon], …]

    def als_details(self):
        return {
            "laender": self.laender, "vignetten": self.vignetten, "faehre": self.faehre,
            "verkehr_min": round(self.verkehr / timedelta(minutes=1)),
            "verbrauch_l": str(self.verbrauch_l) if self.verbrauch_l is not None else None,
            "abfahrt": self.abfahrt, "wirksam": self.wirksam, "linie": self.linie,
        }


LINIE_TOLERANZ_GRAD = 0.0005   # ≈ 50 m – für die Kartenübersicht nicht sichtbar


def vereinfachen(punkte, toleranz=LINIE_TOLERANZ_GRAD):
    """Douglas-Peucker: lässt Punkte weg, die weniger als `toleranz` von der Linie abweichen.
    Kurven bleiben erhalten, gerade Autobahnstücke schrumpfen auf wenige Punkte."""
    if len(punkte) < 3:
        return [[round(a, 5), round(b, 5)] for a, b in punkte]
    kos = math.cos(math.radians(sum(p[0] for p in punkte) / len(punkte)))   # Längengrade schrumpfen nach Norden

    def abstand(p, a, b):
        px, py, ax, ay, bx, by = p[1] * kos, p[0], a[1] * kos, a[0], b[1] * kos, b[0]
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    behalten = {0, len(punkte) - 1}
    stapel = [(0, len(punkte) - 1)]
    while stapel:
        anfang, ende = stapel.pop()
        weitester, entfernung = None, toleranz
        for i in range(anfang + 1, ende):
            d = abstand(punkte[i], punkte[anfang], punkte[ende])
            if d > entfernung:
                weitester, entfernung = i, d
        if weitester is not None:
            behalten.add(weitester)
            stapel += [(anfang, weitester), (weitester, ende)]
    return [[round(punkte[i][0], 5), round(punkte[i][1], 5)] for i in sorted(behalten)]


def berechne_route(start, ziel, profil=None, abfahrt=None, vignetten_meiden="", familie=None):
    """Route zwischen zwei Punkten (lat, lon). `abfahrt` als aware datetime;
    liegt sie in der Vergangenheit, rechnet TomTom ohne Verkehrsprognose."""
    params = {
        "travelMode": "bus",          # wie der TomTom-Web-Planer; Maße wirken (geprüft)
        "routeType": "fastest",
        "sectionType": ["tollVignette", "country", "ferry"],
        "report": "effectiveSettings",
        "routeRepresentation": "polyline",   # Streckenverlauf für die Karte
        **fahrzeug_parameter(profil),
    }
    abfahrt_text = ""
    if abfahrt and abfahrt > timezone.now():
        abfahrt_text = timezone.localtime(abfahrt).replace(tzinfo=None).isoformat(timespec="seconds")
        params["departAt"] = abfahrt_text
        params["traffic"] = "true"
    else:
        params["traffic"] = "false"
    # avoidVignette gibt es nur im POST-Body (per GET: 400 „parameter not supported“);
    # ein leerer POST-Body wird ebenfalls abgelehnt, daher sonst GET.
    body = {}
    meiden = [c.strip().upper() for c in vignetten_meiden.split(",") if c.strip()]
    if meiden:
        body["avoidVignette"] = meiden

    punkte = ":".join(f"{lat},{lon}" for lat, lon in (start, ziel))
    daten = _abrufen(f"{BASIS}/routing/1/calculateRoute/{punkte}/json", params, body or None, familie=familie)
    if not daten.get("routes"):
        raise TomTomFehler("TomTom hat keine Route gefunden.")
    r = daten["routes"][0]
    s = r["summary"]

    laender, vignetten, faehre = [], [], False
    for sec in r.get("sections", []):
        typ = sec.get("sectionType")
        land = sec.get("countryCode", "")
        if typ == "COUNTRY" and land and land not in laender:
            laender.append(land)
        elif typ == "TOLL_VIGNETTE" and land and land not in vignetten:
            vignetten.append(land)
        elif typ == "FERRY":
            faehre = True
    wirksam = {e["key"]: e["value"] for e in daten.get("report", {}).get("effectiveSettings", [])
               if e["key"].startswith("vehicle") or e["key"] in ("travelMode", "departAt")}
    verbrauch = s.get("fuelConsumptionInLiters")
    punkte = [(p["latitude"], p["longitude"]) for leg in r.get("legs", []) for p in leg.get("points", [])]
    return Route(
        entfernung_km=(Decimal(s["lengthInMeters"]) / 1000).quantize(Decimal("0.1")),
        fahrzeit=timedelta(minutes=round(s["travelTimeInSeconds"] / 60)),   # Eingabe ohne Sekunden
        verkehr=timedelta(seconds=s.get("trafficDelayInSeconds", 0)),
        laender=laender, vignetten=vignetten, faehre=faehre,
        verbrauch_l=Decimal(str(verbrauch)).quantize(Decimal("0.1")) if verbrauch is not None else None,
        abfahrt=abfahrt_text, wirksam=wirksam, linie=vereinfachen(punkte),
    )


def etappe_routen(etappe):
    """Berechnet eine Etappe und speichert Entfernung, Fahrzeit und Details.
    Fehlende Koordinaten werden vorher aus der Adresse ermittelt."""
    for ort in (etappe.von_ort, etappe.nach_ort):
        if not ort.hat_koordinaten:
            ort_geocodieren(ort)
    abfahrt = None
    if etappe.startzeit:
        abfahrt = timezone.make_aware(datetime.combine(etappe.datum, etappe.startzeit))
    route = berechne_route(
        (etappe.von_ort.breite, etappe.von_ort.laenge), (etappe.nach_ort.breite, etappe.nach_ort.laenge),
        profil=etappe.fahrzeug, abfahrt=abfahrt, vignetten_meiden=etappe.reise.vignetten_meiden,
        familie=etappe.reise.familie)
    etappe.entfernung_km = route.entfernung_km
    etappe.fahrzeit = route.fahrzeit
    etappe.routing_stand = timezone.now()
    etappe.routing_details = route.als_details()
    etappe.save(update_fields=["entfernung_km", "fahrzeit", "routing_stand", "routing_details"])
    return route


def etappe_linie_holen(etappe):
    """Nur den Streckenverlauf für die Karte nachladen – Entfernung und Fahrzeit bleiben, wie sie sind."""
    for ort in (etappe.von_ort, etappe.nach_ort):
        if not ort.hat_koordinaten:
            ort_geocodieren(ort)
    route = berechne_route(
        (etappe.von_ort.breite, etappe.von_ort.laenge), (etappe.nach_ort.breite, etappe.nach_ort.laenge),
        profil=etappe.fahrzeug, vignetten_meiden=etappe.reise.vignetten_meiden, familie=etappe.reise.familie)
    etappe.routing_details = {**(etappe.routing_details or {}), "linie": route.linie}
    etappe.save(update_fields=["routing_details"])
    return route.linie


def profil_hinweis(reise):
    """Warnung, wenn ohne (vollständiges) Fahrzeugprofil gerechnet wird."""
    etappen = list(reise.etappen.all())
    if any(e.fahrzeug is None for e in etappen):
        return "Ohne Fahrzeugprofil wird wie mit einem Bus ohne Maße gerechnet."
    ohne_masse = sorted({e.fahrzeug.name for e in etappen if not (
        e.fahrzeug.laenge_m and e.fahrzeug.breite_m and e.fahrzeug.hoehe_m and e.fahrzeug.gesamtgewicht_kg)})
    if ohne_masse:
        return f"Im Fahrzeugprofil {', '.join(ohne_masse)} fehlen Maße oder Gewicht – sie wurden nicht berücksichtigt."
    return ""


def reise_routen(reise):
    """Alle Etappen einer Reise. Liefert (erfolgreich, [(etappe, fehlertext)])."""
    ok, fehler = 0, []
    for etappe in reise.etappen.select_related("von_ort", "nach_ort", "fahrzeugprofil", "reise__fahrzeugprofil"):
        try:
            etappe_routen(etappe)
            ok += 1
        except TomTomFehler as e:
            fehler.append((etappe, str(e)))
    return ok, fehler
