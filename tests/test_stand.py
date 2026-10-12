"""Zeitstempel in PDF und Excel: gleicher Stand im Dokument und im Dateinamen."""
from datetime import date, datetime
from io import BytesIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from freigaben.models import Freigabe
from kalender.views import _kontext as kalender_kontext
from konten.models import Person
from reisen.models import Reise

from .hilfen import fam

STAND = datetime(2026, 10, 12, 8, 15, tzinfo=ZoneInfo("Europe/Berlin"))


@mock.patch("reisen.dokumente.timezone.localtime", return_value=STAND)
class StandTest(TestCase):
    def setUp(self):
        self.familie = fam()
        self.reise = Reise.objects.create(familie=self.familie, titel="Sommerreise", von=date(2027, 8, 2), bis=date(2027, 8, 6))
        self.client.force_login(Person.objects.create_user("t@example.org", "T", familie=self.familie, is_staff=True))

    def test_kalender_pdf(self, _):
        antwort = self.client.get(reverse("kalender:pdf", args=[2027]))
        self.assertIn('filename="Urlaubskalender_2027_Stand_2026-10-12_0815.pdf"', antwort["Content-Disposition"])
        html = render_to_string("kalender/pdf.html", {**kalender_kontext(self.familie, 2027), "stand": STAND,
                                                      "zeilenhoehe": 5.0, "schriften": ""})
        self.assertIn("Stand 12.10.2026, 08:15 Uhr", html)
        # Die Kalenderseite im Browser zeigt keinen Stand (nur das PDF)
        self.assertNotContains(self.client.get(reverse("kalender:jahr", args=[2027])), "Stand 12.10.2026")

    def test_reise_pdf_und_excel(self, _):
        pdf = self.client.get(reverse("reisen:pdf", args=[self.reise.pk]))
        self.assertIn("2027-08-02_Sommerreise_Stand_2026-10-12_0815.pdf", pdf["Content-Disposition"])
        excel = self.client.get(reverse("reisen:excel", args=[self.reise.pk]))
        self.assertIn("2027-08-02_Sommerreise_Stand_2026-10-12_0815.xlsx", excel["Content-Disposition"])
        self.assertEqual(load_workbook(BytesIO(excel.content))["Übersicht"]["C1"].value, "Stand: 12.10.2026, 08:15 Uhr")

    def test_geteilter_kalender(self, _):
        f = Freigabe.objects.create(familie=self.familie, art="kalender", jahr=2027, gueltig_bis=date(2099, 1, 1))
        self.client.logout()
        antwort = self.client.get(reverse("freigaben:kalender_pdf", args=[f.token]))
        self.assertIn("Urlaubskalender_2027_Stand_2026-10-12_0815.pdf", antwort["Content-Disposition"])
