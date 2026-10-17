import json
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from freigaben.models import Freigabe
from konten.models import Person
from orte.models import Ort
from reisen.models import Buchung, Etappe, Reise

from .hilfen import fam


class OrteTest(TestCase):
    def setUp(self):
        self.familie = fam()
        self.client.force_login(Person.objects.create_user("t@example.org", "T", familie=self.familie, is_staff=True))
        self.zuhause = Ort.objects.create(familie=self.familie, name="Zuhause", typ="zuhause",
                                          breite=Decimal("54.3226"), laenge=Decimal("10.1355"))
        self.see = Ort.objects.create(familie=self.familie, name="Seecamping", bewertung=5,
                                      breite=Decimal("47.8"), laenge=Decimal("7.55"))
        self.stopp = Ort.objects.create(familie=self.familie, name="Rastplatz am Rhein", typ="zwischen", bewertung=3,
                                        breite=Decimal("49.0"), laenge=Decimal("8.4"))
        for jahr, status in [(2025, "bezahlt"), (2026, "bezahlt"), (2027, "storniert")]:
            r = Reise.objects.create(familie=self.familie, titel=f"Reise {jahr}", von=date(jahr, 8, 1), bis=date(jahr, 8, 10))
            Buchung.objects.create(reise=r, ort=self.see, von=date(jahr, 8, 2), bis=date(jahr, 8, 9), status=status)
        self.reise = r

    def test_sterne(self):
        self.assertEqual((self.see.sterne, self.stopp.sterne, self.zuhause.sterne), ("★★★★★", "★★★☆☆", ""))

    def test_liste_mit_aufenthalten_und_zuletzt(self):
        seite = self.client.get(reverse("admin:orte_ort_changelist")).content.decode()
        zeile = seite[seite.index("Seecamping"):][:900]
        self.assertIn("★★★★★", zeile)
        self.assertIn('<td class="field-aufenthalte">2</td>', zeile)          # stornierte Buchung zählt nicht
        self.assertIn('<td class="field-zuletzt">09.08.2026</td>', zeile)
        self.assertIn("Zwischenübernachtung", seite)

    def test_filtern_und_sortieren(self):
        seite = self.client.get(reverse("admin:orte_ort_changelist"), {"bewertung__exact": 5}).content.decode()
        self.assertIn("Seecamping", seite)
        self.assertNotIn("Rastplatz am Rhein", seite)
        seite = self.client.get(reverse("admin:orte_ort_changelist"), {"typ__exact": "zwischen"}).content.decode()
        self.assertIn("Rastplatz am Rhein", seite)
        self.assertNotIn("Seecamping", seite)
        sortiert = self.client.get(reverse("admin:orte_ort_changelist"), {"o": "-3"})   # nach Bewertung absteigend
        self.assertEqual(sortiert.status_code, 200)

    def test_anlegen_mit_sternen(self):
        antwort = self.client.post(reverse("admin:orte_ort_add"), {
            "name": "Neuer Stopp", "typ": "zwischen", "bewertung": "4", "adresse": "", "land": "", "website": "",
            "breite": "50", "laenge": "8", "preise": "", "notizen": ""})
        self.assertEqual(antwort.status_code, 302)
        ort = Ort.objects.get(name="Neuer Stopp")
        self.assertEqual((ort.typ, ort.bewertung, ort.familie), ("zwischen", 4, self.familie))
        formular = self.client.get(reverse("admin:orte_ort_change", args=[ort.pk])).content.decode()
        self.assertIn('type="radio" name="bewertung" value="5"', formular)

    def test_sterne_auf_reiseseite_nicht_im_geteilten_link(self):
        r = Reise.objects.create(familie=self.familie, titel="Sommer", von=date(2027, 9, 1), bis=date(2027, 9, 3))
        Etappe.objects.create(reise=r, datum=r.von, von_ort=self.zuhause, nach_ort=self.see)
        Buchung.objects.create(reise=r, ort=self.see, von=r.von, bis=r.bis)
        seite = self.client.get(reverse("reisen:reise", args=[r.pk])).content.decode()
        self.assertIn("★★★★★", seite)
        daten = json.loads(seite.split('<script id="kartendaten" type="application/json">')[1].split("</script>")[0])
        self.assertEqual(daten["orte"][1]["sterne"], "★★★★★")
        f = Freigabe.objects.create(familie=self.familie, art="reise", reise=r, gueltig_bis=date.today() + timedelta(days=1))
        self.client.logout()
        oeffentlich = self.client.get(reverse("freigaben:ansehen", args=[f.token])).content.decode()
        self.assertNotIn("★", oeffentlich)


GOOGLE_LANG = ("https://www.google.com/maps/place/Faehrhafen/@50.1110033,-3.2225803,17z/data=!3m1!4b1!4m6!3m5"
               "!1s0x0:0x0!8m2!3d50.111!4d-3.22!16s%2Fg%2F11x?entry=tts")


class GoogleKoordinatenTest(TestCase):
    def test_lesen(self):
        from unittest import mock

        from orte.google import KeineKoordinaten, koordinaten

        D = Decimal
        self.assertEqual(koordinaten(GOOGLE_LANG), (D("50.111000"), D("-3.220000")))          # Stecknadel, nicht @
        self.assertEqual(koordinaten("https://www.google.de/maps/@47.1234567,8.7654321,15z"),
                         (D("47.123457"), D("8.765432")))                                       # nur Kartenmitte
        self.assertEqual(koordinaten("https://maps.google.com/?q=47.5,-3.25"), (D("47.5"), D("-3.25")))
        self.assertEqual(koordinaten("50.1110033, -3.2225803"), (D("50.111003"), D("-3.222580")))
        self.assertEqual(koordinaten("50.1110033 -3.2225803"), (D("50.111003"), D("-3.222580")))
        with mock.patch("orte.google.requests.get") as get:
            get.return_value = mock.Mock(status_code=302, headers={"Location": GOOGLE_LANG})
            self.assertEqual(koordinaten("https://maps.app.goo.gl/AbCdEf123"), (D("50.111"), D("-3.22")))
            get.assert_called_once()
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        for falsch in ["https://example.org/@52.1,6.2,3z", "irgendwas", "https://www.google.com/maps",
                       "95.0, 10.0"]:
            with self.subTest(falsch), self.assertRaises(KeineKoordinaten):
                koordinaten(falsch)
        with mock.patch("orte.google.requests.get") as get:                 # lange Adressen werden nie abgerufen
            koordinaten(GOOGLE_LANG)
            get.assert_not_called()


class OrtKoordinatenEingabeTest(TestCase):
    def setUp(self):
        self.familie = fam()
        self.client.force_login(Person.objects.create_user("t@example.org", "T", familie=self.familie, is_staff=True))
        self.ort = Ort.objects.create(familie=self.familie, name="Hafen", typ="faehre", adresse="Hafenstraße 1")

    def senden(self, **felder):
        daten = {"name": "Hafen", "typ": "faehre", "bewertung": "", "adresse": "Hafenstraße 1", "land": "",
                 "website": "", "breite": "", "laenge": "", "google": "", "preise": "", "notizen": "", **felder}
        return self.client.post(reverse("admin:orte_ort_change", args=[self.ort.pk]), daten)

    def test_von_hand_mit_sieben_stellen_und_komma(self):
        from unittest import mock

        with mock.patch("orte.admin.ort_geocodieren") as tomtom:
            self.assertEqual(self.senden(breite="50,1110033", laenge="-3.2225803").status_code, 302)
            tomtom.assert_not_called()
        self.ort.refresh_from_db()
        self.assertEqual((self.ort.breite, self.ort.laenge), (Decimal("50.111003"), Decimal("-3.222580")))

    def test_google_link_geht_vor_tomtom_und_handeingabe(self):
        from unittest import mock

        with mock.patch("orte.admin.ort_geocodieren") as tomtom:
            antwort = self.senden(google=GOOGLE_LANG, adresse="Neue Adresse 2", breite="1", laenge="2")
            self.assertEqual(antwort.status_code, 302)
            tomtom.assert_not_called()                                   # trotz geänderter Adresse
        self.ort.refresh_from_db()
        self.assertEqual((self.ort.breite, self.ort.laenge), (Decimal("50.111"), Decimal("-3.22")))

    def test_fehler_bleiben_im_formular(self):
        self.assertContains(self.senden(google="https://example.org/x"), "Das ist kein Link aus Google Maps.")
        self.assertContains(self.senden(breite="52.1"), "Bitte Breite und Länge eintragen")
