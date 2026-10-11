"""Familien (Mandanten), TomTom-Schlüssel und Nutzungszähler.

Gibt es schon Personen, kommen sie in eine Familie „Standard“ (Schleswig-Holstein).
"""
import django.db.models.deletion
from django.db import migrations, models


BUNDESLAENDER = [("BW", "Baden-Württemberg"), ("BY", "Bayern"), ("BE", "Berlin"), ("BB", "Brandenburg"),
                 ("HB", "Bremen"), ("HH", "Hamburg"), ("HE", "Hessen"), ("MV", "Mecklenburg-Vorpommern"),
                 ("NI", "Niedersachsen"), ("NW", "Nordrhein-Westfalen"), ("RP", "Rheinland-Pfalz"),
                 ("SL", "Saarland"), ("SN", "Sachsen"), ("ST", "Sachsen-Anhalt"), ("SH", "Schleswig-Holstein"),
                 ("TH", "Thüringen")]


def bestehende_zuordnen(apps, schema_editor):
    Person = apps.get_model("konten", "Person")
    Familie = apps.get_model("konten", "Familie")
    if Person.objects.exists():
        familie, _ = Familie.objects.get_or_create(name="Standard", defaults={"bundesland": "SH"})
        Person.objects.filter(familie__isnull=True).update(familie=familie)


class Migration(migrations.Migration):

    dependencies = [
        ("konten", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiSchluessel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="z. B. „Familie Müller“", max_length=80, unique=True, verbose_name="Name")),
                ("schluessel", models.CharField(max_length=100, verbose_name="API-Schlüssel")),
                ("aktiv", models.BooleanField(default=True, help_text="inaktiv = Familien nutzen den Standardschlüssel", verbose_name="aktiv")),
                ("notiz", models.CharField(blank=True, max_length=200, verbose_name="Notiz")),
                ("angelegt_am", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "TomTom-Schlüssel", "verbose_name_plural": "TomTom-Schlüssel", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Familie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True, verbose_name="Name")),
                ("bundesland", models.CharField(choices=BUNDESLAENDER, default="SH", help_text="bestimmt Feiertage, Schulferien und Urlaubstage", max_length=2, verbose_name="Bundesland")),
                ("angelegt_am", models.DateTimeField(auto_now_add=True)),
                ("api_schluessel", models.ForeignKey(blank=True, help_text="leer = Standardschlüssel des Servers", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="familien", to="konten.apischluessel", verbose_name="TomTom-Schlüssel")),
            ],
            options={"verbose_name": "Familie", "verbose_name_plural": "Familien", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ApiNutzung",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("datum", models.DateField(verbose_name="Datum")),
                ("art", models.CharField(max_length=20, verbose_name="Art")),
                ("anzahl", models.PositiveIntegerField(default=0, verbose_name="Anzahl")),
                ("familie", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="konten.familie")),
                ("schluessel", models.ForeignKey(blank=True, help_text="leer = Standardschlüssel", null=True, on_delete=django.db.models.deletion.SET_NULL, to="konten.apischluessel", verbose_name="Schlüssel")),
            ],
            options={"verbose_name": "TomTom-Nutzung", "verbose_name_plural": "TomTom-Nutzung", "ordering": ["-datum", "familie", "art"]},
        ),
        migrations.AddField(
            model_name="person",
            name="familie",
            field=models.ForeignKey(blank=True, help_text="leer nur beim Super-Admin ohne eigene Reisen", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="personen", to="konten.familie", verbose_name="Familie"),
        ),
        migrations.RunPython(bestehende_zuordnen, migrations.RunPython.noop),
    ]
