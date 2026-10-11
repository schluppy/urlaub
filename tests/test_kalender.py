from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from fahrzeuge.models import Fahrzeugprofil
from kalender.kalender import FEIERTAG, URLAUB, URLAUB_WOCHENENDE, jahreskalender, toenung
from kalender.tage import feiertage, urlaubstage
from konten.models import Person
from orte.models import Ort
from reisen.models import Buchung, Etappe, Kostenposition, Reise

from .hilfen import fam


class FeiertageTest(TestCase):
    def test_sh_2027(self):
        tage = feiertage(2027)
        self.assertEqual(
            sorted(tage),
            [date(2027, 1, 1), date(2027, 3, 26), date(2027, 3, 29), date(2027, 5, 1), date(2027, 5, 6),
             date(2027, 5, 17), date(2027, 10, 3), date(2027, 10, 31), date(2027, 12, 25), date(2027, 12, 26)])
        self.assertEqual(tage[date(2027, 5, 1)], "Tag der Arbeit")
        self.assertEqual(tage[date(2027, 12, 25)], "1. Weihnachtstag")

    def test_urlaubstage_ohne_wochenende_und_feiertag(self):
        # Karfreitag bis Ostermontag
        self.assertEqual(urlaubstage(date(2027, 3, 26), date(2027, 3, 29)), 0)
        self.assertEqual(urlaubstage(date(2027, 8, 27), date(2027, 9, 20)), 17)


class Urlaube2027Test(TestCase):
    """Die Werte aus dem Briefing: insgesamt 25 Urlaubstage."""

    def setUp(self):
        call_command("beispieldaten", stdout=open("/dev/null", "w"))

    def test_urlaubstage_je_reise(self):
        erwartet = {"Ostern an der Nordsee": 0, "Himmelfahrt an der Ostsee": 1, "Campingtreffen": 2, "Sommerreise": 17, "Herbstwoche": 5}
        ist = {r.titel: r.urlaubstage for r in Reise.objects.all()}
        self.assertEqual(ist, erwartet)

    def test_beispieldaten_mehrfach(self):
        call_command("beispieldaten", stdout=open("/dev/null", "w"))
        self.assertEqual(Reise.objects.count(), 5)

    def test_kalenderzellen(self):
        k = jahreskalender(2027, list(Reise.objects.all()))
        self.assertEqual(k["urlaubstage_summe"], 25)

        def zelle(m, d):
            return k["monate"][m - 1].zellen[d - 1]

        # Abfahrt nach Feierabend: diagonal geteilt, Titel dort
        ostern = zelle(3, 25)
        self.assertIn("linear-gradient", ostern.hintergrund)
        self.assertEqual(ostern.text, "Ostern an der Nordsee")
        # Karfreitag im Urlaub bleibt rot, ohne Reisetitel
        self.assertEqual(zelle(3, 26).hintergrund, FEIERTAG)
        self.assertEqual(zelle(3, 26).text, "Karfreitag")
        # Wochenende im Urlaub dunkler
        self.assertEqual(zelle(3, 27).hintergrund, URLAUB_WOCHENENDE)
        # Reise ohne Feierabend-Abfahrt: Titel am ersten Tag
        self.assertEqual(zelle(8, 27).text, "Sommerreise")
        self.assertEqual(zelle(8, 27).hintergrund, URLAUB)
        self.assertEqual(zelle(8, 28).text, "")
        # Schulferien als Balken, normaler Wochentag hell getönt
        self.assertTrue(zelle(7, 5).ferien)
        self.assertEqual(zelle(7, 5).hintergrund, toenung("#A86F12", 0.10))
        # 30. Februar gibt es nicht
        self.assertIsNone(zelle(2, 30).tag)


class BerechnungTest(TestCase):
    def test_kosten_und_waehrung(self):
        profil = Fahrzeugprofil.objects.create(familie=fam(), name="Gespann", verbrauch_l_100km=Decimal("12.2"))
        zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause")
        platz = Ort.objects.create(familie=fam(), name="Küstencamping")
        r = Reise.objects.create(familie=fam(), titel="Schottland", von=date(2026, 5, 29), bis=date(2026, 6, 21),
                                 fahrzeugprofil=profil, dieselpreis=Decimal("2.06"))
        Etappe.objects.create(reise=r, datum=r.von, von_ort=zuhause, nach_ort=platz,
                              entfernung_km=Decimal("3482"), fahrzeit=timedelta(hours=6, minutes=34),
                              pause=timedelta(minutes=75),
                              startzeit=time(5, 30))
        Buchung.objects.create(reise=r, ort=platz, von=date(2026, 5, 30), bis=date(2026, 6, 2),
                               preis_pro_nacht=Decimal(48), waehrung="GBP", wechselkurs=Decimal("0.8653"),
                               anzahlung=Decimal(36))
        Kostenposition.objects.create(reise=r, art="faehre", betrag=Decimal(1442))
        r = Reise.objects.get(pk=r.pk)
        # wie Tabelle: 3482 km × 12,2 L / 100 × 2,06 €
        self.assertEqual(r.dieselkosten, Decimal("875.10"))
        self.assertEqual(r.buchungen_eur, Decimal("166.42"))
        self.assertEqual(r.gesamtkosten, Decimal("2483.52"))
        self.assertEqual(r.naechte, 3)
        self.assertEqual(r.etappen.get().ankunft.strftime("%H:%M"), "13:19")


class SeitenTest(TestCase):
    def setUp(self):
        call_command("beispieldaten", stdout=open("/dev/null", "w"))
        self.person = Person.objects.create_superuser("test@example.org", "Test", familie=fam())

    def test_anmeldung_noetig(self):
        self.assertEqual(self.client.get(reverse("kalender:jahr", args=[2027])).status_code, 302)

    def test_seiten(self):
        self.client.force_login(self.person)
        for url in [reverse("portal:start"), reverse("portal:jahr", args=[2027]),
                    reverse("kalender:jahr", args=[2027]),
                    reverse("admin:reisen_reise_change", args=[Reise.objects.first().pk]),
                    reverse("admin:reisen_reise_add")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        seite = self.client.get(reverse("portal:jahr", args=[2027])).content.decode()
        self.assertIn("Sommerreise", seite)

    def test_pdf(self):
        self.client.force_login(self.person)
        antwort = self.client.get(reverse("kalender:pdf", args=[2027]))
        self.assertEqual(antwort["Content-Type"], "application/pdf")
        self.assertTrue(antwort.content.startswith(b"%PDF"))


class UrlaubUndReisezeitTest(TestCase):
    """Urlaub inkl. Vor-/Nachbereitung bestimmt den Kalender; die Reisezeit ist eine Teilmenge."""

    def setUp(self):
        zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause")
        platz = Ort.objects.create(familie=fam(), name="Seecamping")
        self.r = Reise.objects.create(familie=fam(), titel="Sommerreise", urlaub_von=date(2027, 8, 25), urlaub_bis=date(2027, 9, 20),
                                      von=date(2027, 8, 27), bis=date(2027, 9, 19))
        Etappe.objects.create(reise=self.r, datum=self.r.von, von_ort=zuhause, nach_ort=platz)
        Etappe.objects.create(reise=self.r, datum=self.r.bis, von_ort=platz, nach_ort=zuhause)
        Buchung.objects.create(reise=self.r, ort=platz, von=self.r.von, bis=self.r.bis, gesamtpreis=Decimal(700))

    def test_urlaubstage_aus_urlaub(self):
        # 25.08.–20.09.2027: Mi 25.08. bis Mo 20.09. = 19 Arbeitstage
        self.assertEqual(self.r.urlaubstage, 19)
        self.assertIsNone(self.r.abfahrt_feierabend)

    def test_keine_ungebuchte_nacht(self):
        self.assertFalse([t for _, t in self.r.hinweise() if "Nächte ohne Buchung" in t])

    def test_kalender(self):
        k = jahreskalender(2027, [self.r])
        aug, sep = k["monate"][7].zellen, k["monate"][8].zellen
        self.assertEqual(aug[24].text, "Sommerreise")          # Titel am ersten Urlaubstag (Vorbereitung)
        self.assertEqual(aug[24].hintergrund, URLAUB)
        self.assertEqual(sep[19].hintergrund, URLAUB)          # Mo 20.09. Nachbereitung
        self.assertNotIn("urlaub", sep[20].klassen)            # Di 21.09. wieder Alltag
        self.assertEqual(k["urlaube"][0]["zeitraum"], "25.08.–20.09.")

    def test_feierabend_aus_reisebeginn(self):
        r = Reise.objects.create(familie=fam(), titel="Ostern an der Nordsee", urlaub_von=date(2027, 3, 26), urlaub_bis=date(2027, 3, 29),
                                 von=date(2027, 3, 25), bis=date(2027, 3, 29))
        self.assertEqual(r.abfahrt_feierabend, date(2027, 3, 25))
        self.assertEqual(r.urlaubstage, 0)
        # Reise am Samstag vor dem Urlaub ist keine Feierabend-Abfahrt
        r.von = date(2027, 3, 20)
        self.assertIsNone(r.abfahrt_feierabend)

    def test_ohne_eigenen_urlaub_gilt_reisezeit(self):
        r = Reise(familie=fam(), titel="Kurz", von=date(2027, 6, 3), bis=date(2027, 6, 6))
        self.assertEqual((r.urlaub_beginn, r.urlaub_ende, r.urlaubstage), (r.von, r.bis, 2))
        self.assertFalse(r.hat_eigenen_urlaub)

    def test_urlaub_nur_vollstaendig(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Reise(familie=fam(), titel="X", von=date(2027, 6, 3), bis=date(2027, 6, 6), urlaub_von=date(2027, 6, 1)).full_clean()


class KalenderPdfTest(TestCase):
    def test_eine_seite_a4_quer(self):
        from kalender.views import kalender_dokument

        call_command("beispieldaten", stdout=open("/dev/null", "w"))
        # viele Reisen mit langen Titeln: die Fußzeile wird länger, es muss trotzdem eine Seite bleiben
        for monat in range(1, 13):
            Reise.objects.create(familie=fam(), titel=f"Wochenende mit sehr langem Reisetitel Nr. {monat}",
                                 von=date(2027, monat, 12), bis=date(2027, monat, 14))
        seiten = kalender_dokument(fam(), 2027).pages
        self.assertEqual(len(seiten), 1)
        mm = 25.4 / 96   # WeasyPrint rechnet in CSS-Pixeln
        self.assertEqual((round(seiten[0].width * mm), round(seiten[0].height * mm)), (297, 210))
