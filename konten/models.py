"""Familien (Mandanten), Personen und Magic-Link-Login.

Jede Person gehört zu einer Familie und sieht nur deren Reisen, Orte und
Fahrzeugprofile. Der Super-Admin (is_superuser) legt Familien, Personen und
TomTom-Schlüssel an und pflegt die Schulferien – die Reisen anderer Familien
sieht auch er nicht. Keine Passwörter: Login über einmalig gültige Links per E-Mail.
"""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import DatabaseError, models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class Bundesland(models.TextChoices):
    BW = "BW", "Baden-Württemberg"
    BY = "BY", "Bayern"
    BE = "BE", "Berlin"
    BB = "BB", "Brandenburg"
    HB = "HB", "Bremen"
    HH = "HH", "Hamburg"
    HE = "HE", "Hessen"
    MV = "MV", "Mecklenburg-Vorpommern"
    NI = "NI", "Niedersachsen"
    NW = "NW", "Nordrhein-Westfalen"
    RP = "RP", "Rheinland-Pfalz"
    SL = "SL", "Saarland"
    SN = "SN", "Sachsen"
    ST = "ST", "Sachsen-Anhalt"
    SH = "SH", "Schleswig-Holstein"
    TH = "TH", "Thüringen"


class ApiSchluessel(models.Model):
    """Weiterer TomTom-Schlüssel. Familien ohne eigenen Schlüssel nutzen TOMTOM_API_KEY aus .env."""

    name = models.CharField("Name", max_length=80, unique=True, help_text="z. B. „Familie Müller“")
    schluessel = models.CharField("API-Schlüssel", max_length=100)
    aktiv = models.BooleanField("aktiv", default=True, help_text="inaktiv = Familien nutzen den Standardschlüssel")
    notiz = models.CharField("Notiz", max_length=200, blank=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "TomTom-Schlüssel"
        verbose_name_plural = "TomTom-Schlüssel"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.gekuerzt})"

    @property
    def gekuerzt(self):
        return f"…{self.schluessel[-4:]}" if self.schluessel else "–"


class Familie(models.Model):
    name = models.CharField("Name", max_length=80, unique=True)
    bundesland = models.CharField("Bundesland", max_length=2, choices=Bundesland.choices, default=Bundesland.SH,
                                  help_text="bestimmt Feiertage, Schulferien und Urlaubstage")
    api_schluessel = models.ForeignKey(ApiSchluessel, verbose_name="TomTom-Schlüssel", on_delete=models.PROTECT,
                                       null=True, blank=True, related_name="familien",
                                       help_text="leer = Standardschlüssel des Servers")
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Familie"
        verbose_name_plural = "Familien"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def bundesland_name(self):
        return Bundesland(self.bundesland).label

    def tomtom(self):
        """(Schlüssel, ApiSchluessel oder None für den Standardschlüssel)"""
        if self.api_schluessel and self.api_schluessel.aktiv:
            return self.api_schluessel.schluessel, self.api_schluessel
        return settings.TOMTOM_API_KEY, None


class ApiNutzung(models.Model):
    """Zähler der TomTom-Abrufe je Tag, Schlüssel, Familie und Art."""

    datum = models.DateField("Datum")
    schluessel = models.ForeignKey(ApiSchluessel, verbose_name="Schlüssel", null=True, blank=True,
                                   on_delete=models.SET_NULL, help_text="leer = Standardschlüssel")
    familie = models.ForeignKey(Familie, null=True, blank=True, on_delete=models.SET_NULL)
    art = models.CharField("Art", max_length=20)   # routing, geocoding, kachel
    anzahl = models.PositiveIntegerField("Anzahl", default=0)

    class Meta:
        verbose_name = "TomTom-Nutzung"
        verbose_name_plural = "TomTom-Nutzung"
        ordering = ["-datum", "familie", "art"]
        # eine Zeile je Tag, Schlüssel, Familie und Art – auch wenn Schlüssel oder Familie leer sind;
        # sonst legen gleichzeitige Abrufe (Kartenkacheln) doppelte Zeilen an und get() scheitert
        constraints = [models.UniqueConstraint(fields=["datum", "schluessel", "familie", "art"],
                                               nulls_distinct=False, name="nutzung_je_tag")]

    @classmethod
    def zaehlen(cls, familie, schluessel, art):
        """Zählt einen Abruf. Ein Fehler beim Zählen darf den Abruf selbst nie verhindern."""
        try:
            with transaction.atomic():
                eintrag, _ = cls.objects.get_or_create(datum=timezone.localdate(), schluessel=schluessel,
                                                       familie=familie, art=art)
                cls.objects.filter(pk=eintrag.pk).update(anzahl=models.F("anzahl") + 1)
        except DatabaseError:
            logger.exception("TomTom-Nutzung nicht gezählt")


class PersonManager(BaseUserManager):
    def create_user(self, email, name="", **extra):
        if not email:
            raise ValueError("E-Mail-Adresse fehlt")
        person = self.model(email=self.normalize_email(email).lower(), name=name, **extra)
        person.set_unusable_password()
        person.save(using=self._db)
        return person

    def create_superuser(self, email, name="", password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        person = self.create_user(email, name, **extra)
        if password:
            person.set_password(password)
            person.save(using=self._db)
        return person


class Person(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("E-Mail", unique=True)
    name = models.CharField("Name", max_length=150)
    is_active = models.BooleanField("aktiv", default=True)
    is_staff = models.BooleanField("Zugang Verwaltung", default=True)
    familie = models.ForeignKey(Familie, verbose_name="Familie", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="personen", help_text="leer nur beim Super-Admin ohne eigene Reisen")
    angelegt_am = models.DateTimeField(auto_now_add=True)

    objects = PersonManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["name"]

    def __str__(self):
        return self.name or self.email


class MagicLinkToken(models.Model):
    """Einmal-Token für den Login. Gespeichert wird nur der Hash."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="login_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateTimeField()
    verwendet_am = models.DateTimeField(null=True, blank=True)
    angefordert_von_ip = models.GenericIPAddressField(null=True, blank=True)
    ziel = models.CharField(max_length=200, blank=True, help_text="Seite nach dem Login")

    class Meta:
        verbose_name = "Login-Token"
        verbose_name_plural = "Login-Tokens"

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def erzeugen(cls, person, ip=None, gueltigkeit=None, ziel=""):
        """Gibt den Klartext-Token zurück; er steht nur im Link der E-Mail."""
        token = secrets.token_urlsafe(32)
        gueltigkeit = gueltigkeit or timedelta(minutes=settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN)
        cls.objects.create(
            person=person,
            token_hash=cls._hash(token),
            gueltig_bis=timezone.now() + gueltigkeit,
            angefordert_von_ip=ip,
            ziel=ziel,
        )
        return token

    @classmethod
    def finde_gueltig(cls, token):
        return cls.objects.select_related("person").filter(
            token_hash=cls._hash(token), verwendet_am__isnull=True, gueltig_bis__gte=timezone.now()
        ).first()

    @classmethod
    def zu_viele_anfragen(cls, person=None, ip=None):
        """Begrenzung: 5 Links pro Person und 20 pro IP-Adresse je Stunde."""
        seit = timezone.now() - timedelta(hours=1)
        if person and cls.objects.filter(person=person, erstellt_am__gte=seit).count() >= 5:
            return True
        if ip and cls.objects.filter(angefordert_von_ip=ip, erstellt_am__gte=seit).count() >= 20:
            return True
        return False

    @classmethod
    def einloesen(cls, token):
        """Liefert die Person bei gültigem Token, sonst None. Ein Token
        funktioniert genau einmal."""
        jetzt = timezone.now()
        eintrag = (
            cls.objects.select_related("person")
            .filter(token_hash=cls._hash(token), verwendet_am__isnull=True, gueltig_bis__gte=jetzt)
            .first()
        )
        if eintrag is None or not eintrag.person.is_active:
            return None
        # Bedingtes Update schützt gegen doppeltes Einlösen bei parallelen Klicks.
        aktualisiert = cls.objects.filter(pk=eintrag.pk, verwendet_am__isnull=True).update(
            verwendet_am=jetzt
        )
        return eintrag.person if aktualisiert else None
