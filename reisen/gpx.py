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
FENSTER_S = 10        # Geschwindigkeit über mindestens 10 s, sonst springt sie mit jedem GPS-Ausreißer
STILL_KMH = 3         # langsamer zählt nicht als Bewegung (Kriechen im Stau schon)
HOEHE_SCHWELLE_M = 5  # kleinere Schwankungen der GPS-Höhe sind Rauschen, kein Anstieg
REIHE_PUNKTE = 400    # Punkte je Track für die Diagramme


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
    """GPX → (Name, [Segmente]); ein Segment ist eine Liste von (Zeit, lat, lon, Höhe oder None).
    Punkte ohne Zeit fallen weg."""
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
                ele = kind(p, "ele")
                hoehe = float(ele.text) if ele is not None and ele.text else None
                punkte.append((zeit, float(p.get("lat")), float(p.get("lon")), hoehe))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(punkte) >= 2:
            punkte.sort(key=lambda p: p[0])
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
    alle = sorted((p for s in segmente for p in s), key=lambda p: p[0])
    return {
        "beginn": alle[0][0], "ende": alle[-1][0],
        "entfernung_km": (Decimal(meter) / 1000).quantize(Decimal("0.1")),
        "fahrzeit": timedelta(seconds=round(fahrzeit.total_seconds())),
        "linie": vereinfachen([p[1:3] for p in alle]),
        "statistik": statistik(segmente),
    }


def statistik(segmente):
    """Werte wie in einer Tracking-App: Meter, Dauer mit und ohne Stillstand, Höchstgeschwindigkeit,
    Höhen und eine ausgedünnte Reihe [Sekunden ab Beginn, km, km/h, Höhe, lat, lon] für die Diagramme.

    Gerechnet wird in Fenstern von mindestens FENSTER_S Sekunden; zwischen den Segmenten (Pausen)
    fällt die Geschwindigkeit in der Reihe auf 0."""
    beginn = min(s[0][0] for s in segmente)
    dauer = (max(s[-1][0] for s in segmente) - beginn).total_seconds()
    sekunde = lambda p: round((p[0] - beginn).total_seconds())

    # Feine Fenster: (Ende, Sekunden, Meter, Luftlinie in Metern, mittlere Höhe oder None). Bewegung und
    # Höchstgeschwindigkeit nach der Luftlinie: Das Zittern der GPS-Position im Stand summiert sich sonst zu Schritttempo.
    fenster = []
    for seg in segmente:
        fenster.append((seg[0], 0, 0.0, 0.0, seg[0][3]))
        start, strecke, hoehen = seg[0], 0.0, []
        for a, b in zip(seg, seg[1:]):
            strecke += _m(a[1:3], b[1:3])
            if b[3] is not None:
                hoehen.append(b[3])
            s = (b[0] - start[0]).total_seconds()
            if s >= FENSTER_S or b is seg[-1]:
                fenster.append((b, s, strecke, _m(start[1:3], b[1:3]), sum(hoehen) / len(hoehen) if hoehen else None))
                start, strecke, hoehen = b, 0.0, []
        fenster.append((seg[-1], 0, 0.0, 0.0, None))   # Stillstand bis zum nächsten Segment
    meter = sum(f[2] for f in fenster)

    kmh = lambda m, s: m / s * 3.6 if s else 0.0
    bewegung = sum(f[1] for f in fenster if f[1] and kmh(f[3], f[1]) >= STILL_KMH)
    hoechst = max((kmh(f[3], f[1]) for f in fenster if f[1] >= FENSTER_S), default=0.0)

    hoehen = [f[4] for f in fenster if f[4] is not None]
    hoehe = None
    if hoehen:
        anstieg = abstieg = 0.0
        bezug = hoehen[0]
        for h in hoehen[1:]:
            if h - bezug >= HOEHE_SCHWELLE_M:
                anstieg += h - bezug
                bezug = h
            elif bezug - h >= HOEHE_SCHWELLE_M:
                abstieg += bezug - h
                bezug = h
        hoehe = {"min": round(min(hoehen)), "max": round(max(hoehen)), "anstieg": round(anstieg), "abstieg": round(abstieg)}

    # Für die Diagramme feine Fenster zu Stufen von etwa dauer/REIHE_PUNKTE zusammenfassen
    stufe = max(FENSTER_S, dauer / REIHE_PUNKTE)
    reihe, gefahren, s_sum, m_sum, h_sum = [], 0.0, 0, 0.0, []

    def punkt(p, geschw, h):
        return [sekunde(p), round(gefahren / 1000, 2), round(geschw, 1),
                None if h is None else round(h), round(p[1], 5), round(p[2], 5)]

    for p, s, m, _, h in fenster:
        gefahren += m
        if not s:   # Segmentgrenze
            if s_sum:
                reihe.append(punkt(p, kmh(m_sum, s_sum), sum(h_sum) / len(h_sum) if h_sum else None))
                s_sum, m_sum, h_sum = 0, 0.0, []
            reihe.append(punkt(p, 0.0, h if h is not None else (reihe[-1][3] if reihe else None)))
            continue
        s_sum, m_sum = s_sum + s, m_sum + m
        if h is not None:
            h_sum.append(h)
        if s_sum >= stufe:
            reihe.append(punkt(p, kmh(m_sum, s_sum), sum(h_sum) / len(h_sum) if h_sum else None))
            s_sum, m_sum, h_sum = 0, 0.0, []

    return {"meter": round(meter), "dauer_s": round(dauer), "bewegung_s": round(bewegung),
            "hoechst_kmh": round(hoechst, 1), "hoehe": hoehe, "reihe": reihe}


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


def track_statistik(track):
    """Statistik des Tracks; ältere Tracks bekommen sie beim ersten Bedarf aus ihrem GPX nachgerechnet."""
    if not track.statistik:
        track.statistik = statistik(lesen(track.gpx.encode())[1])
        track.save(update_fields=["statistik"])
    return track.statistik


def etappen_statistik(tracks):
    """Statistik der Tracks einer Etappe zusammengefasst; Reihe mit Sekunden ab dem ersten Beginn und km fortlaufend."""
    tracks = sorted(tracks, key=lambda t: t.beginn)
    werte = [track_statistik(t) for t in tracks]
    meter = sum(w["meter"] for w in werte)
    dauer = sum(w["dauer_s"] for w in werte)
    bewegung = sum(w["bewegung_s"] for w in werte)
    reihe, km = [], 0.0
    for t, w in zip(tracks, werte):
        versatz = round((t.beginn - tracks[0].beginn).total_seconds())
        reihe += [[r[0] + versatz, round(r[1] + km, 2), *r[2:]] for r in w["reihe"]]
        km += w["meter"] / 1000
    hoehen = [w["hoehe"] for w in werte if w["hoehe"]]
    return {
        "km": meter / 1000, "dauer": timedelta(seconds=dauer), "bewegung": timedelta(seconds=bewegung),
        "hoechst_kmh": max(w["hoechst_kmh"] for w in werte),
        "schnitt_kmh": meter / dauer * 3.6 if dauer else None,
        "schnitt_bewegt_kmh": meter / bewegung * 3.6 if bewegung else None,
        "hoehe": {"min": min(h["min"] for h in hoehen), "max": max(h["max"] for h in hoehen),
                  "anstieg": sum(h["anstieg"] for h in hoehen), "abstieg": sum(h["abstieg"] for h in hoehen),
                  "unterschied": max(h["max"] for h in hoehen) - min(h["min"] for h in hoehen)} if hoehen else None,
        "uhrzeit": timezone.localtime(tracks[0].beginn).strftime("%H:%M:%S"),
        "reihe": reihe,
    }


def fahrten(reise):
    """Statistik der Etappen, die „Gefahrene Strecke aus GPX“ ersetzt hat – für die Anzeige neben der Karte."""
    zuordnung, _ = zuordnen(reise)
    return [{"etappe": e, **(w := etappen_statistik(tracks)), "diagramm_id": f"fahrt-{e.pk}",
             "diagramm": {"uhrzeit": w["uhrzeit"], "reihe": w["reihe"], "hoehe": bool(w["hoehe"])}}
            for e, tracks in sorted(zuordnung.items(), key=lambda x: (x[0].datum, x[0].pk))
            if (e.routing_details or {}).get("gpx")]


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
