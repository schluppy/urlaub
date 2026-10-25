import gzip
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from freigaben.models import Widgetzugang
from konten.models import Person
from orte.models import Ort
from reisen import gpx
from reisen.models import Etappe, Reise, Track

from .hilfen import fam


def gpx_text(segmente, name="Fahrt Sa. 24.10. 16:37"):
    """segmente: [[(\"2026-10-24T14:37:00Z\", lat, lon), …], …]"""
    teile = "".join(
        "<trkseg>" + "".join(f'<trkpt lat="{lat}" lon="{lon}"><ele>4.0</ele><time>{t}</time></trkpt>' for t, lat, lon in s)
        + "</trkseg>" for s in segmente)
    return (f'<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
            f"<trk><name>{name}</name>{teile}</trk></gpx>").encode()


# Zwei Teilstücke mit einer Minute Pause, etwa 1,1 km und 1,1 km nach Norden
FAHRT = gpx_text([
    [("2026-10-24T14:37:00Z", 54.30, 10.13), ("2026-10-24T14:38:00Z", 54.305, 10.13), ("2026-10-24T14:39:00Z", 54.31, 10.13)],
    [("2026-10-24T14:40:00Z", 54.31, 10.13), ("2026-10-24T14:42:00Z", 54.32, 10.13)],
])


class LesenTest(TestCase):
    def test_kennzahlen_ohne_pause_zwischen_den_segmenten(self):
        name, segmente = gpx.lesen(FAHRT)
        werte = gpx.kennzahlen(segmente)
        self.assertEqual(name, "Fahrt Sa. 24.10. 16:37")
        self.assertEqual(werte["entfernung_km"], Decimal("2.2"))
        self.assertEqual(werte["fahrzeit"], timedelta(minutes=4))
        self.assertEqual(werte["linie"][0], [54.30, 10.13])
        self.assertEqual(werte["linie"][-1], [54.32, 10.13])

    def test_statistik(self):
        s = gpx.kennzahlen(gpx.lesen(FAHRT)[1])["statistik"]
        self.assertEqual((s["meter"], s["dauer_s"]), (2224, 300))      # Aufzeichnung samt Pause zwischen den Segmenten
        self.assertEqual(s["bewegung_s"], 240)
        self.assertAlmostEqual(s["hoechst_kmh"], 33.4, delta=0.1)
        self.assertEqual(s["hoehe"], {"min": 4, "max": 4, "anstieg": 0, "abstieg": 0})
        self.assertEqual(s["reihe"][0], [0, 0.0, 0.0, 4, 54.3, 10.13])
        self.assertEqual(s["reihe"][-1][:3], [300, 2.22, 0.0])

    def test_stillstand_und_hoehe(self):
        t0 = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        # 2 Minuten Stand mit zitternder Position und Höhe, dann anderthalb Minuten mit 60 km/h 40 m hinauf und 30 m hinab
        stand = [(t0 + timedelta(seconds=i), 54.3 + (i % 2) * 0.00003, 10.13, 40 + (i % 3)) for i in range(120)]
        fahrt = [(t0 + timedelta(seconds=120 + i), 54.3 + i * 0.00015, 10.13, 40 + 2 * min(i, 20) - 1.5 * min(max(0, i - 40), 20))
                 for i in range(91)]
        s = gpx.statistik([stand + fahrt])
        self.assertEqual(s["bewegung_s"], 90)
        self.assertAlmostEqual(s["hoechst_kmh"], 60, delta=1)
        self.assertAlmostEqual(s["hoehe"]["anstieg"], 40, delta=4)   # über 10 s gemittelt, das Zittern im Stand zählt nicht
        self.assertAlmostEqual(s["hoehe"]["abstieg"], 30, delta=4)
        ohne = gpx.statistik([[(p[0], p[1], p[2], None) for p in fahrt]])
        self.assertIsNone(ohne["hoehe"])
        self.assertIsNone(ohne["reihe"][1][3])

    def test_gzip_und_kaputte_dateien(self):
        self.assertEqual(gpx.entpacken(gzip.compress(FAHRT)), FAHRT)
        for daten in (b"kein xml", b"<gpx></gpx>", b"\x1f\x8bkaputt",
                      b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaa">]><gpx>&a;</gpx>'):
            with self.assertRaises(gpx.GpxFehler):
                gpx.lesen(gpx.entpacken(daten))


class HochladenTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.anna = Person.objects.create_user("anna@example.org", familie=self.f)
        self.zugang = Widgetzugang.objects.create(person=self.anna)
        self.herbst = Reise.objects.create(familie=self.f, titel="Herbst", von=date(2026, 10, 24), bis=date(2026, 11, 1))
        self.sommer = Reise.objects.create(familie=self.f, titel="Sommer", von=date(2026, 7, 1), bis=date(2026, 7, 20))
        self.winter = Reise.objects.create(familie=self.f, titel="Winter", von=date(2026, 12, 20), bis=date(2027, 1, 2),
                                           im_kalender=False)

    def url(self, reise, token=None):
        return reverse("freigaben:tracking_hochladen", args=[token or self.zugang.token, reise.pk])

    def test_reisen_zeitlich_naechste_zuerst(self):
        antwort = self.client.get(reverse("freigaben:tracking_reisen", args=[self.zugang.token]), {"datum": "2026-11-20"})
        self.assertEqual([r["titel"] for r in antwort.json()["reisen"]], ["Herbst", "Winter (Alternative)", "Sommer"])
        self.assertEqual(antwort.json()["reisen"][0]["id"], self.herbst.pk)

    def test_hochladen_gzip_und_ersetzen(self):
        antwort = self.client.post(self.url(self.herbst), gzip.compress(FAHRT), content_type="application/gzip")
        self.assertEqual(antwort.status_code, 201)
        self.assertEqual(antwort.json(), {"reise": "Herbst", "km": 2.2, "ersetzt": False, "etappe": None})
        antwort = self.client.post(self.url(self.herbst), FAHRT, content_type="application/gpx+xml")
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort.json()["ersetzt"])
        track = Track.objects.get()
        self.assertEqual(track.reise, self.herbst)
        self.assertIn("<trkseg>", track.gpx)

    def test_fehler(self):
        self.assertEqual(self.client.post(self.url(self.herbst), b"Unsinn", content_type="text/plain").status_code, 400)
        self.assertEqual(self.client.post(self.url(self.herbst, token="falsch"), FAHRT, content_type="text/xml").status_code, 404)
        andere = fam("Andere")
        fremd = Reise.objects.create(familie=andere, titel="Fremd", von=date(2026, 10, 24), bis=date(2026, 10, 25))
        self.assertEqual(self.client.post(self.url(fremd), FAHRT, content_type="text/xml").status_code, 404)
        self.zugang.beenden()
        self.assertEqual(self.client.post(self.url(self.herbst), FAHRT, content_type="text/xml").status_code, 404)
        self.assertFalse(Track.objects.exists())


class RouteAusGpxTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.anna = Person.objects.create_user("anna@example.org", familie=self.f)
        self.client.force_login(self.anna)
        ort = lambda name, b, l: Ort.objects.create(familie=self.f, name=name, breite=Decimal(b), laenge=Decimal(l))
        self.zuhause, self.hafen, self.camp = ort("Zuhause", "54.30", "10.13"), ort("Hafen", "54.32", "10.13"), ort("Camp", "54.5", "9.0")
        self.reise = Reise.objects.create(familie=self.f, titel="Herbst", von=date(2026, 10, 24), bis=date(2026, 11, 1))
        tag = date(2026, 10, 24)
        self.zur_faehre = Etappe.objects.create(
            reise=self.reise, datum=tag, von_ort=self.zuhause, nach_ort=self.hafen, entfernung_km=Decimal("3.0"),
            fahrzeit=timedelta(minutes=9), routing_details={"laender": ["DE"], "verbrauch_l": "1.0", "linie": [[1, 1], [2, 2]]})
        self.weiter = Etappe.objects.create(reise=self.reise, datum=tag, von_ort=self.hafen, nach_ort=self.camp,
                                            entfernung_km=Decimal("90.0"))
        self.seite = reverse("reisen:reise", args=[self.reise.pk])

    def test_ohne_track_nur_tomtom(self):
        seite = self.client.get(self.seite)
        self.assertContains(seite, "Route aktualisieren")
        self.assertNotContains(seite, 'value="gpx"')

    def test_gpx_ersetzt_die_passende_etappe(self):
        gpx.speichern(self.reise, FAHRT)
        self.assertContains(self.client.get(self.seite), 'value="gpx"')
        antwort = self.client.post(reverse("reisen:route", args=[self.reise.pk]), {"quelle": "gpx"}, follow=True)
        self.assertContains(antwort, "1 Etappe aus GPX-Tracks übernommen.")
        self.assertContains(antwort, "gefahren 16:37–16:42 (GPX)")
        e = Etappe.objects.get(pk=self.zur_faehre.pk)
        self.assertEqual((e.entfernung_km, e.fahrzeit), (Decimal("2.2"), timedelta(minutes=4)))
        self.assertEqual(e.routing_details["laender"], ["DE"])
        self.assertNotIn("verbrauch_l", e.routing_details)
        self.assertEqual(e.routing_details["linie"][-1], [54.32, 10.13])
        self.assertEqual(Etappe.objects.get(pk=self.weiter.pk).entfernung_km, Decimal("90.0"))

    def test_statistik_erst_nach_dem_ersetzen(self):
        track, _ = gpx.speichern(self.reise, FAHRT)
        self.assertNotContains(self.client.get(self.seite), "Gefahrene Strecke</h3>")
        Track.objects.filter(pk=track.pk).update(statistik={})   # Track von vor der Statistik
        self.client.post(reverse("reisen:route", args=[self.reise.pk]), {"quelle": "gpx"})
        seite = self.client.get(self.seite)
        self.assertContains(seite, "Gefahrene Strecke</h3>")
        self.assertContains(seite, f'id="fahrt-{self.zur_faehre.pk}"')
        self.assertContains(seite, "<dt>Höchstgeschwindigkeit</dt><dd>33 <small>km/h</small>")
        self.assertContains(seite, "<dt>in Bewegung</dt><dd>0:04 h</dd>")
        self.assertTrue(Track.objects.get(pk=track.pk).statistik)    # nachgerechnet und gespeichert

    def test_track_ohne_etappe_wird_gemeldet(self):
        gpx.speichern(self.reise, FAHRT.replace(b"2026-10-24", b"2026-10-26"))
        antwort = self.client.post(reverse("reisen:route", args=[self.reise.pk]), {"quelle": "gpx"}, follow=True)
        self.assertContains(antwort, "keine Etappe am 26.10.")


class HerunterladenTest(TestCase):
    def setUp(self):
        self.f = fam()
        self.reise = Reise.objects.create(familie=self.f, titel="Herbst", von=date(2026, 10, 24), bis=date(2026, 11, 1))
        self.track, _ = gpx.speichern(self.reise, gzip.compress(FAHRT))
        self.url = reverse("reisen:track_gpx", args=[self.reise.pk, self.track.pk])

    def test_eigene_familie_bekommt_das_original(self):
        self.client.force_login(Person.objects.create_user("anna@example.org", familie=self.f))
        antwort = self.client.get(self.url)
        self.assertEqual(antwort["Content-Type"], "application/gpx+xml")
        self.assertEqual(antwort["Content-Disposition"], 'attachment; filename="Fahrt_2026-10-24_16-37.gpx"')
        self.assertEqual(antwort.content, FAHRT)
        a, b = Ort.objects.create(familie=self.f, name="A"), Ort.objects.create(familie=self.f, name="B")
        Etappe.objects.create(reise=self.reise, datum=date(2026, 10, 24), von_ort=a, nach_ort=b)   # sonst kein „Route aktualisieren“
        self.assertContains(self.client.get(reverse("reisen:reise", args=[self.reise.pk])), self.url)

    def test_verwaltung_zeigt_den_link(self):
        self.client.force_login(Person.objects.create_superuser("t@example.org", "T", familie=self.f))
        self.assertContains(self.client.get(reverse("admin:reisen_reise_change", args=[self.reise.pk])), self.url)

    def test_fremde_und_abgemeldete_nicht(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(Person.objects.create_user("bob@example.org", familie=fam("Andere")))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        andere = Reise.objects.create(familie=self.f, titel="Andere", von=date(2026, 7, 1), bis=date(2026, 7, 2))
        self.client.force_login(Person.objects.create_user("anna@example.org", familie=self.f))
        self.assertEqual(self.client.get(reverse("reisen:track_gpx", args=[andere.pk, self.track.pk])).status_code, 404)


class VerwaltungHochladenTest(TestCase):
    """Alternative zur App: GPX-Dateien unter „Reise ändern“ hochladen."""

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .test_eingabe import leere_inlines
        self.datei = SimpleUploadedFile
        self.f = fam()
        self.client.force_login(Person.objects.create_superuser("t@example.org", "T", familie=self.f))
        a = Ort.objects.create(familie=self.f, name="Zuhause", breite=Decimal("54.30"), laenge=Decimal("10.13"))
        b = Ort.objects.create(familie=self.f, name="Hafen", breite=Decimal("54.32"), laenge=Decimal("10.13"))
        self.reise = Reise.objects.create(familie=self.f, titel="Herbst", von=date(2026, 10, 24), bis=date(2026, 11, 1))
        self.etappe = Etappe.objects.create(reise=self.reise, datum=date(2026, 10, 24), von_ort=a, nach_ort=b,
                                            entfernung_km=Decimal("3.0"))
        self.url = reverse("admin:reisen_reise_change", args=[self.reise.pk])
        self.daten = leere_inlines(**{
            "titel": "Herbst", "von": "2026-10-24", "bis": "2026-11-01", "urlaub_von": "", "urlaub_bis": "",
            "fahrzeugprofil": "", "verbrauch_l_100km": "", "dieselpreis": "1.80", "vignetten_meiden": "",
            "im_kalender": "on", "notizen": "", "_continue": "Sichern"})

    def test_formular_mit_dateifeld(self):
        seite = self.client.get(self.url).content.decode()
        self.assertIn('enctype="multipart/form-data"', seite)
        self.assertIn('name="gpx_dateien"', seite)
        self.assertIn("multiple", seite)
        self.assertLess(seite.index('id="tracks-group"'), seite.index('name="gpx_dateien"'))   # ganz unten
        self.assertLess(seite.index('name="notizen"'), seite.index('id="etappen-group"'))     # übrige Felder oben

    def test_mehrere_hochladen_und_uebernehmen(self):
        zweite = FAHRT.replace(b"T14:", b"T16:")
        antwort = self.client.post(self.url, {**self.daten, "gpx_uebernehmen": "on", "gpx_dateien": [
            self.datei("Fahrt_1.gpx", FAHRT), self.datei("Fahrt_2.gpx.gz", gzip.compress(zweite))]}, follow=True)
        self.assertContains(antwort, "Fahrt_1.gpx: 2,2 km ab 24.10. 16:37 hochgeladen.")
        self.assertContains(antwort, "1 Etappe aus GPX-Tracks übernommen.")
        self.assertEqual(Track.objects.filter(reise=self.reise).count(), 2)
        self.assertEqual(Etappe.objects.get(pk=self.etappe.pk).entfernung_km, Decimal("4.4"))

    def test_ohne_uebernehmen_und_ersetzen(self):
        gpx.speichern(self.reise, FAHRT)
        antwort = self.client.post(self.url, {**self.daten, "gpx_dateien": self.datei("Fahrt.gpx", FAHRT)}, follow=True)
        self.assertContains(antwort, "Fahrt.gpx: 2,2 km ab 24.10. 16:37 ersetzt.")
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(Etappe.objects.get(pk=self.etappe.pk).entfernung_km, Decimal("3.0"))

    def test_kaputte_datei_speichert_nichts(self):
        antwort = self.client.post(self.url, {**self.daten, "titel": "Neu", "gpx_dateien": [
            self.datei("gut.gpx", FAHRT), self.datei("foto.jpg", b"\xff\xd8kein gpx")]})
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "foto.jpg: Die Datei ist kein GPX.")
        self.assertFalse(Track.objects.exists())
        self.assertEqual(Reise.objects.get(pk=self.reise.pk).titel, "Herbst")
