"""Reise und Erinnerung: gehört jetzt einer Familie. Vorhandene Einträge kommen in die erste Familie."""
import django.db.models.deletion
from django.db import migrations, models


def zuordnen(apps, schema_editor):
    Familie = apps.get_model("konten", "Familie")
    modelle = [apps.get_model("reisen", m) for m in ['Reise', 'Erinnerung']]
    if not any(m.objects.exists() for m in modelle):
        return
    familie = Familie.objects.order_by("id").first() or Familie.objects.create(name="Standard", bundesland="SH")
    for m in modelle:
        m.objects.filter(familie__isnull=True).update(familie=familie)


class Migration(migrations.Migration):

    dependencies = [
        ("konten", "0002_familien"),
        ("reisen", "0006_link_ohne_nummer"),
    ]

    operations = [
        migrations.AddField(
            model_name="reise",
            name="familie",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reisen", to="konten.familie"),
        ),
        migrations.AddField(
            model_name="erinnerung",
            name="familie",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="erinnerungen", to="konten.familie"),
        ),
        migrations.RunPython(zuordnen, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="reise",
            name="familie",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reisen", to="konten.familie"),
        ),
        migrations.AlterField(
            model_name="erinnerung",
            name="familie",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="erinnerungen", to="konten.familie"),
        ),

    ]
