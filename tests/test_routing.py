from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from fahrzeuge.models import Fahrzeugprofil
from konten.models import Person
from orte.models import Ort
from reisen.models import Etappe, Reise
from reisen.routing import TomTomFehler, berechne_route, fahrzeug_parameter

from .hilfen import fam


class Antwort:
    def __init__(self, status, daten):
        self.status_code, self._daten = status, daten

    def json(self):
        return self._daten


ROUTE = {"routes": [{"summary": {"lengthInMeters": 818123, "travelTimeInSeconds": 31140,
                                 "trafficDelayInSeconds": 600},
                     "sections": [{"sectionType": "COUNTRY", "countryCode": "DEU"},
                                  {"sectionType": "COUNTRY", "countryCode": "CHE"},
                                  {"sectionType": "TOLL_VIGNETTE", "countryCode": "CHE"}]}],
         "report": {"effectiveSettings": [{"key": "vehicleLength", "value": "12.50"},
                                          {"key": "travelMode", "value": "bus"},
                                          {"key": "key", "value": "geheim"}]}}
GEO = {"results": [{"type": "Point Address", "position": {"lat": 54.32260, "lon": 10.1355},
                    "address": {"freeformAddress": "Rathausplatz 1, 24103 Kiel", "countryCode": "DE"}}]}


@override_settings(TOMTOM_API_KEY="test")
class RoutingTest(TestCase):
    def setUp(self):
        self.profil = Fahrzeugprofil.objects.create(familie=fam(), name="Gespann", laenge_m=Decimal("12.5"), breite_m=None,
                                                    hoechstgeschwindigkeit_kmh=100)

    def test_fahrzeug_parameter_ohne_leere_felder(self):
        p = fahrzeug_parameter(self.profil)
        self.assertEqual(p, {"vehicleLength": Decimal("12.50"), "vehicleMaxSpeed": 100})

    @mock.patch("reisen.routing.requests.post", return_value=Antwort(200, ROUTE))
    def test_route_auswerten(self, post):
        abfahrt = timezone.make_aware(datetime.combine(date.today() + timedelta(days=30), time(6)))
        r = berechne_route((53.7, 9.6), (47.8, 7.5), self.profil, abfahrt, vignetten_meiden="aut, ")
        self.assertEqual(r.entfernung_km, Decimal("818.1"))
        self.assertEqual(r.fahrzeit, timedelta(hours=8, minutes=39))
        self.assertEqual(r.laender, ["DEU", "CHE"])
        self.assertEqual(r.vignetten, ["CHE"])
        self.assertNotIn("key", r.wirksam)
        params = post.call_args.kwargs["params"]
        self.assertEqual(params["travelMode"], "bus")
        self.assertEqual(post.call_args.kwargs["json"], {"avoidVignette": ["AUT"]})
        self.assertTrue(params["departAt"].endswith("T06:00:00"))

    @mock.patch("reisen.routing.requests.get", return_value=Antwort(200, ROUTE))
    def test_vergangene_abfahrt_ohne_departat(self, get):
        abfahrt = timezone.make_aware(datetime(2020, 1, 1, 6))
        berechne_route((53.7, 9.6), (47.8, 7.5), abfahrt=abfahrt)
        params = get.call_args.kwargs["params"]  # ohne Vignetten-Vorgabe per GET
        self.assertNotIn("departAt", params)
        self.assertEqual(params["traffic"], "false")

    @mock.patch("reisen.routing.requests.get",
                return_value=Antwort(400, {"detailedError": {"message": "Unable to find a route"}}))
    def test_fehler_400(self, get):
        with self.assertRaisesMessage(TomTomFehler, "befahrbaren Straße"):
            berechne_route((0, 0), (1, 1))
        with self.assertRaisesMessage(TomTomFehler, "(TomTom: Unable to find a route)"):
            berechne_route((0, 0), (1, 1))

    @override_settings(TOMTOM_API_KEY="")
    def test_ohne_schluessel(self):
        with self.assertRaisesMessage(TomTomFehler, "TOMTOM_API_KEY"):
            berechne_route((0, 0), (1, 1))


@override_settings(TOMTOM_API_KEY="test")
class AdminTest(TestCase):
    def setUp(self):
        self.client.force_login(Person.objects.create_superuser("t@example.org", "T", familie=fam()))
        self.zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause", adresse="Rathausplatz 1, Kiel")
        self.platz = Ort.objects.create(familie=fam(), name="Rheincamping", breite=Decimal("47.797"), laenge=Decimal("7.550"))
        self.reise = Reise.objects.create(familie=fam(), titel="Italien", von=date(2026, 8, 21), bis=date(2026, 9, 6))
        Etappe.objects.create(reise=self.reise, datum=date(2026, 8, 21), startzeit=time(6),
                              von_ort=self.zuhause, nach_ort=self.platz)

    def test_route_aktualisieren(self):
        with mock.patch("reisen.routing.requests.get", side_effect=[Antwort(200, GEO), Antwort(200, ROUTE)]):
            antwort = self.client.post(reverse("admin:reisen_reise_route", args=[self.reise.pk]), follow=True)
        e = Etappe.objects.get()
        self.assertEqual(e.entfernung_km, Decimal("818.1"))
        self.assertIsNotNone(e.routing_stand)
        self.assertEqual(e.routing_details["vignetten"], ["CHE"])
        self.zuhause.refresh_from_db()
        self.assertEqual(self.zuhause.breite, Decimal("54.322600"))
        self.assertContains(antwort, "1 Etappe mit TomTom berechnet")
        self.assertContains(antwort, "Route aktualisieren")

    def test_get_rechnet_nicht(self):
        with mock.patch("reisen.routing.requests.get") as get, mock.patch("reisen.routing.requests.post") as post:
            self.client.get(reverse("admin:reisen_reise_route", args=[self.reise.pk]))
        get.assert_not_called()
        post.assert_not_called()

    def test_ort_speichern_geocodiert(self):
        with mock.patch("reisen.routing.requests.get", return_value=Antwort(200, GEO)):
            self.client.post(reverse("admin:orte_ort_add"), {
                "name": "Neu", "typ": "camping", "adresse": "Irgendwo 1", "land": "", "website": "",
                "breite": "", "laenge": "", "preise": "", "notizen": ""})
        ort = Ort.objects.get(name="Neu")
        self.assertEqual(ort.laenge, Decimal("10.135500"))
        self.assertEqual(ort.land, "DE")
