from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from konten.models import Person
from orte.models import Ort
from reisen.erinnerungen import anstehend, faellige, versenden
from reisen.models import Buchung, Erinnerung, Etappe, Reise

from .hilfen import fam

HEUTE = date(2027, 8, 1)


class ErinnerungenTest(TestCase):
    def setUp(self):
        Person.objects.create_superuser("a@example.org", "Anna", familie=fam())
        Person.objects.create_superuser("b@example.org", "Ben", familie=fam())
        Person.objects.create_superuser("weg@example.org", "Inaktiv", is_active=False, familie=fam())
        self.platz = Ort.objects.create(familie=fam(), name="Camping am See", website="https://example.org")
        self.zuhause = Ort.objects.create(familie=fam(), name="Zuhause", typ="zuhause")
        self.reise = Reise.objects.create(familie=fam(), titel="Sommerreise", von=date(2027, 8, 27), bis=date(2027, 9, 20))
        self.buchung = Buchung.objects.create(
            reise=self.reise, ort=self.platz, von=date(2027, 8, 28), bis=date(2027, 9, 5),
            preis_pro_nacht=Decimal(64), anzahlung=Decimal(100), status="angezahlt",
            rest_faellig_am=date(2027, 8, 5), buchungsnummer="X1")

    def titel(self, heute):
        return [p.titel for p in faellige(heute, fam())]

    def test_restzahlung_zeitfenster(self):
        self.assertEqual(self.titel(date(2027, 7, 28)), [])                        # 8 Tage vorher: noch nichts
        self.assertEqual(self.titel(HEUTE), ["Restzahlung Camping am See in 4 Tagen fällig"])
        self.assertEqual(self.titel(date(2027, 8, 5)), ["Restzahlung Camping am See heute fällig"])
        self.assertEqual(self.titel(date(2027, 8, 7)), ["Restzahlung Camping am See seit 2 Tagen fällig"])
        self.assertEqual(self.titel(date(2027, 8, 25)), ["Sommerreise beginnt in 2 Tagen"])  # zu alt für Mahnung

    def test_bezahlt_keine_erinnerung(self):
        self.buchung.status = "bezahlt"
        self.buchung.save()
        self.assertEqual(self.titel(HEUTE), [])

    def test_versand_einmal_je_stufe(self):
        versenden(HEUTE)
        self.assertEqual(len(mail.outbox), 2)                       # nur aktive Personen
        self.assertEqual(mail.outbox[0].subject, "Urlaubsplaner: Restzahlung Camping am See in 4 Tagen fällig")
        self.assertIn("412,00 EUR bis 05.08.2027", mail.outbox[0].body)
        self.assertIn("Buchungsnr. X1", mail.outbox[0].body)
        self.assertIn(f"/reise/{self.reise.pk}/", mail.outbox[0].body)
        versenden(HEUTE + timedelta(days=1))                        # vorab-Stufe schon verschickt
        self.assertEqual(len(mail.outbox), 2)
        versenden(date(2027, 8, 5))                                 # Fälligkeitstag: neue Stufe
        self.assertEqual(len(mail.outbox), 4)

    def test_mailfehler_nichts_markiert(self):
        with mock.patch("reisen.erinnerungen.send_mail", side_effect=OSError("smtp")):
            with self.assertRaises(OSError):
                versenden(HEUTE)
        self.assertEqual(len(faellige(HEUTE, fam())), 1)

    def test_eigene_erinnerung(self):
        e = Erinnerung.objects.create(familie=fam(), reise=self.reise, datum=HEUTE, text="Fähre buchbar")
        Erinnerung.objects.create(familie=fam(), datum=HEUTE + timedelta(days=3), text="später")
        Erinnerung.objects.create(familie=fam(), datum=HEUTE, text="erledigt", erledigt=True)
        versenden(HEUTE)
        self.assertEqual(mail.outbox[0].subject, "Urlaubsplaner: 2 Erinnerungen")
        self.assertIn("Fähre buchbar", mail.outbox[0].body)
        self.assertNotIn("später", mail.outbox[0].body)
        e.refresh_from_db()
        self.assertIsNotNone(e.gesendet_am)
        self.assertNotIn("Fähre buchbar", self.titel(HEUTE + timedelta(days=1)))

    def test_reisecheck(self):
        Etappe.objects.create(reise=self.reise, datum=self.reise.von, startzeit=time(6),
                              von_ort=self.zuhause, nach_ort=self.platz)
        self.buchung.status = "bezahlt"
        self.buchung.save()
        punkte = faellige(date(2027, 8, 13), fam())
        self.assertEqual([p.titel for p in punkte], ["Sommerreise beginnt in 14 Tagen"])
        zeilen = " | ".join(punkte[0].zeilen)
        self.assertIn("Abfahrt 27.08. um 06:00 nach Camping am See", zeilen)
        self.assertIn("1 Etappe ohne Entfernung", zeilen)
        self.assertIn("Nächte ohne Buchung", zeilen)

    def test_befehl_trocken(self):
        aus = StringIO()
        call_command("erinnerungen", "--trocken", "--heute", "2027-08-01", stdout=aus)
        self.assertIn("2027-08-01 (trocken) 05.08.2027  Restzahlung Camping am See in 4 Tagen fällig", aus.getvalue())
        self.assertEqual(len(mail.outbox), 0)
        call_command("erinnerungen", "--heute", "2026-01-01", stdout=aus)
        self.assertIn("2026-01-01 Nichts fällig.", aus.getvalue())

    def test_startseite_demnaechst(self):
        self.assertEqual([p.art for p in anstehend(date(2027, 7, 20), fam())], ["rest"])   # Reise erst in 38 Tagen
        self.assertEqual([p.art for p in anstehend(HEUTE, fam())], ["rest", "reise"])
        self.client.force_login(Person.objects.get(email="a@example.org"))
        with mock.patch("portal.views.anstehend", return_value=anstehend(HEUTE, fam())):
            antwort = self.client.get(reverse("portal:jahr", args=[2027]))
        self.assertContains(antwort, "Demnächst")
        self.assertContains(antwort, "Restzahlung Camping am See")
