"""Aufbau des Jahreskalenders: 12 Monatsspalten × 31 Tageszeilen.

Liefert reine Daten (Farben, Texte je Zelle); HTML-Seite und PDF nutzen
dieselbe Vorlage. Regeln siehe Projektbriefing, Abschnitt „Jahreskalender“.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings

from konten.models import Bundesland

from .models import Schulferien
from .tage import feiertage, ist_feiertag, wochentag_kurz, zeitraum_text

MONATSFARBEN = ["#2F5D8C", "#5B4E9C", "#8A4F9E", "#2E7D6E", "#4E8A3A", "#6F7F22",
                "#A86F12", "#B5562A", "#9C3F5A", "#7A4A2E", "#4F6470", "#1F6F8B"]
MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]

FEIERTAG = "#C62828"
FERIEN = "#173F73"
URLAUB = "#F7B955"
URLAUB_WOCHENENDE = "#E39226"

TOENUNG_WOCHENTAG = 0.10
TOENUNG_WOCHENENDE = 0.34


def toenung(farbe, anteil):
    """Monatsfarbe mit Weiß gemischt; anteil = Deckkraft der Farbe (0..1)."""
    r, g, b = (int(farbe[i:i + 2], 16) for i in (1, 3, 5))
    misch = (round(255 + (k - 255) * anteil) for k in (r, g, b))
    return "#{:02X}{:02X}{:02X}".format(*misch)


@dataclass
class Zelle:
    tag: date | None
    hintergrund: str = "#FFFFFF"
    schrift: str = "#1C2430"
    text: str = ""            # Feiertagsname oder Reisetitel (rechts, gekürzt)
    ferien: bool = False
    rand: str = ""            # linker Rand: Ferienbalken, sonst Zellenfarbe
    klassen: list = field(default_factory=list)

    @property
    def zahl(self):
        return self.tag.day if self.tag else ""

    @property
    def wochentag(self):
        return wochentag_kurz(self.tag) if self.tag else ""

    @property
    def stil(self):
        rand = FERIEN if self.ferien else (self.rand or self.hintergrund)
        return f"background:{self.hintergrund};color:{self.schrift};border-left-color:{rand}"


@dataclass
class Monat:
    nummer: int
    name: str
    farbe: str
    zellen: list


def _ferientage(ferien):
    tage = {}
    for f in ferien:
        tag = f.von
        while tag <= f.bis:
            tage[tag] = f.bezeichnung
            tag += timedelta(days=1)
    return tage


def _belegung(reisen, bundesland):
    """{tag: ("urlaub" | "feierabend", reise)}.

    Urlaubstage (inkl. Vor- und Nachbereitung) sind Urlaub. Reisetage außerhalb des Urlaubs
    sind an Arbeitstagen „nach Feierabend“ (diagonal geteilt), an freien Tagen ebenfalls Urlaub."""
    belegung = {}
    for r in reisen:
        tag = r.kalender_beginn
        while tag <= r.kalender_ende:
            arbeitstag = tag.weekday() < 5 and not ist_feiertag(tag, bundesland)
            belegung[tag] = ("urlaub" if r.ist_urlaub(tag) or not arbeitstag else "feierabend", r)
            tag += timedelta(days=1)
    return belegung


def zelle_fuer(tag, farbe, feiertag, ferien, belegung=None):
    wochenende = tag.weekday() >= 5
    z = Zelle(tag=tag, ferien=ferien,
              hintergrund=toenung(farbe, TOENUNG_WOCHENENDE if wochenende else TOENUNG_WOCHENTAG))
    if wochenende:
        z.klassen.append("we")

    if belegung:
        art, reise = belegung
        if art == "urlaub":
            z.hintergrund = URLAUB_WOCHENENDE if wochenende else URLAUB
            z.klassen.append("urlaub")
        else:
            # diagonal geteilt: oben links Alltag, unten rechts Urlaub
            z.rand = z.hintergrund
            z.hintergrund = f"linear-gradient(to bottom right, {z.hintergrund} 50%, {URLAUB} 50%)"
            z.klassen.append("feierabend")
        if tag == reise.kalender_beginn:
            z.text = reise.titel

    if feiertag:
        # Feiertag bleibt rot, auch im Urlaub
        z.hintergrund, z.schrift, z.rand = FEIERTAG, "#FFFFFF", ""
        z.klassen.append("feiertag")
        z.text = feiertag
    return z


def jahreskalender(jahr, reisen, bundesland=None):
    """Monate mit je 31 Zellen; Tage, die es nicht gibt, bleiben leer."""
    bundesland = bundesland or settings.BUNDESLAND
    ft = feiertage(jahr, bundesland)
    ferien = list(Schulferien.im_jahr(jahr, bundesland))
    ferientage = _ferientage(ferien)
    belegung = _belegung(reisen, bundesland)

    monate = []
    for m in range(1, 13):
        farbe = MONATSFARBEN[m - 1]
        zellen = []
        for d in range(1, 32):
            try:
                tag = date(jahr, m, d)
            except ValueError:
                zellen.append(Zelle(tag=None, klassen=["leer"]))
                continue
            zellen.append(zelle_fuer(tag, farbe, ft.get(tag), tag in ferientage, belegung.get(tag)))
        monate.append(Monat(m, MONATSNAMEN[m - 1], farbe, zellen))

    zeilen = [[monat.zellen[d] for monat in monate] for d in range(31)]
    return {
        "jahr": jahr,
        "bundesland": bundesland,
        "bundesland_name": Bundesland(bundesland).label,
        "monate": monate,
        "zeilen": zeilen,
        "ferien": [{"bezeichnung": f.bezeichnung, "zeitraum": zeitraum_text(f.von, f.bis)} for f in ferien],
        "urlaube": [{"titel": r.titel, "zeitraum": zeitraum_text(r.urlaub_beginn, r.urlaub_ende),
                     "urlaubstage": r.urlaubstage} for r in sorted(reisen, key=lambda r: r.kalender_beginn)],
        "urlaubstage_summe": sum(r.urlaubstage for r in reisen),
        "farben": {"feiertag": FEIERTAG, "ferien": FERIEN, "urlaub": URLAUB,
                   "urlaub_we": URLAUB_WOCHENENDE,
                   "wochentag": toenung(MONATSFARBEN[0], TOENUNG_WOCHENTAG),
                   "wochenende": toenung(MONATSFARBEN[0], TOENUNG_WOCHENENDE)},
    }
