from datetime import date, time
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from freigaben.models import Widgetzugang
from freigaben.tracking import daten
from konten.models import Person
from orte.models import Ort
from reisen.models import Etappe, Reise

from .hilfen import fam

HEUTE = date(2027, 3, 1)


@mock.patch("freigaben.tracking.timezone.localdate", return_value=HEUTE)
class DatenTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.zuhause = Ort.objects.create(familie=self.f, name="Zuhause", typ="zuhause",
                                          breite=Decimal("47.790191"), laenge=Decimal("12.008675"))
        self.see = Ort.objects.create(familie=self.f, name="Seecamping", breite=Decimal("42.9"), laenge=Decimal("10.5"))
        self.faehre = Ort.objects.create(familie=self.f, name="Livorno", typ="faehre")
        self.reise = Reise.objects.create(familie=self.f, titel="Ostern", von=date(2027, 2, 28), bis=date(2027, 4, 5))

    def etappe(self, datum, von, nach, **kw):
        return Etappe.objects.create(reise=self.reise, datum=datum, von_ort=von, nach_ort=nach, **kw)

    def test_etappen_von_gestern_bis_in_dreissig_tagen_mit_orten(self, _):
        self.etappe(date(2027, 2, 27), self.zuhause, self.see)          # vorgestern – fehlt
        self.etappe(date(2027, 3, 2), self.see, self.faehre, startzeit=time(6, 30))
        self.etappe(date(2027, 2, 28), self.zuhause, self.see)
        self.etappe(date(2027, 3, 31), self.faehre, self.zuhause)       # Tag 30 – noch dabei
        self.etappe(date(2027, 4, 1), self.see, self.zuhause)           # Tag 31 – fehlt
        etappen = daten(self.f)["etappen"]
        self.assertEqual([(e["datum"], e["startzeit"], e["nach"]["name"]) for e in etappen],
                         [("2027-02-28", None, "Seecamping"), ("2027-03-02", "06:30", "Livorno"),
                          ("2027-03-31", None, "Zuhause")])
        self.assertEqual(etappen[0]["von"], {"name": "Zuhause", "typ": "zuhause", "breite": 47.790191, "laenge": 12.008675})
        self.assertEqual(etappen[1]["nach"], {"name": "Livorno", "typ": "faehre", "breite": None, "laenge": None})
        self.assertEqual(etappen[0]["reise"], "Ostern")

    def test_alternativen_und_andere_familien_fehlen(self, _):
        self.reise.im_kalender = False
        self.reise.save()
        self.etappe(HEUTE, self.zuhause, self.see)
        andere = fam("Andere")
        a, b = Ort.objects.create(familie=andere, name="A"), Ort.objects.create(familie=andere, name="B")
        fremd = Reise.objects.create(familie=andere, titel="Fremd", von=HEUTE, bis=HEUTE)
        Etappe.objects.create(reise=fremd, datum=HEUTE, von_ort=a, nach_ort=b)
        self.assertEqual(daten(self.f)["etappen"], [])


class ZugangTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.anna = Person.objects.create_user("anna@example.org", familie=self.f)
        self.client.force_login(self.anna)

    def test_seite_link_und_abruf(self):
        self.assertContains(self.client.get(reverse("portal:start")), reverse("freigaben:tracking"))
        self.assertContains(self.client.get(reverse("freigaben:tracking")), "Link erzeugen")
        self.client.post(reverse("freigaben:tracking"), {"aktion": "erzeugen"})
        zugang = Widgetzugang.objects.get(person=self.anna)
        seite = self.client.get(reverse("freigaben:tracking"))
        self.assertContains(seite, zugang.tracking_link)
        self.assertContains(seite, "urlaubstracking://einrichten?url=http")
        self.client.logout()
        antwort = self.client.get(reverse("freigaben:tracking_daten", args=[zugang.token]))
        self.assertEqual(antwort.json()["etappen"], [])
        zugang.beenden()
        self.assertEqual(self.client.get(reverse("freigaben:tracking_daten", args=[zugang.token])).status_code, 404)

    def test_apk_nur_angemeldet_und_wenn_vorhanden(self):
        with mock.patch("freigaben.views.TRACKING_APK") as apk:
            apk.exists.return_value = False
            self.assertEqual(self.client.get(reverse("freigaben:tracking_apk")).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("freigaben:tracking_apk")).status_code, 302)
