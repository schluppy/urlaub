import json
from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from konten.models import Person
from orte.models import Ort
from reisen.models import Buchung, Etappe, Reise
from reisen.routing import vereinfachen

from .test_routing import ROUTE, Antwort

from .hilfen import fam

GEHEIM = "geheimer-tomtom-key"


class VereinfachenTest(TestCase):
    def test_gerade_schrumpft_ecke_bleibt(self):
        gerade = [(53.0 + i / 1000, 10.0) for i in range(500)]
        self.assertEqual(len(vereinfachen(gerade)), 2)
        ecke = gerade + [(53.499, 10.0 + i / 1000) for i in range(1, 500)]
        punkte = vereinfachen(ecke)
        self.assertEqual(len(punkte), 3)
        self.assertEqual(punkte[1], [53.499, 10.0])

    def test_kurz(self):
        self.assertEqual(vereinfachen([(1.123456, 2.0)]), [[1.12346, 2.0]])


ROUTE_MIT_LINIE = {**ROUTE, "routes": [{**ROUTE["routes"][0], "legs": [{"points": [
    {"latitude": 54.32260, "longitude": 10.1355}, {"latitude": 50.0, "longitude": 8.5},
    {"latitude": 47.7973, "longitude": 7.55037}]}]}]}


@override_settings(TOMTOM_API_KEY=GEHEIM)
class KarteTest(TestCase):
    def setUp(self):
        self.client.force_login(Person.objects.create_superuser("t@example.org", "T", familie=fam()))
        self.zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause", breite=Decimal("54.32260"),
                                          laenge=Decimal("10.1355"))
        self.rhein = Ort.objects.create(familie=fam(), name="Rheincamping", breite=Decimal("47.7973"), laenge=Decimal("7.55037"),
                                        website="https://rheincamping.example")
        self.ohne = Ort.objects.create(familie=fam(), name="Ohne Koordinaten")
        self.reise = Reise.objects.create(familie=fam(), titel="Sommerreise", von=date(2027, 8, 27), bis=date(2027, 8, 29))
        self.hin = Etappe.objects.create(reise=self.reise, datum=date(2027, 8, 27), startzeit=time(6),
                                         von_ort=self.zuhause, nach_ort=self.rhein, entfernung_km=Decimal(818),
                                         fahrzeit=timedelta(hours=9, minutes=25),
                                         routing_details={"laender": ["DEU"], "linie": [[54.32, 10.13], [50, 8.5],
                                                                                        [47.8, 7.55]]})
        Etappe.objects.create(reise=self.reise, datum=date(2027, 8, 29), von_ort=self.rhein, nach_ort=self.zuhause)
        Buchung.objects.create(reise=self.reise, ort=self.rhein, von=date(2027, 8, 27), bis=date(2027, 8, 29))

    def test_kartendaten_auf_der_reiseseite(self):
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk])).content.decode()
        self.assertIn('id="karte"', seite)
        self.assertIn("vendor/leaflet/leaflet.js", seite)
        self.assertIn('data-tomtom="/reise/kachel/tomtom/0/0/0.png"', seite)
        self.assertNotIn(GEHEIM, seite)
        daten = json.loads(seite.split('<script id="kartendaten" type="application/json">')[1].split("</script>")[0])
        self.assertEqual([o["name"] for o in daten["orte"]], ["Zuhause", "Rheincamping"])
        rhein = daten["orte"][1]
        self.assertEqual((rhein["typ"], rhein["website"], rhein["aufenthalte"]),
                         ("camping", "https://rheincamping.example", ["27.08.–29.08. (2 Nächte)"]))
        hin, rueck = daten["strecken"]
        self.assertEqual((hin["gerade"], len(hin["punkte"]), hin["text"]),
                         (False, 3, "27.08. Zuhause → Rheincamping · 818 km"))
        self.assertTrue(rueck["gerade"])          # noch ohne Route: Luftlinie

    def test_pdf_ohne_karte(self):
        antwort = self.client.get(reverse("reisen:pdf", args=[self.reise.pk]))
        self.assertTrue(antwort.content.startswith(b"%PDF"))
        from django.template.loader import render_to_string
        from reisen import dokumente
        from reisen.views import _kontext
        html = render_to_string("reisen/pdf.html", {**_kontext(dokumente.reise_laden(self.reise.pk, fam())), "schriften": ""})
        self.assertNotIn('id="karte"', html)

    def test_kachel_durchreichen(self):
        with mock.patch("reisen.routing.requests.get", return_value=mock.Mock(status_code=200, content=b"PNG")) as get:
            antwort = self.client.get(reverse("reisen:kachel", args=[9, 270, 164]))
        self.assertEqual((antwort.status_code, antwort["Content-Type"], antwort.content), (200, "image/png", b"PNG"))
        self.assertIn("private", antwort["Cache-Control"])
        self.assertTrue(get.call_args.args[0].endswith("/map/1/tile/basic/main/9/270/164.png"))
        self.assertEqual(get.call_args.kwargs["params"]["key"], GEHEIM)   # Key nur serverseitig

    def test_kachel_grenzen_und_fehler(self):
        self.assertEqual(self.client.get(reverse("reisen:kachel", args=[3, 8, 0])).status_code, 404)
        with mock.patch("reisen.routing.requests.get", return_value=mock.Mock(status_code=403, content=b"")):
            self.assertEqual(self.client.get(reverse("reisen:kachel", args=[3, 4, 2])).status_code, 502)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("reisen:kachel", args=[3, 4, 2])).status_code, 302)

    def test_routing_speichert_linie(self):
        from reisen.routing import etappe_routen
        with mock.patch("reisen.routing.requests.get", return_value=Antwort(200, ROUTE_MIT_LINIE)) as get:
            etappe_routen(self.hin)
        self.assertEqual(get.call_args.kwargs["params"]["routeRepresentation"], "polyline")
        self.hin.refresh_from_db()
        self.assertEqual(self.hin.routing_details["linie"][0], [54.32260, 10.1355])

    def test_routenlinien_aendert_nur_die_linie(self):
        Etappe.objects.filter(pk=self.hin.pk).update(routing_details={"laender": ["DEU"]})
        with mock.patch("reisen.routing.requests.get", return_value=Antwort(200, ROUTE_MIT_LINIE)):
            call_command("routenlinien", stdout=StringIO())
        self.hin.refresh_from_db()
        self.assertEqual((self.hin.entfernung_km, self.hin.fahrzeit), (Decimal(818), timedelta(hours=9, minutes=25)))
        self.assertEqual(self.hin.routing_details["laender"], ["DEU"])
        self.assertEqual(len(self.hin.routing_details["linie"]), 3)


class LuftlinienHinweisTest(TestCase):
    def test_hinweis_nur_bei_luftlinie(self):
        from reisen.views import kartendaten
        f = fam()
        a = Ort.objects.create(familie=f, name="A", breite=Decimal("54"), laenge=Decimal("10"))
        b = Ort.objects.create(familie=f, name="B", breite=Decimal("50"), laenge=Decimal("9"))
        r = Reise.objects.create(familie=f, titel="X", von=date(2027, 7, 1), bis=date(2027, 7, 2))
        e = Etappe.objects.create(reise=r, datum=r.von, von_ort=a, nach_ort=b)
        self.assertTrue(kartendaten(r)["luftlinie"])
        Etappe.objects.filter(pk=e.pk).update(routing_details={"linie": [[54, 10], [52, 9.5], [50, 9]]})
        self.assertFalse(kartendaten(Reise.objects.get(pk=r.pk))["luftlinie"])
