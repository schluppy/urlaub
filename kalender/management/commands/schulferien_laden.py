"""Schulferien eines Bundeslands aus der OpenHolidays API laden.

    docker compose exec web python manage.py schulferien_laden SH 2026 2028
    docker compose exec web python manage.py schulferien_laden ALLE 2027
"""
from django.core.management.base import BaseCommand, CommandError

from kalender.schulferien import SchulferienFehler, laden
from konten.models import Bundesland


class Command(BaseCommand):
    help = "Schulferien aus der OpenHolidays API laden (vorhandene Termine bleiben unverändert)"

    def add_arguments(self, parser):
        parser.add_argument("bundesland", choices=Bundesland.values + ["ALLE"], help="Kürzel, z. B. SH, oder ALLE")
        parser.add_argument("jahre", nargs="+", type=int)

    def handle(self, bundesland, jahre, **opts):
        try:
            neu, vorhanden = laden(Bundesland.values if bundesland == "ALLE" else bundesland, jahre)
        except SchulferienFehler as e:
            raise CommandError(str(e))
        for f in neu:
            self.stdout.write(f"neu:       {f.bundesland} {f}")
        for f in vorhanden:
            self.stdout.write(f"vorhanden: {f.bundesland} {f}")
        self.stdout.write(self.style.SUCCESS(f"{len(neu)} neu, {len(vorhanden)} schon vorhanden."))
