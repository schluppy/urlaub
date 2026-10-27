"""Gemeinsam reisen: eine andere Familie einladen; sie sieht die Reise und pflegt nur ihre eigenen Angaben."""
from datetime import date
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from fahrzeuge.models import Fahrzeugprofil
from freigaben.ical import kalender as ical_kalender
from freigaben.models import Widgetzugang
from konten.models import Familie, Person
from konten.statistik import kennzahlen
from reisen import gpx
from reisen.erinnerungen import anstehend, versenden
from reisen.models import Buchung, Erinnerung, Mitreise, MitreiseBuchung, MitreiseKosten, Reise, Track

from .test_familien import daten
from .test_gpx import FAHRT


def formulardaten(antwort, **ausser):
    """Alle Felder einer Verwaltungsseite mit ihren aktuellen Werten – wie beim Absenden im Browser."""
    werte = {}

    def aufnehmen(form):
        for name in form.fields:
            wert = form[name].value()
            if wert is None or wert is False:
                continue
            werte[form.add_prefix(name)] = "on" if wert is True else wert

    aufnehmen(antwort.context["adminform"].form)
    for inline in antwort.context["inline_admin_formsets"]:
        aufnehmen(inline.formset.management_form)
        for form in inline.formset.forms:
            aufnehmen(form)
    werte.update(ausser)
    return werte


class GemeinsamTest(TestCase):
    def setUp(self):
        self.muster = Familie.objects.create(name="Muster", bundesland="SH")
        self.insel = Familie.objects.create(name="Nachbar", bundesland="BY")
        self.reise, self.platz, _ = daten(self.muster, "AAA")
        self.buchung = self.reise.buchungen.get()
        Buchung.objects.filter(pk=self.buchung.pk).update(buchungsnummer="GEHEIM-1")
        self.reise.notizen = "Notiz der Familie Muster"
        self.reise.save()
        self.anna = Person.objects.create_user("anna@example.org", "Anna", familie=self.muster)
        self.ina = Person.objects.create_user("ina@example.org", "Ina", familie=self.insel)
        self.ole = Person.objects.create_user("ole@example.org", "Ole", familie=self.insel)
        self.profil = Fahrzeugprofil.objects.create(familie=self.insel, name="Nachbargespann",
                                                    verbrauch_l_100km=Decimal("10.0"))

    def einladen(self, email="ole@example.org"):
        self.client.force_login(self.anna)
        return self.client.post(reverse("reisen:einladen", args=[self.reise.pk]), {"email": email}, follow=True)

    def mitreisen(self):
        self.einladen()
        m = Mitreise.objects.get()
        self.client.force_login(self.ina)
        self.client.post(reverse("reisen:einladung", args=[m.pk]), {"aktion": "annehmen"})
        m.refresh_from_db()
        return m

    # --- Einladung ---------------------------------------------------------------

    def test_einladung_per_teilen_an_die_ganze_familie(self):
        self.client.force_login(self.anna)
        self.assertContains(self.client.get(reverse("freigaben:reise", args=[self.reise.pk])), "Familie einladen")
        antwort = self.einladen()
        self.assertContains(antwort, "Familie Nachbar ist eingeladen")
        self.assertContains(antwort, "noch nicht angenommen")
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["ina@example.org", "ole@example.org"])
        m = Mitreise.objects.get()
        self.assertIn(reverse("reisen:einladung", args=[m.pk]), mail.outbox[0].body)
        self.assertIsNone(m.angenommen_am)

        # vor dem Annehmen sieht Familie Nachbar die Reise nicht, aber die Einladung
        self.client.force_login(self.ina)
        self.assertEqual(self.client.get(reverse("reisen:reise", args=[self.reise.pk])).status_code, 404)
        start = self.client.get(reverse("portal:jahr", args=[2027]))
        self.assertContains(start, "möchte „AAA Reise“")
        self.assertNotContains(start, f'href="{reverse("reisen:reise", args=[self.reise.pk])}"')

    def test_einladen_nur_andere_bekannte_familien_und_nur_einmal(self):
        self.assertContains(self.einladen("niemand@example.org"), "ist niemand im Urlaubsplaner angemeldet")
        self.assertContains(self.einladen("anna@example.org"), "gehört zu eurer Familie")
        self.einladen()
        self.assertContains(self.einladen("ina@example.org"), "schon eingeladen")
        self.assertEqual(Mitreise.objects.count(), 1)
        # die eingeladene Familie kann nicht selbst weiter einladen
        m = self.mitreisen()
        self.client.force_login(self.ina)
        self.assertEqual(self.client.post(reverse("reisen:einladen", args=[self.reise.pk]),
                                          {"email": "x@example.org"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("freigaben:reise", args=[self.reise.pk])).status_code, 404)
        self.assertTrue(m.angenommen_am)

    def test_annehmen_zeigt_die_reise_vollstaendig(self):
        m = self.mitreisen()
        self.assertEqual(MitreiseBuchung.objects.filter(mitreise=m).count(), 1)
        for person in (self.ina, self.ole):
            self.client.force_login(person)
            seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
            self.assertContains(seite, "Gemeinsame Reise mit Familie Muster")
            self.assertContains(seite, "AAA Platz")
            self.assertContains(seite, reverse("admin:reisen_mitreise_change", args=[m.pk]))
            self.assertNotContains(seite, "GEHEIM-1")                       # Buchungsnr. der anderen Familie
            self.assertNotContains(seite, "Notiz der Familie Muster")
            self.assertNotContains(seite, reverse("reisen:route", args=[self.reise.pk]))
            self.assertNotContains(seite, reverse("freigaben:reise", args=[self.reise.pk]))
            self.assertContains(self.client.get(reverse("portal:jahr", args=[2027])), "AAA Reise")
            self.assertContains(self.client.get(reverse("kalender:jahr", args=[2027])), "AAA Reise")
            self.assertEqual(self.client.get(reverse("reisen:excel", args=[self.reise.pk])).status_code, 200)
        # Familie Muster sieht, wer mitreist
        self.client.force_login(self.anna)
        self.assertContains(self.client.get(reverse("reisen:reise", args=[self.reise.pk])), "Gemeinsam mit Familie Nachbar")

    def test_ablehnen(self):
        self.einladen()
        m = Mitreise.objects.get()
        self.client.force_login(self.ole)
        self.client.post(reverse("reisen:einladung", args=[m.pk]), {"aktion": "ablehnen"})
        self.assertFalse(Mitreise.objects.exists())
        self.assertEqual(self.client.get(reverse("reisen:reise", args=[self.reise.pk])).status_code, 404)

    def test_einladung_nur_fuer_die_eingeladene_familie(self):
        self.einladen()
        m = Mitreise.objects.get()
        andere = Familie.objects.create(name="Dritte")
        self.client.force_login(Person.objects.create_user("d@example.org", "D", familie=andere))
        self.assertEqual(self.client.post(reverse("reisen:einladung", args=[m.pk]), {"aktion": "annehmen"}).status_code, 404)
        self.client.force_login(self.anna)   # auch die einladende Familie nimmt nicht für die andere an
        self.assertEqual(self.client.post(reverse("reisen:einladung", args=[m.pk]), {"aktion": "annehmen"}).status_code, 404)
        self.assertIsNone(Mitreise.objects.get().angenommen_am)

    def test_entfernen_durch_die_familie_der_reise(self):
        m = self.mitreisen()
        MitreiseKosten.objects.create(mitreise=m, art="faehre", betrag=Decimal(99))
        self.client.force_login(self.ina)   # nicht die Mitreisenden über diesen Weg
        self.assertEqual(self.client.post(reverse("reisen:mitreise_beenden", args=[m.pk])).status_code, 404)
        self.client.force_login(self.anna)
        self.client.post(reverse("reisen:mitreise_beenden", args=[m.pk]))
        self.assertFalse(Mitreise.objects.exists())
        self.assertFalse(MitreiseKosten.objects.exists())
        self.client.force_login(self.ina)
        self.assertEqual(self.client.get(reverse("reisen:reise", args=[self.reise.pk])).status_code, 404)

    # --- Eigene Angaben der Mitreisenden -----------------------------------------------

    def test_eigene_angaben_und_berechnung(self):
        m = self.mitreisen()
        m.fahrzeugprofil, m.dieselpreis, m.notizen = self.profil, Decimal("2.000"), "Notiz Nachbar"
        m.save()
        MitreiseBuchung.objects.filter(mitreise=m).update(preis_pro_nacht=Decimal(50), status="gebucht",
                                                          buchungsnummer="INSEL-7")
        MitreiseKosten.objects.create(mitreise=m, art="faehre", betrag=Decimal(100), notiz="Fähre Insel")
        self.client.force_login(self.ina)
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
        r = seite.context["reise"]
        self.assertEqual(r.buchungen_eur, Decimal(200))                     # 4 Nächte × 50 €
        self.assertEqual(r.kostenpositionen_eur, Decimal(100))
        self.assertEqual(r.dieselpreis, Decimal("2.000"))
        self.assertEqual(r.bundesland, "BY")
        self.assertContains(seite, "INSEL-7")
        self.assertContains(seite, "Notiz Nachbar")
        self.assertContains(seite, "Fähre Insel")
        self.assertContains(seite, "mit Nachbargespann")

        # Familie Muster sieht davon nichts; ihre Reise ist unverändert
        self.client.force_login(self.anna)
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
        r = seite.context["reise"]
        self.assertEqual(r.buchungen_eur, Decimal(120))
        self.assertEqual(r.kostenpositionen_eur, Decimal(0))
        for fremd in ("INSEL-7", "Notiz Nachbar", "Fähre Insel", "Nachbargespann"):
            self.assertNotContains(seite, fremd)
        self.assertEqual(Reise.objects.get(pk=self.reise.pk).notizen, "Notiz der Familie Muster")

    def test_ansicht_laesst_sich_nicht_speichern(self):
        self.mitreisen()
        self.client.force_login(self.ina)
        r = self.client.get(reverse("reisen:reise", args=[self.reise.pk])).context["reise"]
        with self.assertRaises(RuntimeError):
            r.save()

    def test_verwaltung_nur_eigene_abschnitte(self):
        m = self.mitreisen()
        Erinnerung.objects.create(familie=self.muster, reise=self.reise, datum=date(2027, 7, 1), text="Muster-Erinnerung")
        self.client.force_login(self.ina)
        url = reverse("admin:reisen_mitreise_change", args=[m.pk])
        seite = self.client.get(url)
        self.assertEqual(seite.status_code, 200)
        inhalt = seite.content.decode()
        for feld in ("fahrzeugprofil", "dieselpreis", "notizen", "gpx_dateien",
                     "eigene_buchungen-0-status", "eigene_buchungen-0-buchungsnummer", "eigene_buchungen-0-stellplatz",
                     "eigene_buchungen-0-preis_pro_nacht", "eigene_buchungen-0-gesamtpreis",
                     "eigene_buchungen-0-anzahlung", "eigene_buchungen-0-rest_faellig_am"):
            self.assertIn(f'name="{feld}"', inhalt)
        for feld in ("titel", "von", "eigene_buchungen-0-ort", "eigene_buchungen-0-von", "etappen-TOTAL_FORMS",
                     "links-TOTAL_FORMS"):
            self.assertNotIn(f'name="{feld}"', inhalt)
        self.assertNotIn("GEHEIM-1", inhalt)
        self.assertNotIn("Muster-Erinnerung", inhalt)
        self.assertIn("AAA Platz", inhalt)

        werte = formulardaten(seite, fahrzeugprofil=self.profil.pk, notizen="Hund mitnehmen",
                              **{"eigene_buchungen-0-status": "angezahlt", "eigene_buchungen-0-preis_pro_nacht": "=40+5",
                                 "eigene_buchungen-0-anzahlung": "20", "eigene_buchungen-0-rest_faellig_am": "2027-07-25",
                                 "kosten-TOTAL_FORMS": "1", "kosten-0-art": "maut", "kosten-0-betrag": "12.50",
                                 "erinnerungen-TOTAL_FORMS": "1", "erinnerungen-0-datum": "2027-07-10",
                                 "erinnerungen-0-text": "Insel-Erinnerung", "_planer": "1"})
        antwort = self.client.post(url, werte)
        self.assertRedirects(antwort, reverse("reisen:reise", args=[self.reise.pk]), fetch_redirect_response=False)
        m.refresh_from_db()
        self.assertEqual((m.fahrzeugprofil, m.notizen), (self.profil, "Hund mitnehmen"))
        mb = MitreiseBuchung.objects.get(mitreise=m)
        self.assertEqual((mb.status, mb.preis_pro_nacht, mb.anzahlung), ("angezahlt", Decimal(45), Decimal(20)))
        self.assertEqual(MitreiseKosten.objects.get(mitreise=m).betrag, Decimal("12.50"))
        e = Erinnerung.objects.get(text="Insel-Erinnerung")
        self.assertEqual((e.familie, e.reise, e.mitreise), (self.insel, self.reise, m))
        # die Buchung der Familie Muster bleibt, wie sie war
        b = Buchung.objects.get(pk=self.buchung.pk)
        self.assertEqual((b.status, b.preis_pro_nacht, b.buchungsnummer), ("angezahlt", Decimal(30), "GEHEIM-1"))
        # die Reise selbst bleibt der Familie Muster
        self.assertEqual(self.client.get(reverse("admin:reisen_reise_change", args=[self.reise.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("reisen:route", args=[self.reise.pk])).status_code, 404)

    def test_neue_buchung_der_anderen_familie_erscheint(self):
        m = self.mitreisen()
        Buchung.objects.create(reise=self.reise, ort=self.platz, von=date(2027, 8, 6), bis=date(2027, 8, 7))
        self.client.force_login(self.ina)
        r = self.client.get(reverse("reisen:reise", args=[self.reise.pk])).context["reise"]
        self.assertEqual([b.status for b in r.buchungen.all()], ["geplant", "geplant"])
        self.client.get(reverse("admin:reisen_mitreise_change", args=[m.pk]))
        self.assertEqual(MitreiseBuchung.objects.filter(mitreise=m).count(), 2)

    def test_verwaltung_fremder_familien_gesperrt(self):
        m = self.mitreisen()
        self.client.force_login(self.anna)   # die Familie der Reise bearbeitet nicht die Angaben der Mitreisenden
        self.assertEqual(self.client.get(reverse("admin:reisen_mitreise_change", args=[m.pk])).status_code, 302)
        self.client.force_login(self.ina)
        self.assertNotContains(self.client.get(reverse("admin:reisen_mitreise_changelist")), "Muster-Erinnerung")

    def test_nicht_mehr_mitreisen(self):
        m = self.mitreisen()
        self.client.force_login(self.ina)
        self.client.post(reverse("admin:reisen_mitreise_delete", args=[m.pk]), {"post": "yes"})
        self.assertFalse(Mitreise.objects.exists())
        self.assertTrue(Reise.objects.filter(pk=self.reise.pk).exists())

    def test_loeschen_der_reise_verraet_nichts(self):
        m = self.mitreisen()
        Erinnerung.objects.create(familie=self.insel, reise=self.reise, mitreise=m, datum=date(2027, 7, 1),
                                  text="Geheime Insel-Erinnerung")
        self.client.force_login(self.anna)
        seite = self.client.get(reverse("admin:reisen_reise_delete", args=[self.reise.pk]))
        self.assertContains(seite, "Gemeinsame Reise mit Familie Nachbar")
        self.assertNotContains(seite, "Geheime Insel-Erinnerung")
        self.client.post(reverse("admin:reisen_reise_delete", args=[self.reise.pk]), {"post": "yes"})
        self.assertFalse(Mitreise.objects.exists())
        self.assertFalse(Erinnerung.objects.filter(familie=self.insel).exists())

    # --- GPX-Tracks -------------------------------------------------------------------

    def test_tracks_getrennt(self):
        m = self.mitreisen()
        eigener, _ = gpx.speichern(self.reise, FAHRT)
        fremder, _ = gpx.speichern(self.reise, FAHRT, mitreise=m)    # dieselbe Fahrt, aber der anderen Familie
        self.assertNotEqual(eigener.pk, fremder.pk)
        self.client.force_login(self.ina)
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
        self.assertEqual([t.pk for t in seite.context["tracks"]], [fremder.pk])
        self.assertEqual(self.client.get(reverse("reisen:track_gpx", args=[self.reise.pk, fremder.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("reisen:track_gpx", args=[self.reise.pk, eigener.pk])).status_code, 404)
        self.client.force_login(self.anna)
        seite = self.client.get(reverse("reisen:reise", args=[self.reise.pk]))
        self.assertEqual([t.pk for t in seite.context["tracks"]], [eigener.pk])
        self.assertEqual(self.client.get(reverse("reisen:track_gpx", args=[self.reise.pk, fremder.pk])).status_code, 404)
        verwaltung = self.client.get(reverse("admin:reisen_reise_change", args=[self.reise.pk]))
        self.assertEqual(verwaltung.context["inline_admin_formsets"][-1].formset.queryset.count(), 1)

    def test_tracks_aus_der_app_und_der_verwaltung(self):
        m = self.mitreisen()
        zugang = Widgetzugang.objects.create(person=self.ina)
        antwort = self.client.post(reverse("freigaben:tracking_hochladen", args=[zugang.token, self.reise.pk]),
                                   FAHRT, content_type="application/gpx+xml")
        self.assertEqual(antwort.status_code, 201)
        self.assertEqual(Track.objects.get().mitreise, m)
        self.client.force_login(self.ina)
        url = reverse("admin:reisen_mitreise_change", args=[m.pk])
        werte = formulardaten(self.client.get(url), _continue="1")
        werte["gpx_dateien"] = SimpleUploadedFile("Zweite.gpx", FAHRT.replace(b"T14:", b"T16:"))
        self.assertContains(self.client.post(url, werte, follow=True), "Zweite.gpx: 2,2 km")
        self.assertEqual(Track.objects.filter(mitreise=m).count(), 2)

    # --- Handy-Apps, Kalender-Abo, Erinnerungen ------------------------------------------

    def test_widget_tracking_und_kalenderabo(self):
        self.mitreisen()
        zugang = Widgetzugang.objects.create(person=self.ole)
        widget = self.client.get(reverse("freigaben:widget_daten", args=[zugang.token])).json()
        self.assertEqual([r["titel"] for r in widget["reisen"]], ["AAA Reise"])
        reisen = self.client.get(reverse("freigaben:tracking_reisen", args=[zugang.token]) + "?datum=2027-08-03").json()
        self.assertEqual([r["id"] for r in reisen["reisen"]], [self.reise.pk])
        ics = ical_kalender(self.insel)
        self.assertIn("SUMMARY:AAA Reise", ics)
        self.assertEqual(Reise.objects.get(pk=self.reise.pk).ical_version, 0)
        self.assertEqual(Mitreise.objects.get().ical_version, 0)

    def test_erinnerungen_je_familie(self):
        m = self.mitreisen()
        MitreiseBuchung.objects.filter(mitreise=m).update(preis_pro_nacht=Decimal(50), anzahlung=Decimal(0),
                                                          status="gebucht", rest_faellig_am=date(2027, 7, 28))
        heute = date(2027, 7, 26)
        mail.outbox = []
        versenden(heute)
        an = {m.to[0]: m.body for m in mail.outbox}
        self.assertIn("200,00 EUR bis 28.07.2027", an["ina@example.org"])
        self.assertIn("110,00 EUR bis 30.07.2027", an["anna@example.org"])
        self.assertNotIn("200,00", an["anna@example.org"])
        self.assertIn("AAA Reise beginnt in 7 Tagen", an["ina@example.org"])
        # Reisecheck und Restzahlung kommen für jede Familie einmal
        mail.outbox = []
        versenden(heute)
        self.assertEqual(mail.outbox, [])
        self.assertTrue(any(p.art == "rest" for p in anstehend(heute, self.insel)))

    def test_statistik_zaehlt_tracks_bei_der_eigenen_familie(self):
        m = self.mitreisen()
        gpx.speichern(self.reise, FAHRT, mitreise=m)
        zeilen = {z["familie"].name: z for z in kennzahlen()["zeilen"]}
        self.assertEqual(zeilen["Nachbar"]["gpx"], 1)
        self.assertNotIn("gpx", zeilen["Muster"])
