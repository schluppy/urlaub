"""Mandantentrennung: Familie A sieht und ändert nichts von Familie B – auch der Super-Admin nicht."""
from datetime import date, time
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from fahrzeuge.models import Fahrzeugprofil
from kalender.models import Schulferien
from konten.models import ApiNutzung, ApiSchluessel, Familie, Person
from orte.models import Ort
from reisen.erinnerungen import versenden
from reisen.models import Buchung, Erinnerung, Etappe, Reise

from .test_routing import GEO, ROUTE, Antwort


def daten(familie, praefix, bundesland_ort="Zuhause"):
    zuhause = Ort.objects.create(familie=familie, name=bundesland_ort, typ="zuhause",
                                 breite=Decimal("53.7"), laenge=Decimal("9.7"))
    platz = Ort.objects.create(familie=familie, name=f"{praefix} Platz", breite=Decimal("47.8"), laenge=Decimal("7.5"))
    profil = Fahrzeugprofil.objects.create(familie=familie, name="Gespann")
    reise = Reise.objects.create(familie=familie, titel=f"{praefix} Reise", von=date(2027, 8, 2), bis=date(2027, 8, 6),
                                 fahrzeugprofil=profil)
    Etappe.objects.create(reise=reise, datum=reise.von, startzeit=time(8), von_ort=zuhause, nach_ort=platz)
    Buchung.objects.create(reise=reise, ort=platz, von=reise.von, bis=reise.bis, preis_pro_nacht=Decimal(30),
                           anzahlung=Decimal(10), status="angezahlt", rest_faellig_am=date(2027, 7, 30))
    Erinnerung.objects.create(familie=familie, reise=reise, datum=date(2027, 7, 20), text=f"{praefix} Fähre buchen")
    return reise, platz, profil


class TrennungTest(TestCase):
    def setUp(self):
        self.a = Familie.objects.create(name="Muster", bundesland="SH")
        self.b = Familie.objects.create(name="Müller", bundesland="BY")
        self.reise_a, self.platz_a, _ = daten(self.a, "AAA")
        self.reise_b, self.platz_b, self.profil_b = daten(self.b, "BBB")
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=self.a, is_staff=True)
        self.boss = Person.objects.create_user("boss@example.org", "Boss", familie=self.a, is_staff=True,
                                               is_superuser=True)
        self.bert = Person.objects.create_user("bert@example.org", "Bert", familie=self.b, is_staff=True)

    def seite(self, person, url):
        self.client.force_login(person)
        return self.client.get(url)

    def test_portalseiten_zeigen_nur_eigene_reisen(self):
        for url in [reverse("portal:jahr", args=[2027]), reverse("kalender:jahr", args=[2027])]:
            with self.subTest(url):
                inhalt = self.seite(self.anna, url).content.decode()
                self.assertIn("AAA Reise", inhalt)
                self.assertNotIn("BBB", inhalt)

    def test_fremde_reise_nicht_gefunden(self):
        for name in ["reisen:reise", "reisen:excel", "reisen:pdf"]:
            with self.subTest(name):
                self.assertEqual(self.seite(self.anna, reverse(name, args=[self.reise_b.pk])).status_code, 404)
                self.assertEqual(self.seite(self.bert, reverse(name, args=[self.reise_b.pk])).status_code, 200)
        self.client.force_login(self.anna)
        with mock.patch("reisen.views.reise_routen") as routen:
            self.assertEqual(self.client.post(reverse("reisen:route", args=[self.reise_b.pk])).status_code, 404)
        routen.assert_not_called()

    def test_verwaltung_listen_und_bearbeiten(self):
        for person in [self.anna, self.boss]:     # auch der Super-Admin sieht keine fremden Reisen
            for url, fremd in [(reverse("admin:reisen_reise_changelist"), "BBB Reise"),
                               (reverse("admin:orte_ort_changelist"), "BBB Platz"),
                               (reverse("admin:reisen_erinnerung_changelist"), "BBB Fähre")]:
                with self.subTest(person=person.name, url=url):
                    inhalt = self.seite(person, url).content.decode()
                    self.assertNotIn(fremd, inhalt)
                    self.assertIn(fremd.replace("BBB", "AAA"), inhalt)
            for url in [reverse("admin:reisen_reise_change", args=[self.reise_b.pk]),
                        reverse("admin:orte_ort_change", args=[self.platz_b.pk]),
                        reverse("admin:fahrzeuge_fahrzeugprofil_change", args=[self.profil_b.pk])]:
                with self.subTest(person=person.name, url=url):
                    # Django leitet bei unbekannten Objekten zur Übersicht weiter
                    self.assertEqual(self.seite(person, url).status_code, 302)
        self.client.force_login(self.anna)
        self.client.post(reverse("admin:reisen_reise_delete", args=[self.reise_b.pk]), {"post": "yes"})
        self.assertTrue(Reise.objects.filter(pk=self.reise_b.pk).exists())

    def test_seitenfilter_nur_eigene_fahrzeugprofile(self):
        profil_a = self.reise_a.fahrzeugprofil
        for person in [self.anna, self.boss]:
            with self.subTest(person=person.name):
                inhalt = self.seite(person, reverse("admin:reisen_reise_changelist")).content.decode()
                self.assertIn(f"fahrzeugprofil__id__exact={profil_a.pk}", inhalt)
                self.assertNotIn(f"fahrzeugprofil__id__exact={self.profil_b.pk}", inhalt)

    def test_autocomplete_nur_eigene_orte(self):
        self.client.force_login(self.anna)
        antwort = self.client.get(reverse("admin:autocomplete"), {
            "term": "Platz", "app_label": "reisen", "model_name": "etappe", "field_name": "nach_ort"})
        namen = [e["text"] for e in antwort.json()["results"]]
        self.assertEqual(namen, ["AAA Platz"])

    def test_fremder_ort_wird_beim_speichern_abgelehnt(self):
        self.client.force_login(self.anna)
        daten_post = {"titel": "Neu", "von": "2027-09-01", "bis": "2027-09-03", "urlaub_von": "", "urlaub_bis": "",
                      "fahrzeugprofil": self.profil_b.pk, "verbrauch_l_100km": "", "dieselpreis": "1.80",
                      "vignetten_meiden": "", "im_kalender": "on", "notizen": ""}
        for prefix in ["etappen", "buchungen", "kosten", "links", "erinnerungen", "tracks"]:
            daten_post.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0",
                               f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000"})
        daten_post.update({"etappen-TOTAL_FORMS": "1", "etappen-0-datum": "2027-09-01",
                           "etappen-0-von_ort": self.platz_a.pk, "etappen-0-nach_ort": self.platz_b.pk,
                           "etappen-0-pause": "00:00"})
        antwort = self.client.post(reverse("admin:reisen_reise_add"), daten_post)
        self.assertEqual(antwort.status_code, 200)       # Formular mit Fehlern statt Speichern
        self.assertFalse(Reise.objects.filter(titel="Neu").exists())
        daten_post.update({"fahrzeugprofil": "", "etappen-TOTAL_FORMS": "0"})
        self.assertEqual(self.client.post(reverse("admin:reisen_reise_add"), daten_post).status_code, 302)
        self.assertEqual(Reise.objects.get(titel="Neu").familie, self.a)

    def test_gleicher_ortsname_in_zwei_familien_erlaubt_in_einer_nicht(self):
        self.client.force_login(self.anna)
        felder = {"typ": "camping", "adresse": "", "land": "", "website": "", "breite": "1", "laenge": "1",
                  "preise": "", "notizen": ""}
        self.assertEqual(self.client.post(reverse("admin:orte_ort_add"), {**felder, "name": "BBB Platz"}).status_code, 302)
        antwort = self.client.post(reverse("admin:orte_ort_add"), {**felder, "name": "AAA Platz"})
        self.assertContains(antwort, "existiert bereits")

    def test_verwaltung_der_familien_nur_super_admin(self):
        for url in [reverse("admin:konten_familie_changelist"), reverse("admin:konten_person_changelist"),
                    reverse("admin:konten_apischluessel_changelist"), reverse("admin:kalender_schulferien_changelist")]:
            with self.subTest(url):
                self.assertEqual(self.seite(self.anna, url).status_code, 403)
                self.assertEqual(self.seite(self.boss, url).status_code, 200)
        self.assertNotContains(self.seite(self.anna, reverse("admin:index")), "Familien")

    def test_erinnerungen_nur_an_eigene_familie(self):
        versenden(date(2027, 7, 25))
        an = {tuple(m.to): m.body for m in mail.outbox}
        self.assertEqual(set(an), {("anna@example.org",), ("boss@example.org",), ("bert@example.org",)})
        self.assertIn("AAA", an[("anna@example.org",)])
        self.assertNotIn("BBB", an[("anna@example.org",)])
        self.assertNotIn("AAA", an[("bert@example.org",)])

    def test_familie_nie_auswaehlbar(self):
        for person in [self.anna, self.boss]:     # auch der Super-Admin wählt keine fremde Familie
            for name in ["reisen_erinnerung", "reisen_reise", "orte_ort", "fahrzeuge_fahrzeugprofil"]:
                with self.subTest(person=person.name, seite=name):
                    inhalt = self.seite(person, reverse(f"admin:{name}_add")).content.decode()
                    self.assertNotIn('name="familie"', inhalt)
                    self.assertNotIn("Müller", inhalt)
        # auch ein untergeschobenes Feld landet bei der eigenen Familie
        self.client.force_login(self.anna)
        antwort = self.client.post(reverse("admin:reisen_erinnerung_add"),
                                   {"familie": self.b.pk, "datum": "2027-07-01", "text": "Neu", "reise": ""})
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Erinnerung.objects.get(text="Neu").familie, self.a)

    def test_bundesland_bestimmt_feiertage_und_ferien(self):
        # 15.08. Mariä Himmelfahrt: in Bayern (teilweise) Feiertag laut holidays-Paket, in SH nicht
        r_by = Reise.objects.create(familie=self.b, titel="BY", von=date(2027, 11, 1), bis=date(2027, 11, 1))
        r_sh = Reise.objects.create(familie=self.a, titel="SH", von=date(2027, 11, 1), bis=date(2027, 11, 1))
        self.assertEqual((r_by.urlaubstage, r_sh.urlaubstage), (0, 1))   # Allerheiligen nur in Bayern
        Schulferien.objects.create(bundesland="BY", bezeichnung="Herbstferien BY", von=date(2027, 11, 2),
                                   bis=date(2027, 11, 5))
        self.assertIn("Herbstferien BY", self.seite(self.bert, reverse("kalender:jahr", args=[2027])).content.decode())
        self.assertNotIn("Herbstferien BY", self.seite(self.anna, reverse("kalender:jahr", args=[2027])).content.decode())
        self.assertIn("Bayern", self.seite(self.bert, reverse("kalender:jahr", args=[2027])).content.decode())

    def test_ohne_familie(self):
        frei = Person.objects.create_user("frei@example.org", "Frei", is_staff=True)
        self.assertContains(self.seite(frei, reverse("portal:start")), "Noch keiner Familie zugeordnet")
        self.assertEqual(self.seite(frei, reverse("kalender:jahr", args=[2027])).status_code, 404)
        self.assertEqual(self.seite(frei, reverse("admin:reisen_reise_changelist")).status_code, 403)


@override_settings(TOMTOM_API_KEY="standard-key")
class SchluesselTest(TestCase):
    def setUp(self):
        self.eigener = ApiSchluessel.objects.create(name="Müller", schluessel="mueller-key-1234")
        self.a = Familie.objects.create(name="Muster", bundesland="SH")
        self.b = Familie.objects.create(name="Müller", bundesland="BY", api_schluessel=self.eigener)
        self.reise_b, _, _ = daten(self.b, "BBB")

    def test_familie_nutzt_eigenen_oder_standardschluessel(self):
        self.assertEqual(self.a.tomtom(), ("standard-key", None))
        self.assertEqual(self.b.tomtom(), ("mueller-key-1234", self.eigener))
        self.eigener.aktiv = False
        self.eigener.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.tomtom()[0], "standard-key")

    def test_routing_und_kachel_mit_familienschluessel_und_zaehler(self):
        from reisen.routing import reise_routen
        with mock.patch("reisen.routing.requests.get", return_value=Antwort(200, ROUTE)) as get:
            reise_routen(self.reise_b)
        self.assertEqual(get.call_args.kwargs["params"]["key"], "mueller-key-1234")
        person = Person.objects.create_user("bert@example.org", "Bert", familie=self.b, is_staff=True)
        self.client.force_login(person)
        with mock.patch("reisen.routing.requests.get", return_value=mock.Mock(status_code=200, content=b"PNG")) as get:
            self.client.get(reverse("reisen:kachel", args=[5, 1, 1]))
            self.client.get(reverse("reisen:kachel", args=[5, 1, 2]))
        self.assertEqual(get.call_args.kwargs["params"]["key"], "mueller-key-1234")
        zaehler = {(n.art, n.schluessel_id): n.anzahl for n in ApiNutzung.objects.filter(familie=self.b)}
        self.assertEqual(zaehler, {("routing", self.eigener.pk): 1, ("kachel", self.eigener.pk): 2})

    def test_geocoding_mit_standardschluessel_gezaehlt(self):
        from reisen.routing import ort_geocodieren
        ort = Ort.objects.create(familie=self.a, name="Neu", adresse="Irgendwo 1")
        with mock.patch("reisen.routing.requests.get", return_value=Antwort(200, GEO)) as get:
            ort_geocodieren(ort)
        self.assertEqual(get.call_args.kwargs["params"]["key"], "standard-key")
        self.assertEqual(ApiNutzung.objects.get(familie=self.a).art, "geocoding")

    def test_schluessel_wird_nicht_angezeigt(self):
        boss = Person.objects.create_user("boss@example.org", "Boss", familie=self.a, is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        for url in [reverse("admin:konten_apischluessel_changelist"),
                    reverse("admin:konten_apischluessel_change", args=[self.eigener.pk])]:
            with self.subTest(url):
                inhalt = self.client.get(url).content.decode()
                self.assertNotIn("mueller-key-1234", inhalt)
        self.assertIn("…1234", self.client.get(reverse("admin:konten_apischluessel_changelist")).content.decode())
        # Ändern ohne neuen Schlüssel behält den alten
        self.client.post(reverse("admin:konten_apischluessel_change", args=[self.eigener.pk]),
                         {"name": "Müller", "schluessel": "", "aktiv": "on", "notiz": "neu",
                          "kontingent_kacheln": "50000", "kontingent_anfragen": "2500"})
        self.eigener.refresh_from_db()
        self.assertEqual((self.eigener.schluessel, self.eigener.notiz), ("mueller-key-1234", "neu"))


class DatenschutzTest(TestCase):
    @override_settings(BETREIBER_NAME="Max Muster", BETREIBER_EMAIL="max@example.org")
    def test_ohne_anmeldung_erreichbar(self):
        antwort = self.client.get(reverse("portal:datenschutz"))
        self.assertContains(antwort, "Max Muster")
        self.assertContains(antwort, "TomTom")
        self.assertContains(self.client.get(reverse("portal:anmelden")), reverse("portal:datenschutz"))


class NutzungZaehlenTest(TestCase):
    """Kartenkacheln werden parallel geladen – der Zähler darf keine doppelten Zeilen anlegen."""

    def test_eine_zeile_auch_ohne_schluessel(self):
        from django.db import IntegrityError, connection, transaction
        from django.utils import timezone

        f = Familie.objects.create(name="Kachel", bundesland="SH")
        for _ in range(3):
            ApiNutzung.zaehlen(f, None, "kachel")
        self.assertEqual(ApiNutzung.objects.get(familie=f, art="kachel").anzahl, 3)
        if connection.vendor == "postgresql":    # SQLite kennt NULLS NOT DISTINCT nicht
            with self.assertRaises(IntegrityError), transaction.atomic():
                ApiNutzung.objects.create(datum=timezone.localdate(), familie=f, art="kachel")

    def test_kontingent_je_schluessel_und_tag(self):
        from django.utils import timezone

        a = Familie.objects.create(name="Eins", bundesland="SH")
        b = Familie.objects.create(name="Zwei", bundesland="SH")
        eigener = ApiSchluessel.objects.create(name="Eigener", schluessel="x" * 20, kontingent_anfragen=100)
        for familie, art in [(a, "routing"), (b, "routing"), (b, "geocoding"), (a, "kachel")]:
            ApiNutzung.zaehlen(familie, None, art)
        ApiNutzung.zaehlen(a, eigener, "routing")
        heute = timezone.localdate()
        self.assertEqual(ApiNutzung.genutzt(heute, None, "routing"), 3)      # Routing + Suche, beide Familien
        self.assertEqual(ApiNutzung.genutzt(heute, None, "kachel"), 1)
        self.assertEqual(ApiNutzung.genutzt(heute, eigener, "geocoding"), 1)
        self.assertEqual(ApiNutzung.kontingent_von(None, "kachel"), 50000)
        self.assertEqual(ApiNutzung.kontingent_von(eigener, "routing"), 100)
        boss = Person.objects.create_user("boss2@example.org", "Boss", familie=a, is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        seite = self.client.get(reverse("admin:konten_apinutzung_changelist"))
        self.assertContains(seite, "3 von 2.500 (0,1 %)")
        self.assertContains(seite, "1 von 50.000 (0,0 %)")
        self.assertContains(seite, "1 von 100 (1,0 %)")
