"""Lange Etappen aufteilen: Wo ist man nach x Stunden Fahrt, und wo sucht man eine Übernachtung?

Gerechnet wird mit der reinen Fahrzeit laut TomTom; die Pause verschiebt nur die Ankunft.
Erst wenn ein Platz gefunden ist, wird die Etappe dort geteilt – die neue Etappe am Folgetag
lässt sich dann genauso weiter aufteilen.
"""
import math
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from orte.models import Ort, Ortstyp

from .models import Etappe
from .routing import TomTomFehler, abschnitt, berechne_route, etappe_routen, ort_bei, ort_geocodieren, punkt_nach

SUCHFENSTER = timedelta(minutes=30)   # ± um den Punkt: dort lohnt die Suche nach einem Platz
UMKREIS_KM = 100                      # vorhandene Orte in dieser Nähe zum Teilen anbieten
CACHE_SEKUNDEN = 6 * 3600             # gleiche Eingaben nicht erneut bei TomTom abfragen


def km_zwischen(a, b):
    """Entfernung zweier Punkte (lat, lon) in km (Haversine)."""
    la1, lo1, la2, lo2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def google_suche(lat, lon, begriff="Campingplatz", zoom=11):
    """Google Maps: Suche nach `begriff` im Kartenausschnitt um den Punkt."""
    return f"https://www.google.com/maps/search/{begriff}/@{lat:.5f},{lon:.5f},{zoom}z"


def _ortstext(o):
    return ", ".join(t for t in (o.name, o.gegend if o.gegend != o.name else "", o.land) if t)


def vorschlag(etappe, start, fahrzeit, pause):
    """Haltepunkt nach `fahrzeit` reiner Fahrt ab `start` (Uhrzeit am Etappendatum).
    Liefert ein dict (auch für den Cache); TomTomFehler bei Problemen mit der Route."""
    von, nach = etappe.von_ort, etappe.nach_ort
    for ort in (von, nach):
        if not ort.hat_koordinaten:
            ort_geocodieren(ort)
    schluessel = "aufteilen:" + ":".join(str(x) for x in (
        etappe.pk, von.koordinaten, nach.koordinaten, getattr(etappe.fahrzeug, "pk", ""),
        etappe.reise.vignetten_meiden, etappe.datum, start, fahrzeit.total_seconds()))
    if (gemerkt := cache.get(schluessel)) is not None:
        return {**gemerkt, "pause": pause, "ankunft": gemerkt["abfahrt"] + fahrzeit + pause}

    abfahrt = datetime.combine(etappe.datum, start)
    route = berechne_route((von.breite, von.laenge), (nach.breite, nach.laenge), profil=etappe.fahrzeug,
                           abfahrt=timezone.make_aware(abfahrt), vignetten_meiden=etappe.reise.vignetten_meiden,
                           familie=etappe.reise.familie, verlauf=True)
    if not route.verlauf:
        raise TomTomFehler("TomTom hat keinen Streckenverlauf geliefert.")
    gesamt = route.verlauf[-1][2]
    sek = fahrzeit.total_seconds()
    if sek >= gesamt:
        raise TomTomFehler(f"Die ganze Etappe dauert nur {gesamt // 3600:.0f}:{gesamt % 3600 // 60:02.0f} h – "
                           "kürzer als die gewünschte Fahrzeit, da gibt es nichts aufzuteilen.")
    lat, lon, meter = punkt_nach(route.verlauf, sek)
    fenster = SUCHFENSTER.total_seconds()
    von_s, bis_s = max(sek - fenster, 0), min(sek + fenster, gesamt)
    familie = etappe.reise.familie
    hier = ort_bei(lat, lon, familie)
    anfang = ort_bei(*punkt_nach(route.verlauf, von_s)[:2], familie)
    ende = ort_bei(*punkt_nach(route.verlauf, bis_s)[:2], familie)

    ergebnis = {
        "abfahrt": abfahrt, "fahrzeit": fahrzeit,
        "lat": lat, "lon": lon, "km": meter / 1000, "ort": _ortstext(hier), "ort_name": hier.name,
        "suche_von": anfang.name, "suche_bis": ende.name,
        "rest_km": (route.verlauf[-1][3] - meter) / 1000, "rest_zeit": timedelta(seconds=gesamt - sek),
        "google": google_suche(lat, lon),
        "linie": route.linie, "bereich": abschnitt(route.verlauf, von_s, bis_s),
    }
    cache.set(schluessel, ergebnis, CACHE_SEKUNDEN)
    return {**ergebnis, "pause": pause, "ankunft": abfahrt + fahrzeit + pause}


def orte_in_der_naehe(etappe, lat, lon):
    """Orte der Familie im Umkreis des Haltepunkts, die nächsten zuerst."""
    kandidaten = []
    for ort in Ort.objects.filter(familie=etappe.reise.familie, breite__isnull=False, laenge__isnull=False) \
            .exclude(pk__in=[etappe.von_ort_id, etappe.nach_ort_id]):
        d = km_zwischen((lat, lon), (ort.breite, ort.laenge))
        if d <= UMKREIS_KM:
            kandidaten.append((d, ort))
    return [(round(d), ort) for d, ort in sorted(kandidaten, key=lambda x: x[0])[:8]]


def neuer_ort(familie, name, breite, laenge, website=""):
    """Zwischenübernachtung anlegen; Adresse und Land kommen von TomTom (wenn erreichbar)."""
    ort = Ort(familie=familie, name=name, typ=Ortstyp.ZWISCHEN, breite=breite, laenge=laenge, website=website)
    try:
        o = ort_bei(float(breite), float(laenge), familie)
        ort.adresse, ort.land = o.adresse, o.land_iso
    except TomTomFehler:
        pass
    ort.save()
    return ort


def teilen(etappe, ort, start_folgetag):
    """Etappe endet in `ort`; am Folgetag geht es von dort zum bisherigen Ziel weiter.
    Beide Etappen werden neu berechnet. Liefert (neue Etappe, [Fehlertexte])."""
    with transaction.atomic():
        ziel = etappe.nach_ort
        etappe.nach_ort = ort
        etappe.entfernung_km = etappe.fahrzeit = etappe.routing_stand = None
        etappe.routing_details = {}
        etappe.save()
        neu = Etappe.objects.create(
            reise=etappe.reise, datum=etappe.datum + timedelta(days=1), von_ort=ort, nach_ort=ziel,
            startzeit=start_folgetag, pause=etappe.pause, fahrzeugprofil=etappe.fahrzeugprofil)
    fehler = []
    for e in (etappe, neu):
        try:
            etappe_routen(e)
        except TomTomFehler as f:
            fehler.append(f"{e}: {f}")
    return neu, fehler
