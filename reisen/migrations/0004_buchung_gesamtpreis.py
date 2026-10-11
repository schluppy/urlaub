"""Buchung: Gesamtpreis als Alternative zum Preis pro Nacht, Feld „Gebühren“ entfällt.

Vorhandene Gebühren gehen in den Gesamtpreis über (Gesamtpreis = Nächte × Preis/Nacht + Gebühren).
"""
from decimal import Decimal

from django.db import migrations, models


def gebuehren_in_gesamtpreis(apps, schema_editor):
    Buchung = apps.get_model("reisen", "Buchung")
    for b in Buchung.objects.exclude(gebuehren=0):
        naechte = (b.bis - b.von).days
        b.gesamtpreis = naechte * (b.preis_pro_nacht or Decimal(0)) + b.gebuehren
        b.preis_pro_nacht = None
        b.save(update_fields=["gesamtpreis", "preis_pro_nacht"])


def gesamtpreis_in_gebuehren(apps, schema_editor):
    Buchung = apps.get_model("reisen", "Buchung")
    for b in Buchung.objects.all():
        if b.gesamtpreis is not None:
            b.gebuehren, b.preis_pro_nacht = b.gesamtpreis, Decimal(0)
        elif b.preis_pro_nacht is None:
            b.preis_pro_nacht = Decimal(0)
        b.save(update_fields=["gebuehren", "preis_pro_nacht"])


class Migration(migrations.Migration):

    dependencies = [
        ("reisen", "0003_alter_etappe_options_remove_etappe_reihenfolge"),
    ]

    operations = [
        migrations.AddField(
            model_name="buchung",
            name="gesamtpreis",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="für den ganzen Aufenthalt – statt Preis/Nacht",
                                      max_digits=9, null=True, verbose_name="Gesamtpreis"),
        ),
        migrations.AlterField(
            model_name="buchung",
            name="preis_pro_nacht",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Preis/Nacht"),
        ),
        migrations.RunPython(gebuehren_in_gesamtpreis, gesamtpreis_in_gebuehren),
        migrations.RemoveField(
            model_name="buchung",
            name="gebuehren",
        ),
    ]
