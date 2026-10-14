# Eigene Migration (eigene Transaktion): PostgreSQL ändert die Tabelle nicht,
# solange aus dem Zusammenfassen in 0003 noch Trigger-Ereignisse ausstehen.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('konten', '0003_nutzung_doppelte'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='apinutzung',
            constraint=models.UniqueConstraint(fields=('datum', 'schluessel', 'familie', 'art'), name='nutzung_je_tag', nulls_distinct=False),
        ),
    ]
