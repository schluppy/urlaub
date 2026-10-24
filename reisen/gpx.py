"""GPX-Tracks lesen und auf Etappen übertragen – die tatsächlich gefahrene Strecke statt der geplanten.

Ein Track gehört zur Etappe an seinem Starttag. Gibt es an dem Tag mehrere (z. B. zur Fähre und
vom Hafen weiter), entscheidet, wessen Start und Ziel am nächsten an Anfang und Ende des Tracks liegen.
"""
import gzip
import io
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from .routing import vereinfachen

GROESSE_HOECHSTENS = 60 * 1024 * 1024   # entpackt; 10 h mit einem Punkt je Sekunde sind etwa 5 MB


class GpxFehler(Exception):
    """GPX unlesbar oder ohne verwertbare Punkte."""


def _m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def entpacken(daten):
    """Die App schickt gzip; eine unkomprimierte Datei geht auch."""
    if daten[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(daten)) as f:
                daten = f.read(GROESSE_HOECHSTENS + 1)
        except (OSError, EOFError):
            raise GpxFehler("Die Datei ist beschädigt.")
    if len(daten) > GROESSE_HOECHSTENS:
        raise GpxFehler("Die Datei ist zu groß.")
    return daten


def lesen(daten):
    """GPX → (Name, [Segmente]); ein Segment ist eine Liste von (Zeit, lat, lon). Punkte ohne Zeit fallen weg."""
    if b"<!DOCTYPE" in daten[:2000] or b"<!ENTITY" in daten:
        raise GpxFehler("Die Datei ist kein GPX.")
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError:
        raise GpxFehler("Die Datei ist kein GPX.")

    def kind(e, name):
        return next((k for k in e if k.tag.rsplit("}", 1)[-1] == name), None)

    def alle(e, name):
        return [k for k in e.iter() if k.tag.rsplit("}", 1)[-1] == name]

    segmente = []
    for seg in alle(wurzel, "trkseg"):
        punkte = []
        for p in seg:
            if p.tag.rsplit("}", 1)[-1] != "trkpt" or kind(p, "time") is None:
                continue
            try:
                zeit = datetime.fromisoformat(kind(p, "time").text.strip().replace("Z", "+00:00"))
                punkte.append((zeit, float(p.get("lat")), float(p.get("lon"))))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(punkte) >= 2:
            punkte.sort()
            segmente.append(punkte)
    if not segmente:
        raise GpxFehler("Die Datei enthält keine Strecke mit Zeitangaben.")
    trk = kind(wurzel, "trk")
    name = kind(trk, "name") if trk is not None else None
    return (name.text or "").strip() if name is not None else "", segmente


def kennzahlen(segmente):
    """Beginn, Ende, km, Fahrzeit (Summe der Segmente) und die vereinfachte Linie."""
    meter = sum(_m(a[1:], b[1:]) for s in segmente for a, b in zip(s, s[1:]))
    fahrzeit = sum((s[-1][0] - s[0][0] for s in segmente), timedelta())
    alle = sorted(p for s in segmente for p in s)
    return {
        "beginn": alle[0][0], "ende": alle[-1][0],
        "entfernung_km": (Decimal(meter) / 1000).quantize(Decimal("0.1")),
        "fahrzeit": timedelta(seconds=round(fahrzeit.total_seconds())),
        "linie": vereinfachen([p[1:] for p in alle]),
    }


def speichern(reise, daten):
    """Track aus GPX-Bytes anlegen. Kommt dieselbe Fahrt (gleicher Beginn) noch einmal, wird sie ersetzt.
    Liefert (Track, ersetzt)."""
    from .models import Track

    text = entpacken(daten)
    name, segmente = lesen(text)
    werte = kennzahlen(segmente)
    track, neu = Track.objects.update_or_create(
        reise=reise, beginn=werte["beginn"],
        defaults={"name": name[:120], "gpx": text.decode("utf-8", "replace"),
                  **{k: v for k, v in werte.items() if k != "beginn"}})
    return track, not neu


def _abstand(track, etappe):
    """Wie gut passt der Track zur Etappe? Meter von Start und Ziel; ohne Koordinaten neutral."""
    if not (track.linie and etappe.von_ort.hat_koordinaten and etappe.nach_ort.hat_koordinaten):
        return 0
    von = (float(etappe.von_ort.breite), float(etappe.von_ort.laenge))
    nach = (float(etappe.nach_ort.breite), float(etappe.nach_ort.laenge))
    return _m(track.linie[0], von) + _m(track.linie[-1], nach)


def etappe_fuer(track, etappen):
    """Die Etappe am Starttag des Tracks, deren Start und Ziel am besten passen; sonst None."""
    tag = timezone.localtime(track.beginn).date()
    kandidaten = [e for e in etappen if e.datum == tag]
    return min(kandidaten, key=lambda e: _abstand(track, e)) if kandidaten else None


def zuordnen(reise):
    """{Etappe: [Tracks]} und die Tracks ohne passende Etappe."""
    etappen = list(reise.etappen.select_related("von_ort", "nach_ort"))
    zuordnung, ohne = {}, []
    for track in reise.tracks.defer("gpx"):
        etappe = etappe_fuer(track, etappen)
        if etappe is None:
            ohne.append(track)
        else:
            zuordnung.setdefault(etappe, []).append(track)
    return zuordnung, ohne


def reise_aus_tracks(reise):
    """Entfernung, Fahrzeit und Linie der Etappen mit Track durch die gefahrene Strecke ersetzen.
    Die TomTom-Liter gehören zur geplanten Strecke und fallen weg; Länder, Vignetten und Fähre bleiben.
    Liefert (Anzahl Etappen, Tracks ohne Etappe)."""
    zuordnung, ohne = zuordnen(reise)
    for etappe, tracks in zuordnung.items():
        tracks.sort(key=lambda t: t.beginn)
        linie = [p for t in tracks for p in t.linie]
        details = {k: v for k, v in (etappe.routing_details or {}).items() if k != "verbrauch_l"}
        details["linie"] = linie
        details["gpx"] = {"tracks": len(tracks), "stand": timezone.now().isoformat(timespec="seconds"),
                          "beginn": timezone.localtime(tracks[0].beginn).strftime("%H:%M"),
                          "ende": timezone.localtime(tracks[-1].ende).strftime("%H:%M")}
        etappe.entfernung_km = sum((t.entfernung_km for t in tracks), Decimal(0))
        etappe.fahrzeit = timedelta(minutes=round(sum((t.fahrzeit for t in tracks), timedelta()) / timedelta(minutes=1)))
        etappe.routing_details = details
        etappe.save(update_fields=["entfernung_km", "fahrzeit", "routing_details"])
    return len(zuordnung), ohne
