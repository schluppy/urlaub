from datetime import date, time, timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from freigaben.models import Widgetzugang
from freigaben.widget import daten
from konten.models import Person
from orte.models import Ort
from reisen.models import Etappe, Reise

from .hilfen import fam

HEUTE = date(2027, 3, 1)


@mock.patch("freigaben.widget.timezone.localdate", return_value=HEUTE)
class DatenTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.zuhause = Ort.objects.create(familie=self.f, name="Zuhause", typ="zuhause")
        self.see = Ort.objects.create(familie=self.f, name="Seecamping")

    def reise(self, titel, von, bis, **kw):
        return Reise.objects.create(familie=self.f, titel=titel, von=von, bis=bis, **kw)

    def test_erste_etappe_mit_startzeit_und_ohne_etappen_die_abfahrt(self, _):
        ostern = self.reise("Ostern", date(2027, 3, 26), date(2027, 4, 5))
        Etappe.objects.create(reise=ostern, datum=date(2027, 3, 26), von_ort=self.zuhause, nach_ort=self.see)
        Etappe.objects.create(reise=ostern, datum=date(2027, 3, 26), startzeit=time(14, 30),
                              von_ort=self.zuhause, nach_ort=self.see)
        Etappe.objects.create(reise=ostern, datum=date(2027, 3, 27), startzeit=time(6, 0),
                              von_ort=self.see, nach_ort=self.see)
        self.reise("Sommer", date(2027, 7, 10), date(2027, 7, 30))
        reisen = daten(self.f)["reisen"]
        self.assertEqual([(r["titel"], r["datum"], r["uhrzeit"]) for r in reisen],
                         [("Ostern", "2027-03-26", "14:30"), ("Sommer", "2027-07-10", None)])
        self.assertEqual(reisen[1]["warten_seit"], "2027-04-05")   # Rückkehr von Ostern

    def test_vergangene_alternativen_und_andere_familien_fehlen(self, _):
        self.reise("Herbst", date(2026, 10, 1), date(2026, 10, 10))
        self.reise("Alternative", date(2027, 5, 1), date(2027, 5, 5), im_kalender=False)
        Reise.objects.create(familie=fam("Andere"), titel="Fremd", von=date(2027, 4, 1), bis=date(2027, 4, 2))
        heute = self.reise("Heute", HEUTE, HEUTE + timedelta(days=3))
        reisen = daten(self.f)["reisen"]
        self.assertEqual([r["titel"] for r in reisen], ["Heute"])
        self.assertEqual(reisen[0]["warten_seit"], "2026-10-10")
        self.assertTrue(reisen[0]["link"].endswith(reverse("reisen:reise", args=[heute.pk])))


class ZugangTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.anna = Person.objects.create_user("anna@example.org", familie=self.f)
        self.client.force_login(self.anna)
        Reise.objects.create(familie=self.f, titel="Sommer", von=date(2099, 7, 1), bis=date(2099, 7, 20))

    def test_erzeugen_abrufen_beenden(self):
        self.assertContains(self.client.get(reverse("freigaben:widget")), "Widget-Link erzeugen")
        self.client.post(reverse("freigaben:widget"), {"aktion": "erzeugen"})
        zugang = Widgetzugang.objects.get(person=self.anna)
        seite = self.client.get(reverse("freigaben:widget"))
        self.assertContains(seite, zugang.link)
        self.assertContains(seite, "urlaubswidget://einrichten?url=http")
        self.client.logout()
        antwort = self.client.get(reverse("freigaben:widget_daten", args=[zugang.token]))
        self.assertEqual(antwort.json()["reisen"][0]["titel"], "Sommer")
        zugang.refresh_from_db()
        self.assertEqual(zugang.abrufe, 1)
        self.client.force_login(self.anna)
        self.client.post(reverse("freigaben:widget"), {"aktion": "beenden"})
        self.assertEqual(self.client.get(reverse("freigaben:widget_daten", args=[zugang.token])).status_code, 404)

    def test_gesperrte_person_und_unbekannter_link(self):
        zugang = Widgetzugang.objects.create(person=self.anna)
        self.anna.is_active = False
        self.anna.save()
        self.assertEqual(self.client.get(reverse("freigaben:widget_daten", args=[zugang.token])).status_code, 404)
        self.assertEqual(self.client.get(reverse("freigaben:widget_daten", args=["gibt-es-nicht"])).status_code, 404)

    def test_app_nur_angemeldet(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("freigaben:widget_apk")).status_code, 302)

    def test_knopf_auf_kalenderseite(self):
        self.assertContains(self.client.get(reverse("kalender:jahr", args=[2027])), reverse("freigaben:widget"))
