"""Fahrzeugprofil: gehört jetzt einer Familie. Vorhandene Einträge kommen in die erste Familie."""
import django.db.models.deletion
from django.db import migrations, models


def zuordnen(apps, schema_editor):
    Familie = apps.get_model("konten", "Familie")
    modelle = [apps.get_model("fahrzeuge", m) for m in ['Fahrzeugprofil']]
    if not any(m.objects.exists() for m in modelle):
        return
    familie = Familie.objects.order_by("id").first() or Familie.objects.create(name="Standard", bundesland="SH")
    for m in modelle:
        m.objects.filter(familie__isnull=True).update(familie=familie)


class Migration(migrations.Migration):

    dependencies = [
        ("konten", "0002_familien"),
        ("fahrzeuge", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fahrzeugprofil",
            name="familie",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fahrzeugprofile", to="konten.familie"),
        ),
        migrations.RunPython(zuordnen, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fahrzeugprofil",
            name="familie",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fahrzeugprofile", to="konten.familie"),
        ),
        migrations.AlterField(
            model_name="fahrzeugprofil",
            name="name",
            field=models.CharField(max_length=80, verbose_name="Name"),
        ),
        migrations.AddConstraint(
            model_name="fahrzeugprofil",
            constraint=models.UniqueConstraint(fields=("familie", "name"), name="profil_name_je_familie"),
        ),
    ]
