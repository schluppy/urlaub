"""Öffentliche Links mit Ablaufdatum für eine Reise oder den Jahreskalender.

Der Link funktioniert ohne Anmeldung und nur zum Ansehen. Der Token ist zufällig (128 Bit)
und wird im Klartext gespeichert, damit sich ein Link später erneut verschicken lässt.
"""
import secrets
from datetime import date, timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

MAX_TAGE = 366


def neuer_token():
    return secrets.token_urlsafe(16)


def abo_token():
    return secrets.token_urlsafe(24)


class Art(models.TextChoices):
    REISE = "reise", "Reise"
    KALENDER = "kalender", "Kalender"


class Freigabe(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="freigaben")
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    reise = models.ForeignKey("reisen.Reise", on_delete=models.CASCADE, null=True, blank=True, related_name="freigaben")
    jahr = models.PositiveSmallIntegerField("Jahr", null=True, blank=True)
    token = models.CharField(max_length=40, unique=True, default=neuer_token, editable=False)
    gueltig_bis = models.DateField("gültig bis", help_text="einschließlich dieses Tages")
    mit_details = models.BooleanField("Kosten und Buchungsdetails zeigen", default=False,
                                      help_text="Preise, Buchungsnummern, Kosten, Links und Notizen")
    fuer = models.CharField("für", max_length=80, blank=True, help_text="nur zur eigenen Übersicht, z. B. „Oma“")
    erstellt_von = models.ForeignKey("konten.Person", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    beendet_am = models.DateTimeField("beendet am", null=True, blank=True)
    aufrufe = models.PositiveIntegerField("Aufrufe", default=0)
    zuletzt_am = models.DateTimeField("zuletzt aufgerufen", null=True, blank=True)

    class Meta:
        verbose_name = "Freigabe"
        verbose_name_plural = "Freigaben"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"{self.titel} bis {self.gueltig_bis:%d.%m.%Y}"

    def clean(self):
        if self.gueltig_bis:
            if self.gueltig_bis < date.today():
                raise ValidationError({"gueltig_bis": "Das Ablaufdatum liegt in der Vergangenheit."})
            if self.gueltig_bis > date.today() + timedelta(days=MAX_TAGE):
                raise ValidationError({"gueltig_bis": "Höchstens ein Jahr im Voraus."})

    @property
    def titel(self):
        return self.reise.titel if self.art == Art.REISE else f"Urlaubskalender {self.jahr}"

    @property
    def aktiv(self):
        return self.beendet_am is None and self.gueltig_bis >= date.today()

    @property
    def link(self):
        return settings.BASIS_URL + reverse("freigaben:ansehen", args=[self.token])

    @property
    def nachricht(self):
        return f"{self.titel} – zum Ansehen bis {self.gueltig_bis:%d.%m.%Y}:\n{self.link}"

    @property
    def whatsapp(self):
        return "https://wa.me/?text=" + quote(self.nachricht)

    @property
    def email(self):
        return f"mailto:?subject={quote(self.titel)}&body={quote(self.nachricht)}"

    def aufgerufen(self):
        Freigabe.objects.filter(pk=self.pk).update(aufrufe=models.F("aufrufe") + 1, zuletzt_am=timezone.now())

    def beenden(self):
        if self.beendet_am is None:
            self.beendet_am = timezone.now()
            self.save(update_fields=["beendet_am"])


class Kalenderabo(models.Model):
    """Geheimer Link für ein Kalender-Abonnement (iCal), z. B. in Google Kalender.
    Je Person höchstens ein aktiver Link; er zeigt die Urlaube ihrer Familie."""

    person = models.ForeignKey("konten.Person", on_delete=models.CASCADE, related_name="kalenderabos")
    token = models.CharField(max_length=60, unique=True, default=abo_token, editable=False)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    beendet_am = models.DateTimeField("beendet am", null=True, blank=True)
    abrufe = models.PositiveIntegerField("Abrufe", default=0)
    zuletzt_am = models.DateTimeField("zuletzt abgerufen", null=True, blank=True)

    class Meta:
        verbose_name = "Kalender-Abo"
        verbose_name_plural = "Kalender-Abos"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"Kalender-Abo {self.person}"

    @property
    def aktiv(self):
        return self.beendet_am is None and self.person.is_active and self.person.familie_id is not None

    @property
    def link(self):
        return settings.BASIS_URL + reverse("freigaben:abo_feed", args=[self.token])

    @property
    def webcal(self):
        return "webcal://" + self.link.split("://", 1)[1]

    def abgerufen(self):
        Kalenderabo.objects.filter(pk=self.pk).update(abrufe=models.F("abrufe") + 1, zuletzt_am=timezone.now())

    def beenden(self):
        if self.beendet_am is None:
            self.beendet_am = timezone.now()
            self.save(update_fields=["beendet_am"])
