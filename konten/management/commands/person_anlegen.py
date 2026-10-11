"""Legt eine Person an, die sich per Anmeldelink einloggen darf.

    docker compose exec web python manage.py person_anlegen ADRESSE "NAME" --familie Muster --super-admin

Weitere Personen legt der Super-Admin danach in der Verwaltung an (Personen).
"""
from django.core.management.base import BaseCommand, CommandError

from konten.models import Familie, Person


class Command(BaseCommand):
    help = "Person mit E-Mail-Adresse anlegen (voller Zugriff, kein Passwort)"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("name")
        parser.add_argument("--familie", help="Name der Familie; wird bei Bedarf angelegt (Bundesland SH)")
        parser.add_argument("--super-admin", action="store_true", help="darf Familien, Personen und Schlüssel verwalten")

    def handle(self, email, name, familie=None, super_admin=False, **opts):
        email = email.strip().lower()
        if Person.objects.filter(email=email).exists():
            raise CommandError(f"{email} ist schon angelegt.")
        if familie:
            familie, _ = Familie.objects.get_or_create(name=familie, defaults={"bundesland": "SH"})
        Person.objects.create_user(email, name, familie=familie, is_staff=True, is_superuser=super_admin)
        self.stdout.write(self.style.SUCCESS(f"{name} <{email}> angelegt. Anmelden unter /anmelden/."))
