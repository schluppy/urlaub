from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase

from orte.models import Ort
from reisen.models import Etappe, Reise

from .hilfen import fam


class FahrtKennzahlenTest(TestCase):
    """Entfernung/Fahrzeit der Reiseseite: vor dem Urlaub Hinweg, im Urlaub Rückweg, danach beides."""

    def setUp(self):
        z = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause", breite=Decimal("54.3"), laenge=Decimal("10.1"))
        p = Ort.objects.create(familie=fam(), name="Ferienpark")
        self.r = Reise.objects.create(familie=fam(), titel="Pfingsten", von=date(2027, 5, 28), bis=date(2027, 6, 6),
                                      urlaub_von=date(2027, 5, 29), urlaub_bis=date(2027, 6, 6))
        Etappe.objects.create(reise=self.r, datum=date(2027, 5, 28), von_ort=z, nach_ort=p, startzeit=time(17),
                              entfernung_km=Decimal("158.4"), fahrzeit=timedelta(hours=2, minutes=41))
        Etappe.objects.create(reise=self.r, datum=date(2027, 6, 6), von_ort=p, nach_ort=z, startzeit=time(10),
                              entfernung_km=Decimal("157.6"), fahrzeit=timedelta(hours=2, minutes=28))

    def test_phasen(self):
        self.assertEqual(self.r.fahrt_kennzahlen(date(2027, 5, 1)), ("Hinweg", Decimal("158.4"), timedelta(hours=2, minutes=41)))
        self.assertEqual(self.r.fahrt_kennzahlen(date(2027, 5, 29)), ("Rückweg", Decimal("157.6"), timedelta(hours=2, minutes=28)))
        self.assertEqual(self.r.fahrt_kennzahlen(date(2027, 6, 6))[0], "Rückweg")
        self.assertEqual(self.r.fahrt_kennzahlen(date(2027, 6, 7)),
                         ("Hin- und Rückweg", Decimal("316.0"), timedelta(hours=5, minutes=9)))

    def test_ohne_rueckweg_bleibt_hinweg(self):
        self.r.etappen.filter(datum=date(2027, 6, 6)).delete()
        self.assertEqual(self.r.fahrt_kennzahlen(date(2027, 6, 1))[0], "Hinweg")
