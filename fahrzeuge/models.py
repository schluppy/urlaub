"""Fahrzeugprofile für das Routing (TomTom-Parameter vehicle*) und den Verbrauch."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Fahrzeugprofil(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="fahrzeugprofile")
    name = models.CharField("Name", max_length=80)
    laenge_m = models.DecimalField("Gesamtlänge (m)", max_digits=4, decimal_places=2,
                                   null=True, blank=True, help_text="inkl. Wohnwagen und Deichsel")
    breite_m = models.DecimalField("Breite (m)", max_digits=4, decimal_places=2, null=True, blank=True,
                                   help_text="breiteste Stelle, ohne Spiegel")
    hoehe_m = models.DecimalField("Höhe (m)", max_digits=4, decimal_places=2, null=True, blank=True)
    gesamtgewicht_kg = models.PositiveIntegerField("Gesamtgewicht (kg)", null=True, blank=True,
                                                   help_text="Zugfahrzeug + Wohnwagen")
    achslast_kg = models.PositiveIntegerField("Achslast (kg)", null=True, blank=True,
                                              help_text="höchste Achslast")
    achszahl = models.PositiveSmallIntegerField("Achszahl", null=True, blank=True)
    hoechstgeschwindigkeit_kmh = models.PositiveSmallIntegerField(
        "Höchstgeschwindigkeit (km/h)", default=100, validators=[MinValueValidator(30)])
    verbrauch_l_100km = models.DecimalField("Ø Verbrauch (L/100 km)", max_digits=4, decimal_places=1,
                                            default=Decimal("11.0"))
    verbrauchskurve = models.CharField(
        "Verbrauchskurve", max_length=200, blank=True,
        help_text="optional, TomTom-Format km/h,L/100km getrennt durch Doppelpunkt, "
                  "z. B. 50,8.5:80,11.0:100,13.5")
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Fahrzeugprofil"
        verbose_name_plural = "Fahrzeugprofile"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["familie", "name"], name="profil_name_je_familie")]

    def __str__(self):
        return self.name
