"""Orte: Zuhause, Campingplätze, Fährterminals. Jeder Ort gibt es nur einmal
und wird von Etappen und Buchungen verknüpft."""
from django.db import models


class Ortstyp(models.TextChoices):
    ZUHAUSE = "zuhause", "Zuhause"
    CAMPINGPLATZ = "camping", "Campingplatz"
    ZWISCHEN = "zwischen", "Zwischenübernachtung"
    FAEHRE = "faehre", "Fährterminal"
    SONSTIGES = "sonstiges", "Sonstiges"


class Bewertung(models.IntegerChoices):
    EINS = 1, "★☆☆☆☆ schlecht"
    ZWEI = 2, "★★☆☆☆ mäßig"
    DREI = 3, "★★★☆☆ ordentlich"
    VIER = 4, "★★★★☆ gut"
    FUENF = 5, "★★★★★ ausgezeichnet"


class Ort(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="orte")
    name = models.CharField("Name", max_length=150)
    typ = models.CharField("Typ", max_length=20, choices=Ortstyp.choices, default=Ortstyp.CAMPINGPLATZ)
    adresse = models.CharField("Adresse", max_length=300, blank=True)
    land = models.CharField("Land", max_length=3, blank=True,
                            help_text="ISO-Kürzel, z. B. DE, IT, GB (für Vignetten und Übersicht)")
    breite = models.DecimalField("Breite", max_digits=9, decimal_places=6, null=True, blank=True)
    laenge = models.DecimalField("Länge", max_digits=9, decimal_places=6, null=True, blank=True)
    website = models.URLField("Website", max_length=500, blank=True)
    bewertung = models.PositiveSmallIntegerField("Bewertung", choices=Bewertung.choices, null=True, blank=True,
                                                 help_text="eure Meinung – erscheint nicht in geteilten Links")
    preise = models.TextField("Preise", blank=True,
                              help_text="z. B. „Stellplatz 34 €/Nacht, Strom 4 €, Kurtaxe 2 € p. P.“")
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Ort"
        verbose_name_plural = "Orte"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["familie", "name"], name="ort_name_je_familie")]

    def __str__(self):
        return self.name

    @property
    def sterne(self):
        """„★★★★☆“ oder leer"""
        return "★" * self.bewertung + "☆" * (5 - self.bewertung) if self.bewertung else ""

    @property
    def hat_koordinaten(self):
        return self.breite is not None and self.laenge is not None

    @property
    def koordinaten(self):
        """„lat,lon“ wie es die TomTom-API erwartet."""
        return f"{self.breite},{self.laenge}" if self.hat_koordinaten else ""

    @classmethod
    def zuhause(cls, familie):
        return cls.objects.filter(familie=familie, typ=Ortstyp.ZUHAUSE).first()
