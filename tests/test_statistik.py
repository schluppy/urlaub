"""Statistik für den Super-Admin und die Erfassung der letzten Nutzung."""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from freigaben.models import Freigabe, Widgetzugang
from konten.models import Familie, Person
from reisen.models import Erinnerung, Track

from .test_familien import daten


class ZuletztAktivTest(TestCase):
    def setUp(self):
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=Familie.objects.create(name="A"))

    def test_seitenaufruf_setzt_zeitpunkt(self):
        self.client.force_login(self.anna)
        self.client.get(reverse("portal:start"))
        self.anna.refresh_from_db()
        self.assertAlmostEqual(self.anna.zuletzt_aktiv, timezone.now(), delta=timedelta(seconds=10))

    def test_schreibt_hoechstens_alle_paar_minuten(self):
        vorhin = timezone.now() - timedelta(minutes=2)
        Person.objects.filter(pk=self.anna.pk).update(zuletzt_aktiv=vorhin)
        self.client.force_login(self.anna)
        self.client.get(reverse("portal:start"))
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.zuletzt_aktiv, vorhin)

    def test_ohne_anmeldung_nichts(self):
        self.client.get(reverse("portal:anmelden"))
        self.anna.refresh_from_db()
        self.assertIsNone(self.anna.zuletzt_aktiv)


class StatistikTest(TestCase):
    def setUp(self):
        self.a = Familie.objects.create(name="Muster", bundesland="SH")
        self.b = Familie.objects.create(name="Müller", bundesland="BY")
        self.reise_b, _, _ = daten(self.b, "BBB")
        daten(self.a, "AAA")
        Freigabe.objects.create(familie=self.b, art="reise", reise=self.reise_b,
                                gueltig_bis=date.today() + timedelta(days=5), aufrufe=7)
        Freigabe.objects.create(familie=self.b, art="kalender", jahr=2027, gueltig_bis=date.today() - timedelta(days=1))
        Erinnerung.objects.create(familie=self.b, datum=date.today(), text="BBB erledigt", erledigt=True)
        self.boss = Person.objects.create_user("boss@example.org", "Boss", familie=self.a, is_superuser=True)
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=self.a)
        self.bert = Person.objects.create_user("bert@example.org", "Bert", familie=self.b,
                                               zuletzt_aktiv=timezone.now() - timedelta(days=3))
        self.url = reverse("admin:konten_familie_statistik")
        Widgetzugang.objects.create(person=self.bert, abrufe=5, zuletzt_am=timezone.now())
        Widgetzugang.objects.create(person=self.bert, abrufe=3, beendet_am=timezone.now())
        Track.objects.create(reise=self.reise_b, beginn=timezone.now(), ende=timezone.now(),
                             entfernung_km=123.4, fahrzeit=timedelta(hours=2), gpx="<gpx/>")

    def test_nur_super_admin(self):
        self.client.force_login(self.anna)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_zahlen_je_familie(self):
        self.client.force_login(self.boss)
        antwort = self.client.get(self.url)
        zeilen = {z["familie"].name: z for z in antwort.context["zeilen"]}
        b = zeilen["Müller"]
        self.assertEqual((b["orte"], b["reisen"], b["etappen"], b["buchungen"]), (2, 1, 1, 1))
        self.assertEqual((b["freigaben"], b["freigaben_aktiv"], b["freigaben_aufrufe"]), (2, 1, 7))
        self.assertEqual(b["erinnerungen_offen"], 1)
        self.assertEqual(b["aktive_personen"], 1)
        self.assertAlmostEqual(b["zuletzt_genutzt"], self.bert.zuletzt_aktiv, delta=timedelta(seconds=1))
        self.assertEqual((b["widget_aktiv"], b["widget_abrufe"]), (1, 8))
        self.assertEqual(b["gpx"], 1)
        self.assertNotIn("freigaben", zeilen["Muster"])
        self.assertNotIn("gpx", zeilen["Muster"])
        # Muster wurde gerade vom Boss genutzt und steht deshalb oben
        self.assertEqual(antwort.context["zeilen"][0]["familie"].name, "Muster")
        self.assertEqual(antwort.context["summen"]["reisen"], 2)
        self.assertEqual((antwort.context["summen"]["widget_abrufe"], antwort.context["summen"]["gpx"]), (8, 1))

    def test_keine_inhalte_fremder_familien(self):
        self.client.force_login(self.boss)
        inhalt = self.client.get(self.url).content.decode()
        self.assertIn("Müller", inhalt)
        self.assertIn("vor 3 Tagen", inhalt)
        self.assertNotIn("BBB", inhalt)

    def test_links_in_der_verwaltung(self):
        self.client.force_login(self.boss)
        for seite in [reverse("admin:index"), reverse("admin:konten_familie_changelist")]:
            self.assertContains(self.client.get(seite), self.url)
        self.client.force_login(self.anna)
        self.assertNotContains(self.client.get(reverse("admin:index")), self.url)
