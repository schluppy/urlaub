from datetime import date

from django.test import TestCase
from django.urls import reverse

from konten.models import Person
from orte.models import Ort
from reisen.models import Buchung, Reise

from .hilfen import fam


class ZieleMitStatusTest(TestCase):
    def setUp(self):
        f = fam()
        self.rhein = Ort.objects.create(familie=f, name="Rheincamping", typ="zwischen")
        self.see = Ort.objects.create(familie=f, name="Seecamping")
        self.wald = Ort.objects.create(familie=f, name="Waldcamping", typ="zwischen")
        self.r = Reise.objects.create(familie=f, titel="Sommer", von=date(2027, 7, 5), bis=date(2027, 7, 23))
        for ort, von, bis, status in [(self.rhein, (7, 5), (7, 6), "gebucht"),
                                      (self.see, (7, 6), (7, 20), "angezahlt"),
                                      (self.wald, (7, 20), (7, 21), "geplant"),
                                      (self.rhein, (7, 21), (7, 22), "gebucht"),      # gleicher Platz, gleicher Status
                                      (self.see, (7, 22), (7, 23), "storniert")]:
            Buchung.objects.create(reise=self.r, ort=ort, von=date(2027, *von), bis=date(2027, *bis), status=status)
        self.client.force_login(Person.objects.create_user("t@example.org", "T", familie=f, is_staff=True))

    def test_reihenfolge_ohne_doppelte_und_stornierte(self):
        self.assertEqual(self.r.ziele_mit_status, [("Rheincamping", "gebucht", "gebucht"),
                                                   ("Seecamping", "angezahlt", "angezahlt"),
                                                   ("Waldcamping", "geplant", "geplant")])

    def test_gleicher_platz_mit_anderem_status_erscheint_zweimal(self):
        b = self.r.buchungen.get(von=date(2027, 7, 21))
        b.status = "angefragt"
        b.save()
        namen = [n for n, _, _ in Reise.objects.get(pk=self.r.pk).ziele_mit_status]
        self.assertEqual(namen, ["Rheincamping", "Seecamping", "Waldcamping", "Rheincamping"])

    def test_anzeige_in_der_jahresuebersicht(self):
        seite = self.client.get(reverse("portal:jahr", args=[2027])).content.decode()
        self.assertIn('<span class="ziel">Rheincamping <span class="status gebucht">gebucht</span></span>, '
                      '<span class="ziel">Seecamping <span class="status angezahlt">angezahlt</span></span>', seite)
        self.assertIn('<span class="status geplant">geplant</span>', seite)
        self.assertNotIn("storniert", seite)
