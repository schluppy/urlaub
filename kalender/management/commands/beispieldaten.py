"""Beispieldaten zum Ausprobieren: Familie „Muster“ (Schleswig-Holstein) mit Zuhause in Kiel,
einem Fahrzeugprofil, den Schulferien SH 2027 und fünf erfundenen Urlauben 2027.
Mehrfach ausführbar – vorhandene Einträge bleiben unverändert.

    docker compose exec web python manage.py beispieldaten
    docker compose exec web python manage.py person_anlegen du@example.org "Dein Name" --familie Muster

Die Termine sind so gewählt, dass sie die Regeln des Kalenders zeigen: Abfahrt nach Feierabend
vor Karfreitag, Brückentag nach Himmelfahrt, Fronleichnam (in SH kein Feiertag).
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from fahrzeuge.models import Fahrzeugprofil
from kalender.models import Schulferien
from konten.models import Familie
from orte.models import Ort, Ortstyp
from reisen.models import Reise

# Quelle: https://www.schleswig-holstein.de/DE/landesregierung/themen/bildung-hochschulen/ferientermine
SCHULFERIEN_SH = [
    ("Weihnachtsferien", date(2026, 12, 21), date(2027, 1, 6)),
    ("Osterferien", date(2027, 3, 30), date(2027, 4, 10)),
    ("Ferientag nach Himmelfahrt", date(2027, 5, 7), date(2027, 5, 7)),
    ("Sommerferien", date(2027, 7, 3), date(2027, 8, 14)),
    ("Herbstferien", date(2027, 10, 11), date(2027, 10, 23)),
    ("Weihnachtsferien", date(2027, 12, 23), date(2028, 1, 8)),
]

# (Titel, Urlaub von, Urlaub bis, Abfahrt nach Feierabend = Reisebeginn vor dem Urlaub)
URLAUBE_2027 = [
    ("Ostern an der Nordsee", date(2027, 3, 26), date(2027, 3, 29), date(2027, 3, 25)),
    ("Himmelfahrt an der Ostsee", date(2027, 5, 7), date(2027, 5, 9), date(2027, 5, 5)),
    ("Campingtreffen", date(2027, 6, 3), date(2027, 6, 6), None),
    ("Sommerreise", date(2027, 8, 27), date(2027, 9, 20), None),
    ("Herbstwoche", date(2027, 10, 9), date(2027, 10, 16), None),
]


class Command(BaseCommand):
    help = "Beispielfamilie „Muster“ mit Zuhause, Fahrzeugprofil, Schulferien SH und Urlauben 2027"

    def add_arguments(self, parser):
        parser.add_argument("--familie", default="Muster", help="Name der Familie (wird bei Bedarf angelegt)")

    @transaction.atomic
    def handle(self, familie="Muster", **opts):
        familie, neu = Familie.objects.get_or_create(name=familie, defaults={"bundesland": "SH"})
        self._melden(f"Familie {familie}", neu)
        _, neu = Ort.objects.get_or_create(familie=familie, name="Zuhause", defaults={
            "typ": Ortstyp.ZUHAUSE, "adresse": "Rathausplatz 1, 24103 Kiel", "land": "DE",
            "breite": "54.322600", "laenge": "10.135500"})
        self._melden("Ort Zuhause", neu)

        gespann, neu = Fahrzeugprofil.objects.get_or_create(familie=familie, name="Gespann", defaults={
            "laenge_m": "12.50", "breite_m": "2.30", "hoehe_m": "2.60", "gesamtgewicht_kg": 3500,
            "achslast_kg": 1500, "achszahl": 3, "hoechstgeschwindigkeit_kmh": 100, "verbrauch_l_100km": "11.5",
            "notizen": "Beispielwerte – bitte durch die eigenen Maße ersetzen."})
        self._melden("Fahrzeugprofil Gespann", neu)

        anzahl = 0
        for bezeichnung, von, bis in SCHULFERIEN_SH:
            _, neu = Schulferien.objects.get_or_create(bundesland="SH", von=von,
                                                       defaults={"bezeichnung": bezeichnung, "bis": bis})
            anzahl += neu
        self.stdout.write(f"Schulferien SH: {anzahl} neu")

        anzahl = 0
        for titel, von, bis, feierabend in URLAUBE_2027:
            _, neu = Reise.objects.get_or_create(familie=familie, titel=titel, urlaub_von=von, defaults={
                "urlaub_bis": bis, "von": feierabend or von, "bis": bis, "fahrzeugprofil": gespann})
            anzahl += neu
        self.stdout.write(f"Reisen 2027: {anzahl} neu")

    def _melden(self, was, neu):
        self.stdout.write(f"{was}: {'angelegt' if neu else 'vorhanden'}")
