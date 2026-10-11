"""Reise: Urlaub (Kalender, Urlaubstage) und Reisezeit (unterwegs) getrennt.

Bisher: von/bis = Urlaub, dazu optional „Abfahrt nach Feierabend“.
Jetzt:  urlaub_von/urlaub_bis = bisheriges von/bis;
        von/bis = Reisezeit – erste bis letzte Etappe, ohne Etappen Feierabend-Tag bzw. von / bis.
Die Feierabend-Abfahrt ergibt sich künftig aus Reisebeginn an einem Arbeitstag vor dem Urlaub.
"""
from django.db import migrations, models


def aufteilen(apps, schema_editor):
    Reise = apps.get_model("reisen", "Reise")
    Etappe = apps.get_model("reisen", "Etappe")
    for r in Reise.objects.all():
        r.urlaub_von, r.urlaub_bis = r.von, r.bis
        daten = list(Etappe.objects.filter(reise=r).order_by("datum").values_list("datum", flat=True))
        if daten:
            r.von, r.bis = daten[0], daten[-1]
        elif r.abfahrt_feierabend:
            r.von = r.abfahrt_feierabend
        r.save(update_fields=["urlaub_von", "urlaub_bis", "von", "bis"])


def zusammenfuehren(apps, schema_editor):
    Reise = apps.get_model("reisen", "Reise")
    for r in Reise.objects.all():
        if r.urlaub_von and r.von < r.urlaub_von:
            r.abfahrt_feierabend = r.von
        r.von, r.bis = r.urlaub_von or r.von, r.urlaub_bis or r.bis
        r.save(update_fields=["abfahrt_feierabend", "von", "bis"])


class Migration(migrations.Migration):

    dependencies = [
        ("reisen", "0004_buchung_gesamtpreis"),
    ]

    operations = [
        migrations.AddField(
            model_name="reise",
            name="urlaub_von",
            field=models.DateField(blank=True, help_text="erster Urlaubstag (inkl. Vorbereitung); leer = wie Reisezeit",
                                   null=True, verbose_name="Urlaub von"),
        ),
        migrations.AddField(
            model_name="reise",
            name="urlaub_bis",
            field=models.DateField(blank=True, help_text="letzter Urlaubstag (inkl. Nachbereitung)", null=True,
                                   verbose_name="Urlaub bis"),
        ),
        migrations.RunPython(aufteilen, zusammenfuehren),
        migrations.RemoveField(
            model_name="reise",
            name="abfahrt_feierabend",
        ),
        migrations.AlterField(
            model_name="reise",
            name="von",
            field=models.DateField(help_text="Abfahrt. Liegt sie an einem Arbeitstag vor dem Urlaub, gilt sie als "
                                             "„Abfahrt nach Feierabend“.", verbose_name="Reisezeit von"),
        ),
        migrations.AlterField(
            model_name="reise",
            name="bis",
            field=models.DateField(help_text="Rückkehr", verbose_name="Reisezeit bis"),
        ),
    ]
