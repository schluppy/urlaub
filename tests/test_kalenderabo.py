from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from freigaben.ical import kalender
from freigaben.models import Kalenderabo
from konten.models import Familie, Person
from orte.models import Ort
from reisen.models import Buchung, Etappe, Reise

from .hilfen import fam


class HauptortTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.zuhause = Ort.objects.create(familie=self.f, name="Zuhause", typ="zuhause")
        self.stopp = Ort.objects.create(familie=self.f, name="Rastplatz", typ="zwischen")
        self.see = Ort.objects.create(familie=self.f, name="Seecamping", adresse="Seeweg 1, 79395 Neuenburg")
        self.berg = Ort.objects.create(familie=self.f, name="Bergcamping")
        self.faehre = Ort.objects.create(familie=self.f, name="Fährhafen", typ="faehre")
        self.r = Reise.objects.create(familie=self.f, titel="Sommer", von=date(2027, 8, 1), bis=date(2027, 8, 20))

    def buchung(self, ort, von, bis, status="gebucht"):
        Buchung.objects.create(reise=self.r, ort=ort, von=date(2027, 8, von), bis=date(2027, 8, bis), status=status)

    def test_meiste_naechte_ohne_zwischenstopp_und_faehre(self):
        self.buchung(self.stopp, 1, 2)
        self.buchung(self.faehre, 2, 12)        # viele Nächte, zählt aber nicht
        self.buchung(self.berg, 12, 15)
        self.buchung(self.see, 15, 19)
        self.assertEqual(self.r.hauptort, self.see)

    def test_mehrere_aufenthalte_am_selben_ort_zaehlen_zusammen(self):
        self.buchung(self.see, 1, 3)
        self.buchung(self.berg, 3, 6)
        self.buchung(self.see, 6, 8)            # Seecamping 2 + 2 = 4 > Bergcamping 3
        self.assertEqual(self.r.hauptort, self.see)

    def test_stornierte_zaehlen_nicht_gleichstand_erster(self):
        self.buchung(self.see, 1, 9, status="storniert")
        self.buchung(self.berg, 9, 12)
        self.buchung(self.see, 12, 15)
        self.assertEqual(self.r.hauptort, self.berg)

    def test_ohne_buchungen_aus_etappen_und_sonst_keiner(self):
        self.assertIsNone(self.r.hauptort)
        Etappe.objects.create(reise=self.r, datum=date(2027, 8, 1), von_ort=self.zuhause, nach_ort=self.stopp)
        Etappe.objects.create(reise=self.r, datum=date(2027, 8, 2), von_ort=self.stopp, nach_ort=self.berg)
        Etappe.objects.create(reise=self.r, datum=date(2027, 8, 20), von_ort=self.berg, nach_ort=self.zuhause)
        self.assertEqual(self.r.hauptort, self.berg)


class IcalTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.see = Ort.objects.create(familie=self.f, name="Seecamping; am Rhein", adresse="Seeweg 1, 79395 Neuenburg",
                                      breite=Decimal("47.8"), laenge=Decimal("7.55"))
        self.r = Reise.objects.create(familie=self.f, titel="Sommer, Sonne", urlaub_von=date(2027, 8, 25),
                                      urlaub_bis=date(2027, 9, 20), von=date(2027, 8, 27), bis=date(2027, 9, 19))
        Buchung.objects.create(reise=self.r, ort=self.see, von=date(2027, 8, 27), bis=date(2027, 9, 19))
        Reise.objects.create(familie=self.f, titel="Nur Alternative", von=date(2027, 10, 1), bis=date(2027, 10, 3),
                             im_kalender=False)
        Reise.objects.create(familie=Familie.objects.create(name="Andere", bundesland="BY"), titel="Fremdreise",
                             von=date(2027, 7, 1), bis=date(2027, 7, 3))

    def test_termin(self):
        ics = kalender(self.f)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n"))
        entfaltet = ics.replace("\r\n ", "")
        self.assertIn("DTSTART;VALUE=DATE:20270825\r\n", entfaltet)       # Urlaubsbeginn, nicht Reisebeginn
        self.assertIn("DTEND;VALUE=DATE:20270921\r\n", entfaltet)         # Ende exklusiv: Tag nach dem Urlaub
        self.assertIn("SUMMARY:Sommer\\, Sonne\r\n", entfaltet)
        self.assertIn("LOCATION:Seecamping\\; am Rhein\\, Seeweg 1\\, 79395 Neuenburg\r\n", entfaltet)
        self.assertIn("GEO:47.800000;7.550000", entfaltet)
        self.assertIn(f"UID:reise-{self.r.pk}@", entfaltet)
        self.assertIn("Unterwegs 27.08. – 19.09.2027", entfaltet)
        self.assertIn(f"/reise/{self.r.pk}/", entfaltet)
        self.assertEqual(entfaltet.count("BEGIN:VEVENT"), 1)               # keine Alternative, keine fremde Familie
        self.assertNotIn("Fremdreise", entfaltet)

    def test_zeilen_hoechstens_75_byte(self):
        self.r.titel = "Ä" * 120
        self.r.save()
        for zeile in kalender(self.f).split("\r\n"):
            self.assertLessEqual(len(zeile.encode("utf-8")), 75, zeile)


class AboTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=self.f, is_staff=True)
        Reise.objects.create(familie=self.f, titel="Sommer", von=date(2027, 8, 1), bis=date(2027, 8, 10))
        self.client.force_login(self.anna)

    def test_erzeugen_abrufen_neu_beenden(self):
        self.assertContains(self.client.get(reverse("freigaben:abo")), "Abo-Link erzeugen")
        self.client.post(reverse("freigaben:abo"), {"aktion": "erzeugen"})
        abo = Kalenderabo.objects.get()
        self.assertContains(self.client.get(reverse("freigaben:abo")), abo.link)
        self.client.logout()
        feed = self.client.get(reverse("freigaben:abo_feed", args=[abo.token]))
        self.assertEqual((feed.status_code, feed["Content-Type"]), (200, "text/calendar; charset=utf-8"))
        self.assertIn(b"SUMMARY:Sommer", feed.content)
        abo.refresh_from_db()
        self.assertEqual(abo.abrufe, 1)
        self.assertTrue(abo.webcal.startswith("webcal://"))
        # neuer Link ersetzt den alten
        self.client.force_login(self.anna)
        self.client.post(reverse("freigaben:abo"), {"aktion": "erzeugen"})
        neu = Kalenderabo.objects.filter(beendet_am__isnull=True).get()
        self.assertNotEqual(neu.token, abo.token)
        self.assertEqual(self.client.get(reverse("freigaben:abo_feed", args=[abo.token])).status_code, 404)
        # beenden
        self.client.post(reverse("freigaben:abo"), {"aktion": "beenden"})
        self.assertEqual(self.client.get(reverse("freigaben:abo_feed", args=[neu.token])).status_code, 404)

    def test_gesperrte_person_und_unbekannter_link(self):
        abo = Kalenderabo.objects.create(person=self.anna)
        self.anna.is_active = False
        self.anna.save()
        self.assertEqual(self.client.get(reverse("freigaben:abo_feed", args=[abo.token])).status_code, 404)
        self.assertEqual(self.client.get(reverse("freigaben:abo_feed", args=["gibt-es-nicht"])).status_code, 404)

    def test_knopf_auf_kalenderseite(self):
        self.assertContains(self.client.get(reverse("kalender:jahr", args=[2027])), reverse("freigaben:abo"))
