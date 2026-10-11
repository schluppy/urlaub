"""Verschickt fällige Erinnerungen. Täglich per Cron, z. B. um 7 Uhr:

    0 7 * * *  cd /opt/urlaub && docker compose exec -T web python manage.py erinnerungen
"""
from datetime import date

from django.core.management.base import BaseCommand

from reisen.erinnerungen import faellige, versenden


class Command(BaseCommand):
    help = "Fällige Erinnerungen (Restzahlungen, eigene, Reisecheck) per Mail verschicken"

    def add_arguments(self, parser):
        parser.add_argument("--trocken", action="store_true", help="nur anzeigen, nichts senden")
        parser.add_argument("--heute", type=date.fromisoformat, default=None, help="Datum JJJJ-MM-TT (zum Testen)")

    def handle(self, trocken=False, heute=None, **opts):
        heute = heute or date.today()
        if trocken:
            from konten.models import Familie
            punkte = [p for f in Familie.objects.all() for p in faellige(heute, f)]
        else:
            punkte = versenden(heute)
        vorne = f"{heute:%Y-%m-%d} {'(trocken) ' if trocken else ''}"
        for p in punkte:
            self.stdout.write(f"{vorne}{p.datum:%d.%m.%Y}  {p.titel}")
        if not punkte:
            self.stdout.write(f"{vorne}Nichts fällig.")
