"""Lädt für Etappen ohne Streckenverlauf die Linie für die Karte nach (TomTom).
Entfernung, Fahrzeit und übrige Angaben bleiben unverändert.

    docker compose exec web python manage.py routenlinien            # nur fehlende
    docker compose exec web python manage.py routenlinien --alle     # alle neu
"""
from django.core.management.base import BaseCommand

from reisen.models import Etappe
from reisen.routing import TomTomFehler, etappe_linie_holen


class Command(BaseCommand):
    help = "Streckenverlauf für die Karte nachladen, ohne Entfernung und Fahrzeit zu ändern"

    def add_arguments(self, parser):
        parser.add_argument("--alle", action="store_true", help="auch Etappen, die schon eine Linie haben")

    def handle(self, alle=False, **opts):
        ok = fehler = 0
        for e in Etappe.objects.select_related("reise__fahrzeugprofil", "fahrzeugprofil", "von_ort", "nach_ort"):
            if not alle and (e.routing_details or {}).get("linie"):
                continue
            try:
                n = len(etappe_linie_holen(e))
                ok += 1
                self.stdout.write(f"{e.reise.titel}: {e} – {n} Punkte")
            except TomTomFehler as f:
                fehler += 1
                self.stderr.write(f"{e.reise.titel}: {e} – {f}")
        self.stdout.write(self.style.SUCCESS(f"{ok} Linien geladen, {fehler} Fehler."))
