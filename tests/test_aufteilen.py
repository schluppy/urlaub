from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from konten.models import Person
from orte.models import Ort
from reisen.models import Etappe, Reise
from reisen.routing import abschnitt, punkt_nach

from .hilfen import fam

# 13 Punkte von Nord nach Süd, je Punkt 1 h und 100 km – 12 h und 1.200 km insgesamt
PUNKTE = [{"latitude": 54 - i * 0.9, "longitude": 10.0} for i in range(13)]
ROUTE = {"routes": [{"summary": {"lengthInMeters": 1200000, "travelTimeInSeconds": 43200},
                     "legs": [{"points": PUNKTE}],
                     "progress": [{"pointIndex": i, "travelTimeInSeconds": i * 3600, "distanceInMeters": i * 100000}
                                  for i in range(13)]}]}


class Antwort:
    def __init__(self, daten):
        self.status_code, self._daten = 200, daten

    def json(self):
        return self._daten


def tomtom(url, params=None, timeout=None):
    if "calculateRoute" in url:
        return Antwort(ROUTE)
    lat = float(url.split("reverseGeocode/")[1].split(",")[0])
    return Antwort({"addresses": [{"address": {
        "municipality": f"Ort{lat:.2f}", "countrySecondarySubdivision": "Kreis", "country": "Frankreich",
        "countryCode": "FR", "freeformAddress": f"Hauptstraße 1, Ort{lat:.2f}"}}]})


class VerlaufTest(TestCase):
    VERLAUF = [(54.0, 10.0, 0, 0), (53.0, 10.0, 3600, 100000), (52.0, 10.0, 7200, 200000)]

    def test_punkt_nach_zwischen_zwei_punkten(self):
        self.assertEqual(punkt_nach(self.VERLAUF, 5400), (52.5, 10.0, 150000))
        self.assertEqual(punkt_nach(self.VERLAUF, 0), (54.0, 10.0, 0))
        self.assertEqual(punkt_nach(self.VERLAUF, 99999), (52.0, 10.0, 200000))   # hinter dem Ziel: Ziel

    def test_abschnitt(self):
        self.assertEqual(abschnitt(self.VERLAUF, 1800, 5400), [[53.5, 10.0], [52.5, 10.0]])


@override_settings(TOMTOM_API_KEY="test")
@mock.patch("reisen.routing.requests.get", side_effect=tomtom)
class AufteilenTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(Person.objects.create_superuser("t@example.org", "T", familie=fam()))
        zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause", breite=Decimal("54"), laenge=Decimal("10"))
        self.ziel = Ort.objects.create(familie=fam(), name="Strandcamping", breite=Decimal("43.2"), laenge=Decimal("10"))
        self.reise = Reise.objects.create(familie=fam(), titel="Süden", von=date(2028, 8, 25), bis=date(2028, 9, 17))
        self.etappe = Etappe.objects.create(reise=self.reise, datum=date(2028, 8, 25), von_ort=zuhause,
                                            nach_ort=self.ziel, startzeit=time(6), pause=timedelta(hours=2),
                                            fahrzeit=timedelta(hours=12), entfernung_km=Decimal(1200))
        self.url = reverse("reisen:aufteilen", args=[self.reise.pk, self.etappe.pk])

    def berechnen(self, **werte):
        return self.client.get(self.url, {"start": "06:00", "fahrzeit": "10:00", "pause": "02:00", **werte})

    def test_link_nur_bei_langen_etappen(self, get):
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
        self.assertContains(seite, self.url)
        Etappe.objects.filter(pk=self.etappe.pk).update(fahrzeit=timedelta(hours=7))
        self.assertNotContains(self.client.get(reverse("reisen:reise", args=[self.reise.pk])), self.url)

    def test_formular_vorbelegt_ohne_abruf(self, get):
        seite = self.client.get(self.url)
        self.assertContains(seite, 'value="06:00"')   # Start der Etappe
        self.assertContains(seite, 'value="02:00"')   # Pause der Etappe
        self.assertNotContains(seite, "Platz gefunden?")
        self.assertNotContains(seite, "leaflet.js")
        get.assert_not_called()

    def test_haltepunkt(self, get):
        seite = self.berechnen()
        self.assertContains(seite, "1.000 km")                  # nach 10 h
        self.assertContains(seite, "18:00")                     # 6:00 + 10 h + 2 h Pause
        self.assertContains(seite, "200 km")                    # Rest
        self.assertContains(seite, "2:00 h")                    # Restfahrzeit
        self.assertContains(seite, "Ort45.00, Kreis, Frankreich")
        self.assertContains(seite, "zwischen <b>Ort45.45</b> und\n    <b>Ort44.55</b>")   # ± 30 Min.
        self.assertContains(seite, "https://www.google.com/maps/search/Campingplatz/@45.00000,10.00000,11z")
        params = get.call_args_list[0].kwargs["params"]
        self.assertEqual(params["extendedRouteRepresentation"], ["travelTime", "distance"])
        self.assertEqual(params["departAt"], "2028-08-25T06:00:00")
        self.assertEqual(self.client.session["aufteilen_fahrzeit"], "10:00")
        # gleiche Eingaben, andere Pause: aus dem Cache, ohne neuen Abruf
        anzahl = get.call_count
        self.assertContains(self.berechnen(pause="01:00"), "17:00")
        self.assertEqual(get.call_count, anzahl)

    def test_fahrzeit_laenger_als_etappe(self, get):
        self.assertContains(self.berechnen(fahrzeit="13:00"), "nichts aufzuteilen")

    def test_teilen_mit_neuem_platz(self, get):
        antwort = self.client.post(self.url, {"start": "06:00", "fahrzeit": "10:00", "pause": "02:00",
                                              "name": "Camping am See", "google": "45.01, 10.02", "weiter_um": "08:00",
                                              "website": "camping-am-see.example"})
        ort = Ort.objects.get(name="Camping am See")
        self.assertEqual((ort.typ, ort.land, ort.familie, ort.website),
                         ("zwischen", "FR", fam(), "https://camping-am-see.example"))
        erste, zweite = self.reise.etappen.all()
        self.assertEqual((erste.von_ort.name, erste.nach_ort, erste.entfernung_km), ("Zuhause", ort, Decimal("1200.0")))
        self.assertEqual((zweite.datum, zweite.startzeit, zweite.von_ort, zweite.nach_ort, zweite.pause),
                         (date(2028, 8, 26), time(8), ort, self.ziel, timedelta(hours=2)))
        # zweite Etappe ist (laut Testroute) wieder lang → gleich weiter aufteilen
        self.assertRedirects(antwort, reverse("reisen:aufteilen", args=[self.reise.pk, zweite.pk]))

    def test_teilen_mit_vorhandenem_ort(self, get):
        nah = Ort.objects.create(familie=fam(), name="Platz in der Nähe", typ="zwischen",
                                 breite=Decimal("45.1"), laenge=Decimal("10.1"))
        Ort.objects.create(familie=fam(), name="Weit weg", breite=Decimal("50"), laenge=Decimal("10"))
        seite = self.berechnen()
        self.assertContains(seite, "Platz in der Nähe (14 km)")
        self.assertNotContains(seite, "Weit weg (")
        self.client.post(self.url, {"start": "06:00", "fahrzeit": "10:00", "pause": "02:00",
                                    "ort": nah.pk, "weiter_um": "08:30"})
        self.assertEqual([e.nach_ort for e in self.reise.etappen.all()], [nah, self.ziel])
        self.assertContains(self.berechnen(), 'name="weiter_um" value="08:30"')   # zuletzt gewählt

    def test_teilen_ohne_angaben(self, get):
        seite = self.client.post(self.url, {"start": "06:00", "fahrzeit": "10:00", "pause": "", "weiter_um": "08:00"})
        self.assertContains(seite, "Namen des Platzes eintragen")
        self.assertContains(seite, "Link oder Koordinaten aus Google Maps einfügen")
        self.assertEqual(self.reise.etappen.count(), 1)

    def test_fremde_familie(self, get):
        fremd = Reise.objects.create(familie=fam("Andere"), titel="X", von=date(2028, 1, 1), bis=date(2028, 1, 2))
        self.assertEqual(self.client.get(reverse("reisen:aufteilen", args=[fremd.pk, self.etappe.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("reisen:aufteilen", args=[self.reise.pk, 999])).status_code, 404)
