from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from kalender.models import Schulferien
from kalender.schulferien import SchulferienFehler, abrufen
from konten.models import Person

from .hilfen import fam


def eintrag(von, bis, name, ausnahme=False):
    e = {"startDate": von, "endDate": bis, "name": [{"language": "DE", "text": name}],
         "subdivisions": [{"code": "DE-SH"}]}
    if ausnahme:
        e.update(tags=["Exception"], comment=[{"language": "DE", "text": "Inseln Sylt, Föhr, Amrum, Helgoland und die Halligen"}])
    return e


API_2028 = [eintrag("2027-12-23", "2028-01-08", "Weihnachtsferien"), eintrag("2028-04-03", "2028-04-15", "Osterferien"),
            eintrag("2028-05-26", "2028-05-26", "Himmelfahrt"),
            eintrag("2028-06-24", "2028-08-04", "Sommerferien"),
            eintrag("2028-06-24", "2028-07-28", "Sommerferien", ausnahme=True),
            eintrag("2028-10-16", "2028-10-30", "Herbstferien"),
            eintrag("2028-10-09", "2028-10-30", "Herbstferien", ausnahme=True)]


def antwort(daten, status=200):
    return mock.Mock(status_code=status, json=lambda: daten)


class SchulferienAbrufTest(TestCase):
    @mock.patch("kalender.schulferien.requests.get", return_value=antwort(API_2028))
    def test_ohne_inselausnahmen(self, get):
        ferien = abrufen("SH", 2028)
        self.assertEqual([(n, v.isoformat(), b.isoformat()) for n, v, b in ferien], [
            ("Weihnachtsferien", "2027-12-23", "2028-01-08"), ("Osterferien", "2028-04-03", "2028-04-15"),
            ("Ferientag nach Himmelfahrt", "2028-05-26", "2028-05-26"), ("Sommerferien", "2028-06-24", "2028-08-04"), ("Herbstferien", "2028-10-16", "2028-10-30")])
        params = get.call_args.kwargs["params"]
        self.assertEqual((params["subdivisionCode"], params["validFrom"], params["validTo"]),
                         ("DE-SH", "2028-01-01", "2028-12-31"))

    @mock.patch("kalender.schulferien.requests.get", return_value=antwort([], status=500))
    def test_fehler(self, get):
        with self.assertRaisesMessage(SchulferienFehler, "500"):
            abrufen("SH", 2028)

    def test_befehl_laesst_vorhandene_unveraendert(self):
        Schulferien.objects.create(bundesland="SH", bezeichnung="Weihnachtsferien (von Hand)",
                                   von=date(2027, 12, 23), bis=date(2028, 1, 8))
        aus = StringIO()
        with mock.patch("kalender.schulferien.requests.get", return_value=antwort(API_2028)):
            call_command("schulferien_laden", "SH", "2028", stdout=aus)
            call_command("schulferien_laden", "SH", "2028", stdout=aus)   # zweiter Lauf: nichts doppelt
        self.assertIn("4 neu, 1 schon vorhanden.", aus.getvalue())
        self.assertIn("0 neu, 5 schon vorhanden.", aus.getvalue())
        self.assertEqual(Schulferien.objects.count(), 5)
        self.assertTrue(Schulferien.objects.filter(bezeichnung="Weihnachtsferien (von Hand)").exists())


class SchulferienAdminTest(TestCase):
    def test_knopf_nur_fuer_super_admin(self):
        mitglied = Person.objects.create_user("m@example.org", "M", familie=fam(), is_staff=True)
        self.client.force_login(mitglied)
        self.assertEqual(self.client.get(reverse("admin:kalender_schulferien_abrufen")).status_code, 302)
        chef = Person.objects.create_user("c@example.org", "C", familie=fam(), is_staff=True, is_superuser=True)
        self.client.force_login(chef)
        self.assertContains(self.client.get(reverse("admin:kalender_schulferien_changelist")), "Schulferien abrufen")
        with mock.patch("kalender.schulferien.requests.get", return_value=antwort(API_2028)):
            ergebnis = self.client.post(reverse("admin:kalender_schulferien_abrufen"),
                                        {"bundesland": "SH", "jahre": "2028"}, follow=True)
        self.assertContains(ergebnis, "Schleswig-Holstein 2028: 5 neu")
        self.assertContains(ergebnis, "Herbstferien 16.10.2028–30.10.2028")
        falsch = self.client.post(reverse("admin:kalender_schulferien_abrufen"), {"bundesland": "SH", "jahre": "zwanzig"})
        self.assertContains(falsch, "nur Jahreszahlen")


def mv(von, bis, name, gruppen):
    return {**eintrag(von, bis, name), "groups": [{"code": g} for g in gruppen]}


# Auszug Mecklenburg-Vorpommern 2027: allgemeinbildende (ABS) und berufliche Schulen (BBS)
API_MV_2027 = [mv("2027-02-08", "2027-02-13", "Winterferien", ["DE-MV-BBS"]),
               mv("2027-02-08", "2027-02-19", "Winterferien", ["DE-MV-ABS"]),
               mv("2027-07-12", "2027-08-28", "Sommerferien", ["DE-MV-BBS"]),
               mv("2027-07-05", "2027-08-14", "Sommerferien", ["DE-MV-ABS"]),
               mv("2027-11-25", "2027-11-25", "Zusätzlicher Ferientag", ["DE-MV-ABS", "DE-MV-BBS"])]


class AlleLaenderTest(TestCase):
    @mock.patch("kalender.schulferien.requests.get", return_value=antwort(API_MV_2027))
    def test_nur_allgemeinbildende_schulen(self, get):
        self.assertEqual([(n, v.isoformat(), b.isoformat()) for n, v, b in abrufen("MV", 2027)], [
            ("Winterferien", "2027-02-08", "2027-02-19"), ("Sommerferien", "2027-07-05", "2027-08-14"),
            ("Zusätzlicher Ferientag", "2027-11-25", "2027-11-25")])

    def test_alle_bundeslaender(self):
        def je_land(url, params, **kw):
            land = params["subdivisionCode"][3:]
            return antwort([eintrag("2027-07-01", "2027-08-10", f"Sommerferien {land}")])
        aus = StringIO()
        with mock.patch("kalender.schulferien.requests.get", side_effect=je_land) as get:
            call_command("schulferien_laden", "ALLE", "2027", stdout=aus)
        self.assertEqual(get.call_count, 16)
        self.assertEqual(Schulferien.objects.values("bundesland").distinct().count(), 16)
        self.assertIn("16 neu", aus.getvalue())
        self.assertIn("BY Sommerferien BY", aus.getvalue())

    def test_familie_anlegen_holt_fehlende_schulferien(self):
        chef = Person.objects.create_user("c@example.org", "C", familie=fam(), is_staff=True, is_superuser=True)
        self.client.force_login(chef)
        daten = {"name": "Huber", "bundesland": "BY", "api_schluessel": "",
                 "personen-TOTAL_FORMS": "0", "personen-INITIAL_FORMS": "0",
                 "personen-MIN_NUM_FORMS": "0", "personen-MAX_NUM_FORMS": "1000"}
        heute = date.today().year
        with mock.patch("kalender.schulferien.requests.get",
                        return_value=antwort([eintrag(f"{heute}-08-01", f"{heute}-09-10", "Sommerferien")])) as get:
            seite = self.client.post(reverse("admin:konten_familie_add"), daten, follow=True)
        self.assertContains(seite, "Schulferien Bayern")
        self.assertEqual(get.call_count, 2)                     # dieses und nächstes Jahr
        self.assertTrue(Schulferien.objects.filter(bundesland="BY").exists())
        # Bundesland ohne Erfolg beim Abruf: Familie wird trotzdem gespeichert, mit Hinweis
        daten.update(name="Weber", bundesland="HE")
        with mock.patch("kalender.schulferien.requests.get", return_value=antwort([], status=503)):
            seite = self.client.post(reverse("admin:konten_familie_add"), daten, follow=True)
        self.assertContains(seite, "konnten nicht abgerufen werden")
        from konten.models import Familie
        self.assertTrue(Familie.objects.filter(name="Weber").exists())
