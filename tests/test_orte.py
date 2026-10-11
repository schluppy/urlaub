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
