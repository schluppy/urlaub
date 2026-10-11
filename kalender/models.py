from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Schulferien(models.Model):
    bundesland = models.CharField("Bundesland", max_length=2, default=settings.BUNDESLAND)
    bezeichnung = models.CharField("Bezeichnung", max_length=80, help_text="z. B. Osterferien")
    von = models.DateField("Von")
    bis = models.DateField("Bis")

    class Meta:
        verbose_name = "Schulferien"
        verbose_name_plural = "Schulferien"
        ordering = ["von"]
        constraints = [models.UniqueConstraint(fields=["bundesland", "von"], name="ferien_eindeutig")]

    def __str__(self):
        return f"{self.bezeichnung} {self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError({"bis": "„Bis“ liegt vor „Von“."})

    @classmethod
    def im_jahr(cls, jahr, bundesland=None):
        """Alle Ferien, die das Jahr berühren (auch Weihnachtsferien über den Jahreswechsel)."""
        return cls.objects.filter(bundesland=bundesland or settings.BUNDESLAND,
                                  von__year__lte=jahr, bis__year__gte=jahr)
