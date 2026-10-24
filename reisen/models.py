"""Reisen mit Etappen, Buchungen, Kostenpositionen und Links.

Alles, was in der Tabelle von Hand gerechnet wurde (Nächte, Kraftstoffkosten,
Summen, Urlaubstage), wird hier berechnet und nicht gespeichert.
"""
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models

from fahrzeuge.models import Fahrzeugprofil
from kalender.tage import ist_feiertag, urlaubstage
from orte.models import Ort, Ortstyp

CENT = Decimal("0.01")


def _cent(betrag):
    return Decimal(betrag).quantize(CENT, rounding=ROUND_HALF_UP)


class Reise(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="reisen")
    titel = models.CharField("Titel", max_length=80, help_text="erscheint so im Kalender")
    # Urlaub: die freien Tage inkl. Vor- und Nachbereitung – bestimmt Kalender und Urlaubstage.
    urlaub_von = models.DateField("Urlaub von", null=True, blank=True,
                                  help_text="erster Urlaubstag (inkl. Vorbereitung); leer = wie Reisezeit")
    urlaub_bis = models.DateField("Urlaub bis", null=True, blank=True,
                                  help_text="letzter Urlaubstag (inkl. Nachbereitung)")
    # Reisezeit: mit dem Gespann unterwegs – bestimmt Etappen, Buchungen, Nächte.
    von = models.DateField("Reisezeit von", help_text="Abfahrt. Liegt sie an einem Arbeitstag vor dem Urlaub, "
                                                      "gilt sie als „Abfahrt nach Feierabend“.")
    bis = models.DateField("Reisezeit bis", help_text="Rückkehr")
    fahrzeugprofil = models.ForeignKey(Fahrzeugprofil, verbose_name="Fahrzeugprofil", on_delete=models.PROTECT,
                                       null=True, blank=True, related_name="reisen")
    verbrauch_l_100km = models.DecimalField(
        "Ø Verbrauch (L/100 km)", max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="leer = Wert aus dem Fahrzeugprofil")
    dieselpreis = models.DecimalField("Kraftstoffpreis (€/L)", max_digits=5, decimal_places=3, default=Decimal("1.80"))
    vignetten_meiden = models.CharField(
        "Vignettenpflichtige Straßen meiden in", max_length=60, blank=True,
        help_text="ISO-3-Kürzel mit Komma, z. B. CHE,AUT. Leer = Vignettenstraßen erlaubt.")
    im_kalender = models.BooleanField("im Kalender", default=True,
                                      help_text="aus für Alternativen, die nur geplant werden")
    notizen = models.TextField("Notizen", blank=True)
    # Kalender-Abo: Version des Termins, damit Google & Co. Änderungen sicher übernehmen
    ical_pruefsumme = models.CharField(max_length=64, blank=True, editable=False)
    ical_version = models.PositiveIntegerField(default=0, editable=False)
    ical_geaendert = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Reise"
        verbose_name_plural = "Reisen"
        ordering = ["von"]

    ICAL_FELDER = {"ical_pruefsumme", "ical_version", "ical_geaendert"}

    def save(self, *args, **kwargs):
        # Die Termin-Version pflegt nur der Kalender-Feed; ein normales Speichern (Verwaltung)
        # darf sie nicht mit einem veralteten Stand überschreiben.
        if self.pk and not self._state.adding and kwargs.get("update_fields") is None:
            kwargs["update_fields"] = [f.name for f in self._meta.concrete_fields
                                       if not f.primary_key and f.name not in self.ICAL_FELDER]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titel} ({self.von:%d.%m.%Y})"

    def clean(self):
        fehler = {}
        if self.von and self.bis and self.bis < self.von:
            fehler["bis"] = "Die Rückkehr liegt vor der Abfahrt."
        if bool(self.urlaub_von) != bool(self.urlaub_bis):
            fehler["urlaub_bis" if self.urlaub_von else "urlaub_von"] = "Bitte Urlaub von und bis angeben (oder beide leer)."
        elif self.urlaub_von and self.urlaub_bis < self.urlaub_von:
            fehler["urlaub_bis"] = "Das Urlaubsende liegt vor dem Urlaubsbeginn."
        if fehler:
            raise ValidationError(fehler)

    # --- Zeitraum ------------------------------------------------------------

    @property
    def urlaub_beginn(self):
        return self.urlaub_von or self.von

    @property
    def urlaub_ende(self):
        return self.urlaub_bis or self.bis

    @property
    def hat_eigenen_urlaub(self):
        return (self.urlaub_beginn, self.urlaub_ende) != (self.von, self.bis)

    @property
    def kalender_beginn(self):
        """Erster Tag im Kalender: Urlaubsbeginn oder frühere Abfahrt."""
        return min(self.von, self.urlaub_beginn)

    @property
    def kalender_ende(self):
        return max(self.bis, self.urlaub_ende)

    def ist_urlaub(self, tag):
        return self.urlaub_beginn <= tag <= self.urlaub_ende

    @property
    def abfahrt_feierabend(self):
        """Abfahrt an einem Arbeitstag vor dem Urlaub – zählt nicht als Urlaubstag."""
        if self.von < self.urlaub_beginn and self.von.weekday() < 5 and not ist_feiertag(self.von, self.bundesland):
            return self.von
        return None

    @property
    def urlaubstage(self):
        return urlaubstage(self.urlaub_beginn, self.urlaub_ende, self.bundesland)

    @property
    def bundesland(self):
        return self.familie.bundesland

    @property
    def jahr(self):
        return self.urlaub_beginn.year

    # --- Fahrt ---------------------------------------------------------------

    @property
    def verbrauch(self):
        if self.verbrauch_l_100km is not None:
            return self.verbrauch_l_100km
        return self.fahrzeugprofil.verbrauch_l_100km if self.fahrzeugprofil else None

    def _etappen(self):
        # nutzt vorab geladene Etappen (prefetch_related), falls vorhanden
        return list(self.etappen.all())

    @property
    def entfernung_km(self):
        return sum((e.entfernung_km or 0 for e in self._etappen()), Decimal(0))

    @property
    def fahrzeit(self):
        return sum((e.fahrzeit or timedelta() for e in self._etappen()), timedelta())

    @property
    def dieselliter(self):
        return sum((e.dieselliter or 0 for e in self._etappen()), Decimal(0))

    @property
    def diesel_quelle(self):
        """Wie die Liter zustande kommen – für die Zeile unter den Kosten."""
        etappen = [e for e in self._etappen() if e.dieselliter is not None]
        tomtom = [e for e in etappen if e.tomtom_liter is not None]
        if not tomtom:
            return f"{self.verbrauch:.1f} L/100 km".replace(".", ",") if self.verbrauch is not None else ""
        km = sum((e.entfernung_km or 0 for e in etappen), Decimal(0))
        schnitt = (f"Ø {(self.dieselliter / km * 100).quantize(Decimal('0.1'), ROUND_HALF_UP)} L/100 km"
                   .replace(".", ",") if km else "")
        if len(tomtom) == len(etappen):
            return f"{schnitt}, Verbrauchskurve TomTom"
        return f"{schnitt}, {len(tomtom)} von {len(etappen)} Etappen mit Verbrauchskurve TomTom"

    @property
    def dieselkosten(self):
        return _cent(self.dieselliter * self.dieselpreis)

    # --- Kosten --------------------------------------------------------------

    def _buchungen(self):
        return [b for b in self.buchungen.all() if b.status != Buchungsstatus.STORNIERT]

    @property
    def naechte(self):
        return sum(b.naechte for b in self._buchungen())

    @property
    def buchungen_eur(self):
        return sum((b.summe_eur for b in self._buchungen()), Decimal(0))

    @property
    def kostenpositionen_eur(self):
        return sum((k.betrag for k in self.kosten.all()), Decimal(0))

    @property
    def gesamtkosten(self):
        return self.dieselkosten + self.buchungen_eur + self.kostenpositionen_eur

    @property
    def offen_eur(self):
        return sum((b.rest_eur for b in self._buchungen() if b.status != Buchungsstatus.BEZAHLT), Decimal(0))

    def aufenthalte(self):
        """Übernachtungen laut Etappen: [(Ort, Ankunft, Abfahrt)] – Ankunft mit einer Etappe,
        Abfahrt mit der nächsten. Zuhause und Zwischenhalte ohne Nacht zählen nicht."""
        etappen = self._etappen()
        ergebnis = []
        for etappe, naechste in zip(etappen, etappen[1:] + [None]):
            ort = etappe.nach_ort
            if ort.typ == Ortstyp.ZUHAUSE:
                continue
            abfahrt = naechste.datum if naechste else self.bis
            if abfahrt > etappe.datum:
                ergebnis.append((ort, etappe.datum, abfahrt))
        return ergebnis

    def gesamtrouten(self):
        """Abschnitte der Reise als Links für ADAC Maps und Google Maps (siehe Gesamtroute unten)."""
        return [Gesamtroute(a, self.fahrzeugprofil) for a in abschnitte(self._etappen()) if len(a) >= 2]

    @property
    def hauptort(self):
        """Haupturlaubsort: Platz mit den meisten Nächten – ohne Zwischenübernachtungen, Fähren und Zuhause.
        Zuerst aus den Buchungen, sonst aus den Aufenthalten laut Etappen; bei Gleichstand der erste."""
        nebensaechlich = {Ortstyp.ZUHAUSE, Ortstyp.ZWISCHEN, Ortstyp.FAEHRE}
        naechte = {}
        for b in sorted(self._buchungen(), key=lambda b: b.von):
            if b.ort.typ not in nebensaechlich:
                naechte[b.ort] = naechte.get(b.ort, 0) + b.naechte
        if not naechte:
            for ort, an, ab in self.aufenthalte():
                if ort.typ not in nebensaechlich:
                    naechte[ort] = naechte.get(ort, 0) + (ab - an).days
        return max(naechte, key=naechte.get) if naechte else None   # max nimmt bei Gleichstand den ersten

    @property
    def ziele_mit_status(self):
        """[(Ortsname, Status, Statustext)] in Buchungsreihenfolge, ohne stornierte;
        derselbe Platz mit gleichem Status nur einmal (z. B. Zwischenstopp auf Hin- und Rückweg)."""
        ergebnis = []
        for b in sorted(self._buchungen(), key=lambda b: b.von):
            eintrag = (b.ort.name, b.status, b.get_status_display())
            if eintrag not in ergebnis:
                ergebnis.append(eintrag)
        return ergebnis

    def kostenaufstellung(self):
        """[(Bezeichnung, Betrag €)] – Kraftstoff, Übernachtungen, dann je Kostenart."""
        posten = [("Kraftstoff", self.dieselkosten), ("Übernachtungen", self.buchungen_eur)]
        for art, label in Kostenart.choices:
            betrag = sum((k.betrag for k in self.kosten.all() if k.art == art), Decimal(0))
            if betrag:
                posten.append((label, betrag))
        return [(name, betrag) for name, betrag in posten if betrag]

    def hinweise(self, heute=None):
        """Was in der Tabelle früher unbemerkt blieb: fehlende Routen, Lücken, Fälligkeiten."""
        heute = heute or date.today()
        hinweise = []
        etappen = self._etappen()
        ohne = [e for e in etappen if not e.entfernung_km]
        if ohne:
            hinweise.append(("warnung", f"{len(ohne)} Etappe{'n' if len(ohne) > 1 else ''} ohne Entfernung – "
                                        "„Route aktualisieren“ ausführen."))
        for e in etappen:
            if not (self.von <= e.datum <= self.bis):
                hinweise.append(("warnung", f"Etappe {e} liegt außerhalb des Reisezeitraums."))
        if etappen and not self.verbrauch:
            hinweise.append(("warnung", "Kein Verbrauch hinterlegt – Kraftstoffkosten fehlen."))

        buchungen = self._buchungen()
        if buchungen:
            belegt = set()
            for b in buchungen:
                belegt.update(b.von + timedelta(days=i) for i in range(b.naechte))
            # alle Nächte der Reisezeit: von der Abfahrt bis zur Nacht vor der Rückkehr
            luecken = [self.von + timedelta(days=i) for i in range((self.bis - self.von).days)
                       if self.von + timedelta(days=i) not in belegt]
            if luecken:
                tage = ", ".join(f"{t:%d.%m.}" for t in luecken[:8]) + (" …" if len(luecken) > 8 else "")
                hinweise.append(("info", f"Nächte ohne Buchung: {tage} (z. B. Fähre oder noch offen)"))
        for b in buchungen:
            if b.status != Buchungsstatus.BEZAHLT and b.rest > 0 and b.rest_faellig_am:
                if b.rest_faellig_am < heute:
                    hinweise.append(("fehler", f"Restzahlung {b.ort} war am {b.rest_faellig_am:%d.%m.%Y} fällig."))
                elif b.rest_faellig_am <= heute + timedelta(days=30):
                    hinweise.append(("warnung", f"Restzahlung {b.ort} fällig am {b.rest_faellig_am:%d.%m.%Y}."))
        return hinweise


LANGE_ETAPPE = timedelta(hours=8)   # ab hier bietet die Etappenliste „aufteilen“ an


class Etappe(models.Model):
    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="etappen")
    datum = models.DateField("Datum")
    von_ort = models.ForeignKey(Ort, verbose_name="Von", on_delete=models.PROTECT, related_name="+")
    nach_ort = models.ForeignKey(Ort, verbose_name="Nach", on_delete=models.PROTECT, related_name="+")
    startzeit = models.TimeField("Start", null=True, blank=True)
    pause = models.DurationField("Pause", default=timedelta(), help_text="hh:mm:ss")
    fahrzeugprofil = models.ForeignKey(
        Fahrzeugprofil, verbose_name="Fahrzeug abweichend", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", help_text="leer = Fahrzeug der Reise")
    entfernung_km = models.DecimalField("Entfernung (km)", max_digits=7, decimal_places=1, null=True, blank=True)
    fahrzeit = models.DurationField("Fahrzeit", null=True, blank=True, help_text="hh:mm:ss")
    routing_stand = models.DateTimeField("Routing-Stand", null=True, blank=True,
                                         help_text="Zeitpunkt der letzten Berechnung mit TomTom")
    routing_details = models.JSONField("Routing-Details", default=dict, blank=True, editable=False)

    class Meta:
        verbose_name = "Etappe"
        verbose_name_plural = "Etappen"
        ordering = ["reise", "datum", "startzeit", "id"]   # Reihenfolge ergibt sich aus Datum und Start

    def __str__(self):
        return f"{self.datum:%d.%m.} {self.von_ort} → {self.nach_ort}"

    def clean(self):
        if self.von_ort_id and self.von_ort_id == self.nach_ort_id:
            raise ValidationError("Start und Ziel sind derselbe Ort.")

    @property
    def fahrzeug(self):
        return self.fahrzeugprofil or self.reise.fahrzeugprofil

    @property
    def verbrauch(self):
        if self.fahrzeugprofil:
            return self.fahrzeugprofil.verbrauch_l_100km
        return self.reise.verbrauch

    @property
    def tomtom_liter(self):
        """Liter laut TomTom – nur, solange das Fahrzeug der Etappe eine Verbrauchskurve hat."""
        liter = (self.routing_details or {}).get("verbrauch_l")
        if liter is None or not (self.fahrzeug and self.fahrzeug.verbrauchskurve):
            return None
        return Decimal(liter)

    @property
    def dieselliter(self):
        """TomTom-Liter, sonst Entfernung × Ø-Verbrauch; None, wenn beides fehlt."""
        if self.tomtom_liter is not None:
            return self.tomtom_liter
        if self.entfernung_km and self.verbrauch is not None:
            return self.entfernung_km * self.verbrauch / 100
        return None

    @property
    def ist_lang(self):
        """Lange Etappe: die Etappenliste bietet „aufteilen“ an."""
        return bool(self.fahrzeit and self.fahrzeit > LANGE_ETAPPE)

    @property
    def karten_link(self):
        """Google-Maps-Route aus den Koordinaten (ersetzt die von Hand gepflegten Links)."""
        if not (self.von_ort.hat_koordinaten and self.nach_ort.hat_koordinaten):
            return ""
        return ("https://www.google.com/maps/dir/?api=1"
                f"&origin={self.von_ort.koordinaten}&destination={self.nach_ort.koordinaten}&travelmode=driving")

    @property
    def adac_link(self):
        """Route in ADAC Maps (mit Maut, Gespann bzw. Wohnmobil). ADAC hat keine API – nur dieser Link.
        Punkte als lat_lon_Typ_0; 2 = Start, 6 = Ziel wie in den Links von maps.adac.de."""
        if not (self.von_ort.hat_koordinaten and self.nach_ort.hat_koordinaten):
            return ""
        art = self.fahrzeug.art if self.fahrzeug else "trailer"
        start = f"{self.von_ort.breite:.5f}_{self.von_ort.laenge:.5f}_2_0"
        ziel = f"{self.nach_ort.breite:.5f}_{self.nach_ort.laenge:.5f}_6_0"
        return f"https://maps.adac.de/route?places={start},{ziel}&vehicle-type={art}"

    @property
    def ankunft(self):
        """Start + Fahrzeit + Pause; None, solange etwas fehlt."""
        if self.startzeit is None or self.fahrzeit is None:
            return None
        return datetime.combine(self.datum, self.startzeit) + self.fahrzeit + (self.pause or timedelta())


# --- Gesamtroute: mehrere Etappen in einem Link -------------------------------

GOOGLE_MAX_ZWISCHENZIELE = 9    # mehr nimmt Google Maps in der Adresse nicht an


def abschnitte(etappen):
    """Etappen in zusammenhängende Abschnitte teilen. Ein neuer Abschnitt beginnt, wo eine Etappe nicht
    am Ziel der vorigen startet – so ist eine Fähre eingetragen (Etappe endet am Abfahrtshafen, die
    nächste beginnt am Ankunftshafen). Eine Etappe von Fährterminal zu Fährterminal ist die Überfahrt
    selbst und gehört zu keinem Abschnitt."""
    teile, aktuell = [], []
    for e in etappen:
        ueberfahrt = e.von_ort.typ == Ortstyp.FAEHRE and e.nach_ort.typ == Ortstyp.FAEHRE
        if aktuell and (ueberfahrt or e.von_ort_id != aktuell[-1].nach_ort_id):
            teile.append(aktuell)
            aktuell = []
        if not ueberfahrt:
            aktuell.append(e)
    if aktuell:
        teile.append(aktuell)
    return teile


class Gesamtroute:
    def __init__(self, etappen, fahrzeugprofil=None):
        self.etappen = etappen
        orte = [etappen[0].von_ort]
        for e in etappen:
            if e.nach_ort_id != orte[-1].pk:
                orte.append(e.nach_ort)
        self.orte = orte
        self.rundreise = orte[0].pk == orte[-1].pk
        self.name = f"Rundreise ab {orte[0]}" if self.rundreise else f"{orte[0]} → {orte[-1]}"
        self.zeitraum = f"{etappen[0].datum:%d.%m.} – {etappen[-1].datum:%d.%m.}"
        self.ohne_koordinaten = [o for o in orte if not o.hat_koordinaten]
        fahrzeug = etappen[0].fahrzeug or fahrzeugprofil
        self.art = fahrzeug.art if fahrzeug else "trailer"

    @property
    def adac_link(self):
        """ADAC Maps: Punkte als lat_lon_6_0 hintereinander (so auch in längeren Routen von maps.adac.de)."""
        if self.ohne_koordinaten:
            return ""
        punkte = ",".join(f"{o.breite:.5f}_{o.laenge:.5f}_6_0" for o in self.orte)
        return f"https://maps.adac.de/route?places={punkte}&vehicle-type={self.art}"

    @property
    def zu_viele_fuer_google(self):
        return len(self.orte) - 2 > GOOGLE_MAX_ZWISCHENZIELE

    @property
    def google_link(self):
        if self.ohne_koordinaten or self.zu_viele_fuer_google:
            return ""
        zwischen = "%7C".join(o.koordinaten for o in self.orte[1:-1])
        return ("https://www.google.com/maps/dir/?api=1"
                f"&origin={self.orte[0].koordinaten}&destination={self.orte[-1].koordinaten}"
                + (f"&waypoints={zwischen}" if zwischen else "") + "&travelmode=driving")


class Buchungsstatus(models.TextChoices):
    GEPLANT = "geplant", "geplant"
    ANGEFRAGT = "angefragt", "angefragt"
    GEBUCHT = "gebucht", "gebucht"
    ANGEZAHLT = "angezahlt", "angezahlt"
    BEZAHLT = "bezahlt", "bezahlt"
    STORNIERT = "storniert", "storniert"


class Buchung(models.Model):
    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="buchungen")
    ort = models.ForeignKey(Ort, verbose_name="Ort", on_delete=models.PROTECT, related_name="buchungen")
    von = models.DateField("Anreise")
    bis = models.DateField("Abreise")
    # Entweder Preis pro Nacht oder Gesamtpreis für den Aufenthalt; der Gesamtpreis gilt, wenn gesetzt.
    preis_pro_nacht = models.DecimalField("Preis/Nacht", max_digits=8, decimal_places=2, null=True, blank=True)
    gesamtpreis = models.DecimalField("Gesamtpreis", max_digits=9, decimal_places=2, null=True, blank=True,
                                      help_text="für den ganzen Aufenthalt – statt Preis/Nacht")
    waehrung = models.CharField("Währung", max_length=3, default="EUR")
    wechselkurs = models.DecimalField("Kurs", max_digits=10, decimal_places=4, default=Decimal(1),
                                      help_text="1 € = … Fremdwährung (z. B. 0,8653 GBP)")
    anzahlung = models.DecimalField("Anzahlung", max_digits=8, decimal_places=2, default=Decimal(0),
                                    help_text="in Buchungswährung")
    rest_faellig_am = models.DateField("Rest fällig am", null=True, blank=True)
    status = models.CharField("Status", max_length=12, choices=Buchungsstatus.choices,
                              default=Buchungsstatus.GEPLANT)
    buchungsnummer = models.CharField("Buchungsnr.", max_length=60, blank=True)
    stellplatz = models.CharField("Stellplatz", max_length=40, blank=True, help_text="z. B. Platz 47 oder Parzelle B12")
    notiz = models.CharField("Notiz", max_length=200, blank=True)

    class Meta:
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        ordering = ["reise", "von"]

    def __str__(self):
        return f"{self.ort} {self.von:%d.%m.}–{self.bis:%d.%m.%Y}"

    def clean(self):
        if self.von and self.bis and self.bis <= self.von:
            raise ValidationError({"bis": "Die Abreise muss nach der Anreise liegen."})
        if self.wechselkurs is not None and self.wechselkurs <= 0:
            raise ValidationError({"wechselkurs": "Kurs muss größer als 0 sein."})
        if (self.preis_pro_nacht is not None and self.gesamtpreis is not None and self.von and self.bis
                and _cent(self.preis_pro_nacht * self.naechte) != _cent(self.gesamtpreis)):
            raise ValidationError({"gesamtpreis": "Bitte entweder Preis/Nacht oder Gesamtpreis angeben – "
                                                  f"{self.naechte} × {self.preis_pro_nacht} ergibt nicht "
                                                  f"{self.gesamtpreis}."})

    @property
    def naechte(self):
        return (self.bis - self.von).days

    @property
    def ist_pauschal(self):
        return self.gesamtpreis is not None

    @property
    def summe(self):
        """In Buchungswährung: Gesamtpreis, sonst Nächte × Preis/Nacht (ohne Preis: 0)."""
        if self.gesamtpreis is not None:
            return self.gesamtpreis
        return self.naechte * (self.preis_pro_nacht or Decimal(0))

    @property
    def preis_je_nacht(self):
        """Zur Anzeige, bei Pauschalen umgerechnet."""
        if self.gesamtpreis is not None:
            return _cent(self.gesamtpreis / self.naechte) if self.naechte else None
        return self.preis_pro_nacht

    @property
    def rest(self):
        return self.summe - self.anzahlung

    def in_eur(self, betrag):
        return _cent(betrag / self.wechselkurs)

    @property
    def summe_eur(self):
        return self.in_eur(self.summe)

    @property
    def rest_eur(self):
        return self.in_eur(self.rest)

    @property
    def ist_fremdwaehrung(self):
        return self.waehrung.upper() != "EUR"


class Kostenart(models.TextChoices):
    FAEHRE = "faehre", "Fähre"
    VIGNETTE = "vignette", "Vignette"
    MAUT = "maut", "Maut"
    SONSTIGES = "sonstiges", "Sonstiges"


class Kostenposition(models.Model):
    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="kosten")
    art = models.CharField("Art", max_length=12, choices=Kostenart.choices, default=Kostenart.SONSTIGES)
    betrag = models.DecimalField("Betrag (€)", max_digits=8, decimal_places=2)
    notiz = models.CharField("Notiz", max_length=200, blank=True)

    class Meta:
        verbose_name = "Kostenposition"
        verbose_name_plural = "Kostenpositionen"
        ordering = ["reise", "art"]

    def __str__(self):
        return f"{self.get_art_display()} {self.betrag} €"


class Link(models.Model):
    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="links")
    titel = models.CharField("Titel", max_length=150)
    url = models.URLField("URL", max_length=1000)

    class Meta:
        verbose_name = "Link"
        verbose_name_plural = "Links"
        ordering = ["reise", "id"]   # in der Reihenfolge der Eingabe

    def __str__(self):
        return self.titel


class Erinnerung(models.Model):
    """Eigene Erinnerung, z. B. „Fähre buchbar ab …“. Wird am Datum per Mail verschickt."""

    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="erinnerungen")
    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="erinnerungen", null=True, blank=True)
    datum = models.DateField("Erinnern am")
    text = models.CharField("Text", max_length=200)
    gesendet_am = models.DateTimeField("gesendet am", null=True, blank=True)
    erledigt = models.BooleanField("erledigt", default=False)

    class Meta:
        verbose_name = "Erinnerung"
        verbose_name_plural = "Erinnerungen"
        ordering = ["datum"]

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.text}"

    def save(self, *args, **kwargs):
        if self.reise_id and not self.familie_id:
            self.familie_id = self.reise.familie_id
        super().save(*args, **kwargs)


class Versandprotokoll(models.Model):
    """Merkt sich automatisch erzeugte Erinnerungen, damit jede nur einmal kommt."""

    schluessel = models.CharField(max_length=100, unique=True)
    gesendet_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Versandprotokoll"
        verbose_name_plural = "Versandprotokoll"


class Track(models.Model):
    """Tatsächlich gefahrene Strecke als GPX – meist aus der App „Tracking“. „Route aktualisieren“
    kann damit Entfernung, Fahrzeit und Linie der passenden Etappe ersetzen."""

    reise = models.ForeignKey(Reise, on_delete=models.CASCADE, related_name="tracks")
    name = models.CharField("Name", max_length=120, blank=True)
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende")
    entfernung_km = models.DecimalField("Entfernung (km)", max_digits=7, decimal_places=1)
    fahrzeit = models.DurationField("Fahrzeit", help_text="ohne Pausen zwischen den Teilstücken")
    linie = models.JSONField(default=list, editable=False)   # vereinfacht [[lat, lon], …] wie bei TomTom
    gpx = models.TextField(editable=False)
    hochgeladen_am = models.DateTimeField("hochgeladen am", auto_now_add=True)

    class Meta:
        verbose_name = "GPX-Track"
        verbose_name_plural = "GPX-Tracks"
        ordering = ["reise", "beginn"]

    def __str__(self):
        return self.name or f"Track {self.beginn:%d.%m. %H:%M}"
