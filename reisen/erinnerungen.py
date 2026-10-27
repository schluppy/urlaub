"""Erinnerungen per Mail: Restzahlungen, eigene Erinnerungen, Reisecheck vor Abfahrt.

Täglich per Cron: `manage.py erinnerungen`. Jede Erinnerung kommt nur einmal
(eigene: Feld `gesendet_am`, automatische: `Versandprotokoll`).
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Prefetch
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from konten.models import Familie

from .mitreise import angenommen, fuer, sichtbar
from .models import Buchung, Buchungsstatus, Erinnerung, Etappe, MitreiseBuchung, Reise, Versandprotokoll

REST_VORLAUF_TAGE = 7       # erste Mail so viele Tage vor Fälligkeit
REST_NACHLAUF_TAGE = 14     # überfällige Zahlungen nur so lange melden (alte Daten nicht anmahnen)
REISECHECK_TAGE = 14        # Reisecheck so viele Tage vor dem ersten Reisetag


@dataclass
class Punkt:
    art: str                 # "rest", "erinnerung", "reise"
    datum: object
    titel: str
    zeilen: list = field(default_factory=list)
    reise: Reise | None = None
    schluessel: str = ""     # für das Versandprotokoll
    erinnerung: Erinnerung | None = None
    dringend: bool = False

    @property
    def link(self):
        return settings.BASIS_URL + reverse("reisen:reise", args=[self.reise.pk]) if self.reise else ""


def _offene_buchungen(familie):
    """Eigene Buchungen und – bei gemeinsamen Reisen – die eigenen Angaben zu Buchungen der anderen Familie.
    Jede mit `schluessel` fürs Versandprotokoll."""
    offen = {"rest_faellig_am__isnull": False}
    erledigt = {"status__in": [Buchungsstatus.BEZAHLT, Buchungsstatus.STORNIERT]}
    buchungen = []
    for b in Buchung.objects.filter(reise__familie=familie, **offen).exclude(**erledigt).select_related("ort", "reise"):
        b.schluessel = f"rest-{b.pk}"
        buchungen.append(b)
    for mb in (MitreiseBuchung.objects.filter(mitreise__in=angenommen(familie), **offen).exclude(**erledigt)
               .select_related("buchung__ort", "buchung__reise")):
        b = mb.als_buchung()
        b.schluessel = f"rest-mit{mb.pk}"
        buchungen.append(b)
    return buchungen


def _rest_text(b):
    betrag = f"{b.rest:.2f} {b.waehrung}".replace(".", ",")
    if b.ist_fremdwaehrung:
        betrag += f" (ca. {b.rest_eur:.2f} €)".replace(".", ",")
    return betrag


def restzahlungen(heute, familie, vorlauf=REST_VORLAUF_TAGE):
    punkte = []
    for b in _offene_buchungen(familie):
        if b.rest <= 0:
            continue
        tage = (b.rest_faellig_am - heute).days
        if 0 < tage <= vorlauf:
            stufe, titel = "vorab", f"Restzahlung {b.ort} in {tage} Tag{'en' if tage > 1 else ''} fällig"
        elif -REST_NACHLAUF_TAGE <= tage <= 0:
            stufe = "faellig"
            titel = f"Restzahlung {b.ort} " + ("heute fällig" if tage == 0 else f"seit {-tage} Tag{'en' if tage < -1 else ''} fällig")
        else:
            continue
        punkte.append(Punkt(
            art="rest", datum=b.rest_faellig_am, titel=titel, reise=b.reise, dringend=stufe == "faellig",
            zeilen=[f"{_rest_text(b)} bis {b.rest_faellig_am:%d.%m.%Y}",
                    f"{b.reise.titel}, {b.von:%d.%m.}–{b.bis:%d.%m.%Y}"
                    + (f", Buchungsnr. {b.buchungsnummer}" if b.buchungsnummer else "")
                    + (f", Stellplatz {b.stellplatz}" if b.stellplatz else "")]
            + ([f"Website: {b.ort.website}"] if b.ort.website else []),
            schluessel=f"{b.schluessel}-{b.rest_faellig_am:%Y%m%d}-{stufe}"))
    return punkte


def _eigene_erinnerungen(familie):
    return Erinnerung.objects.filter(familie=familie).select_related("reise")


def eigene(heute, familie):
    return [Punkt(art="erinnerung", datum=e.datum, titel=e.text, reise=e.reise, erinnerung=e,
                  zeilen=[e.reise.titel] if e.reise else [])
            for e in _eigene_erinnerungen(familie).filter(datum__lte=heute, gesendet_am__isnull=True, erledigt=False)]


def _reisen_ab(heute, tage, familie):
    return fuer(sichtbar(familie).filter(im_kalender=True, bis__gte=heute, von__lte=heute + timedelta(days=tage + 1))
                .select_related("fahrzeugprofil", "familie")
                .prefetch_related(Prefetch("etappen", queryset=Etappe.objects.select_related("von_ort", "nach_ort")),
                                  Prefetch("buchungen", queryset=Buchung.objects.select_related("ort")), "kosten"),
                familie)


def reisechecks(heute, familie, tage=REISECHECK_TAGE):
    punkte = []
    for r in _reisen_ab(heute, tage, familie):
        bis_start = (r.von - heute).days
        if not 0 <= bis_start <= tage:
            continue
        zeilen = [f"{text}" for _, text in r.hinweise(heute)]
        erste = next(iter(r.etappen.all()), None)
        if erste and erste.startzeit:
            zeilen.insert(0, f"Abfahrt {erste.datum:%d.%m.} um {erste.startzeit:%H:%M} nach {erste.nach_ort}")
        if r.offen_eur:
            zeilen.append(f"Noch offen: {r.offen_eur:.2f} €".replace(".", ","))
        if not zeilen:
            zeilen.append("Keine offenen Punkte.")
        punkte.append(Punkt(art="reise", datum=r.von, reise=r,
                            titel=f"{r.titel} beginnt in {bis_start} Tag{'en' if bis_start != 1 else ''}"
                            if bis_start else f"{r.titel} beginnt heute",
                            zeilen=zeilen, schluessel=f"reise-{r.pk}{f'-mit{r.mitreise.pk}' if r.mitreise else ''}"
                                                      f"-{r.von:%Y%m%d}-check"))
    return punkte


def faellige(heute, familie):
    """Alles, was heute für die Familie verschickt werden soll und noch nicht verschickt wurde."""
    punkte = eigene(heute, familie) + restzahlungen(heute, familie) + reisechecks(heute, familie)
    schon = set(Versandprotokoll.objects.filter(
        schluessel__in=[p.schluessel for p in punkte if p.schluessel]).values_list("schluessel", flat=True))
    punkte = [p for p in punkte if not p.schluessel or p.schluessel not in schon]
    return sorted(punkte, key=lambda p: (not p.dringend, p.datum))


def anstehend(heute, familie, tage=30):
    """Für die Startseite: was in den nächsten Wochen ansteht (unabhängig vom Versand)."""
    punkte = restzahlungen(heute, familie, vorlauf=tage)
    punkte += [Punkt(art="erinnerung", datum=e.datum, titel=e.text, reise=e.reise, erinnerung=e,
                     dringend=e.datum <= heute)
               for e in _eigene_erinnerungen(familie).filter(erledigt=False, datum__lte=heute + timedelta(days=tage))]
    punkte += reisechecks(heute, familie, tage=tage)
    return sorted(punkte, key=lambda p: p.datum)


def _familie_versenden(heute, familie, empfaenger):
    punkte = faellige(heute, familie)
    if not punkte:
        return []
    betreff = (f"Urlaubsplaner: {punkte[0].titel}" if len(punkte) == 1
               else f"Urlaubsplaner: {len(punkte)} Erinnerungen")
    with transaction.atomic():
        jetzt = timezone.now()
        for p in punkte:
            if p.erinnerung:
                p.erinnerung.gesendet_am = jetzt
                p.erinnerung.save(update_fields=["gesendet_am"])
            elif p.schluessel:
                Versandprotokoll.objects.create(schluessel=p.schluessel)
        # Mailfehler rollen die Markierungen zurück – dann kommt alles am nächsten Tag erneut.
        for person in empfaenger:
            text = render_to_string("reisen/mail/erinnerungen.txt", {
                "person": person, "punkte": punkte, "heute": heute,
                "verwaltung": settings.BASIS_URL + reverse("admin:reisen_erinnerung_changelist")})
            send_mail(betreff, text, settings.DEFAULT_FROM_EMAIL, [person.email])
    return punkte


def versenden(heute, familie=None, empfaenger=None):
    """Je Familie eine Mail an ihre aktiven Mitglieder, nur mit ihren Punkten. Liefert alle Punkte."""
    familien = [familie] if familie else list(Familie.objects.all())
    punkte = []
    for f in familien:
        an = list(empfaenger) if empfaenger is not None else list(f.personen.filter(is_active=True))
        punkte += _familie_versenden(heute, f, an)
    return punkte
