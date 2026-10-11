import json
from datetime import date, time, timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase
from django.urls import reverse

from freigaben.models import Freigabe
from konten.models import Familie, Person
from orte.models import Ort
from reisen.models import Buchung, Etappe, Kostenposition, Reise
from reisen.views import _km, ohne_zuhause

from .hilfen import fam

HEIM = (54.3226, 10.1355)   # Beispiel: Kiel, Rathausplatz


class OhneZuhauseTest(TestCase):
    def test_linie_beginnt_am_kreisrand(self):
        # gerade nach Süden: alle 0,01° ≈ 1,1 km
        linie = [[HEIM[0] - i / 100, HEIM[1]] for i in range(0, 20)]
        rest = ohne_zuhause(linie, {HEIM})
        self.assertAlmostEqual(_km(rest[0], HEIM), 3.0, delta=0.01)
        self.assertTrue(all(_km(p, HEIM) >= 2.99 for p in rest))
        self.assertEqual(rest[-1], linie[-1])

    def test_luftlinie_und_rueckweg(self):
        hin = ohne_zuhause([[*HEIM], [47.8, 7.55]], {HEIM})
        self.assertEqual(len(hin), 2)
        self.assertAlmostEqual(_km(hin[0], HEIM), 3.0, delta=0.01)
        zurueck = ohne_zuhause([[47.8, 7.55], [*HEIM]], {HEIM})
        self.assertAlmostEqual(_km(zurueck[-1], HEIM), 3.0, delta=0.01)


class FreigabeTest(TestCase):
    def setUp(self):
        self.familie = fam()
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=self.familie, is_staff=True)
        zuhause = Ort.objects.create(familie=self.familie, name="Zuhause", typ="zuhause",
                                     adresse="Rathausplatz 1, Kiel", breite=Decimal("54.3226"), laenge=Decimal("10.1355"))
        platz = Ort.objects.create(familie=self.familie, name="Seecamping", breite=Decimal("47.8"),
                                   laenge=Decimal("7.55"), website="https://seecamping.example")
        self.reise = Reise.objects.create(familie=self.familie, titel="Sommerreise", von=date(2027, 8, 2),
                                          bis=date(2027, 8, 6), notizen="Geheime Notiz")
        linie = [[54.3226 - i / 100, 10.1355] for i in range(0, 20)] + [[47.8, 7.55]]
        Etappe.objects.create(reise=self.reise, datum=date(2027, 8, 2), startzeit=time(8), von_ort=zuhause,
                              nach_ort=platz, entfernung_km=Decimal(900), routing_details={"linie": linie})
        Etappe.objects.create(reise=self.reise, datum=date(2027, 8, 6), von_ort=platz, nach_ort=zuhause)
        Buchung.objects.create(reise=self.reise, ort=platz, von=date(2027, 8, 2), bis=date(2027, 8, 6),
                               gesamtpreis=Decimal(321), buchungsnummer="ABC-777")
        Kostenposition.objects.create(reise=self.reise, art="vignette", betrag=Decimal("42.50"))
        self.client.force_login(self.anna)

    def teilen(self, **daten):
        daten = {"gueltig_bis": (date.today() + timedelta(days=7)).isoformat(), "fuer": "Oma", **daten}
        antwort = self.client.post(reverse("freigaben:reise", args=[self.reise.pk]), daten)
        self.assertEqual(antwort.status_code, 302)
        return Freigabe.objects.latest("id"), antwort

    def test_link_erstellen_und_teilen(self):
        f, antwort = self.teilen()
        self.assertEqual((f.familie, f.reise, f.fuer, f.mit_details, f.erstellt_von), (self.familie, self.reise, "Oma", False, self.anna))
        self.assertGreaterEqual(len(f.token), 20)
        seite = self.client.get(antwort["Location"]).content.decode()
        self.assertIn(f.link, seite)
        self.assertIn("https://wa.me/?text=", seite)
        self.assertIn("Sommerreise", unquote(f.whatsapp))
        self.assertIn(f.link, unquote(f.whatsapp))
        self.assertTrue(f.email.startswith("mailto:?subject=Sommerreise&body="))

    def test_oeffentlich_ohne_anmeldung_ohne_kosten_und_ohne_zuhause(self):
        f, _ = self.teilen()
        self.client.logout()
        antwort = self.client.get(reverse("freigaben:ansehen", args=[f.token]))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(antwort["Cache-Control"], "no-store")
        inhalt = antwort.content.decode()
        self.assertIn("Sommerreise", inhalt)
        self.assertIn("Seecamping", inhalt)
        for verborgen in ["321,00", "42,50", "ABC-777", "Geheime Notiz", "Rathausplatz", "Bearbeiten", "data-tomtom"]:
            with self.subTest(verborgen):
                self.assertNotIn(verborgen, inhalt)
        karte = json.loads(inhalt.split('<script id="kartendaten" type="application/json">')[1].split("</script>")[0])
        self.assertEqual([o["name"] for o in karte["orte"]], ["Seecamping"])
        for s in karte["strecken"]:
            self.assertTrue(all(_km(p, HEIM) >= 2.99 for p in s["punkte"]), s["text"])
        f.refresh_from_db()
        self.assertEqual(f.aufrufe, 1)
        self.assertIsNotNone(f.zuletzt_am)

    def test_mit_details(self):
        f, _ = self.teilen(mit_details="on")
        self.client.logout()
        inhalt = self.client.get(reverse("freigaben:ansehen", args=[f.token])).content.decode()
        for sichtbar in ["321,00", "42,50", "ABC-777", "Geheime Notiz"]:
            self.assertIn(sichtbar, inhalt)
        self.assertNotIn("Rathausplatz", inhalt)   # Zuhause bleibt auch hier verborgen

    def test_abgelaufen_und_beendet(self):
        f, _ = self.teilen()
        Freigabe.objects.filter(pk=f.pk).update(gueltig_bis=date.today() - timedelta(days=1))
        self.client.logout()
        antwort = self.client.get(reverse("freigaben:ansehen", args=[f.token]))
        self.assertEqual(antwort.status_code, 410)
        self.assertNotIn("Sommerreise", antwort.content.decode())
        self.assertNotIn(self.familie.name, antwort.content.decode())
        self.client.force_login(self.anna)
        f2, _ = self.teilen()
        self.client.post(reverse("freigaben:beenden", args=[f2.pk]))
        self.client.logout()
        self.assertContains(self.client.get(reverse("freigaben:ansehen", args=[f2.token])), "beendet", status_code=410)
        self.assertEqual(self.client.get(reverse("freigaben:ansehen", args=["gibt-es-nicht"])).status_code, 404)

    def test_heute_noch_gueltig_ablauf_pruefung(self):
        _, antwort = self.teilen(gueltig_bis=date.today().isoformat())
        self.assertEqual(antwort.status_code, 302)
        for falsch in [date.today() - timedelta(days=1), date.today() + timedelta(days=400)]:
            antwort = self.client.post(reverse("freigaben:reise", args=[self.reise.pk]),
                                       {"gueltig_bis": falsch.isoformat()})
            self.assertEqual(antwort.status_code, 200)   # Formular mit Fehler
        self.assertEqual(Freigabe.objects.count(), 1)

    def test_fremde_familie(self):
        f, _ = self.teilen()
        bert = Person.objects.create_user("bert@example.org", "Bert", is_staff=True,
                                          familie=Familie.objects.create(name="Andere", bundesland="BY"))
        self.client.force_login(bert)
        self.assertEqual(self.client.get(reverse("freigaben:reise", args=[self.reise.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("freigaben:beenden", args=[f.pk])).status_code, 404)
        f.refresh_from_db()
        self.assertTrue(f.aktiv)
        self.assertNotContains(self.client.get(reverse("admin:freigaben_freigabe_changelist")), "Sommerreise")

    def test_kalender_teilen_mit_pdf(self):
        antwort = self.client.post(reverse("freigaben:kalender", args=[2027]),
                                   {"gueltig_bis": (date.today() + timedelta(days=30)).isoformat()})
        f = Freigabe.objects.get()
        self.assertEqual((f.art, f.jahr, f.reise), ("kalender", 2027, None))
        Reise.objects.create(familie=Familie.objects.create(name="Andere", bundesland="BY"), titel="Fremdreise",
                             von=date(2027, 9, 1), bis=date(2027, 9, 3))
        self.client.logout()
        seite = self.client.get(reverse("freigaben:ansehen", args=[f.token])).content.decode()
        self.assertIn("Urlaubskalender 2027", seite)
        self.assertIn("Sommerreise", seite)
        self.assertNotIn("Fremdreise", seite)
        pdf = self.client.get(reverse("freigaben:kalender_pdf", args=[f.token]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        reise_freigabe = Freigabe.objects.create(familie=self.familie, art="reise", reise=self.reise,
                                                 gueltig_bis=date.today())
        self.assertEqual(self.client.get(reverse("freigaben:kalender_pdf", args=[reise_freigabe.token])).status_code, 404)
