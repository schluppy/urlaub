"""Kennzahlen je Familie für den Super-Admin.

Nur Zahlen und Zeitpunkte – keine Titel, Orte oder Texte: die Inhalte
anderer Familien bleiben auch für den Super-Admin verborgen.
"""
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from freigaben.models import Freigabe, Kalenderabo, Widgetzugang
from orte.models import Ort
from reisen.models import Buchung, Erinnerung, Etappe, Reise, Track

from .models import ApiNutzung, Familie, MagicLinkToken, Person


def _je_familie(qs, pfad="familie", **werte):
    """{familie_id: {name: wert}} für die Aggregate in `werte`."""
    return {z.pop(pfad): z for z in qs.values(pfad).annotate(**werte)}


def _spaetester(*zeiten):
    zeiten = [z for z in zeiten if z]
    return max(zeiten) if zeiten else None


def kennzahlen():
    heute = timezone.localdate()
    jetzt = timezone.now()
    seit_30 = jetzt - timedelta(days=30)

    personen = _je_familie(
        Person.objects.all(),
        personen=Count("pk"), aktive_personen=Count("pk", filter=Q(is_active=True)),
        aktiv_30=Count("pk", filter=Q(zuletzt_aktiv__gte=seit_30)),
        zuletzt_aktiv=Max("zuletzt_aktiv"), letzter_login=Max("last_login"))
    orte = _je_familie(Ort.objects.all(), orte=Count("pk"))
    reisen = _je_familie(
        Reise.objects.all(),
        reisen=Count("pk"), reisen_kommend=Count("pk", filter=Q(bis__gte=heute)),
        reisen_laufend=Count("pk", filter=Q(von__lte=heute, bis__gte=heute)))
    etappen = _je_familie(Etappe.objects.all(), "reise__familie", etappen=Count("pk"),
                          km=Sum("entfernung_km"))
    buchungen = _je_familie(Buchung.objects.all(), "reise__familie", buchungen=Count("pk"))
    tracks = _je_familie(Track.objects.all(), "reise__familie", gpx=Count("pk"), gpx_km=Sum("entfernung_km"))
    freigaben = _je_familie(
        Freigabe.objects.all(),
        freigaben=Count("pk"),
        freigaben_aktiv=Count("pk", filter=Q(beendet_am__isnull=True, gueltig_bis__gte=heute)),
        freigaben_aufrufe=Sum("aufrufe"), freigabe_zuletzt=Max("zuletzt_am"))
    abos = _je_familie(
        Kalenderabo.objects.all(), "person__familie",
        abos_aktiv=Count("pk", filter=Q(beendet_am__isnull=True, person__is_active=True)),
        abo_zuletzt=Max("zuletzt_am", filter=Q(beendet_am__isnull=True)))
    # Ein Zugang gilt für Widget und Tracking-App; die Abrufe zählen beide zusammen.
    widget = _je_familie(
        Widgetzugang.objects.all(), "person__familie",
        widget_aktiv=Count("pk", filter=Q(beendet_am__isnull=True, person__is_active=True)),
        widget_abrufe=Sum("abrufe"), widget_zuletzt=Max("zuletzt_am"))
    erinnerungen = _je_familie(
        Erinnerung.objects.all(),
        erinnerungen_offen=Count("pk", filter=Q(erledigt=False, gesendet_am__isnull=True)),
        erinnerungen_gesendet=Count("pk", filter=Q(gesendet_am__isnull=False)))
    tomtom = _je_familie(ApiNutzung.objects.filter(datum__gte=heute - timedelta(days=30)),
                         tomtom_30=Sum("anzahl"))
    bearbeitet = _je_familie(LogEntry.objects.all(), "user__familie", zuletzt_bearbeitet=Max("action_time"),
                             aenderungen_30=Count("pk", filter=Q(action_time__gte=seit_30)))

    zeilen = []
    for familie in Familie.objects.all():
        z = {"familie": familie}
        for quelle in (personen, orte, reisen, etappen, buchungen, tracks, freigaben, abos, widget,
                       erinnerungen, tomtom, bearbeitet):
            z.update(quelle.get(familie.pk, {}))
        z["zuletzt_genutzt"] = _spaetester(z.get("zuletzt_aktiv"), z.get("letzter_login"),
                                           z.get("zuletzt_bearbeitet"))
        zeilen.append(z)
    zeilen.sort(key=lambda z: z["zuletzt_genutzt"] or jetzt.replace(year=1970), reverse=True)

    summen = {}
    for schluessel in ("personen", "aktive_personen", "aktiv_30", "orte", "reisen", "reisen_kommend",
                       "reisen_laufend", "etappen", "km", "buchungen", "gpx", "gpx_km", "freigaben",
                       "freigaben_aktiv", "freigaben_aufrufe", "abos_aktiv", "widget_aktiv", "widget_abrufe", "erinnerungen_offen", "erinnerungen_gesendet",
                       "tomtom_30", "aenderungen_30"):
        summen[schluessel] = sum(z.get(schluessel) or 0 for z in zeilen)

    tokens = MagicLinkToken.objects.filter(erstellt_am__gte=seit_30)
    gesamt = {
        "familien": len(zeilen),
        "ohne_familie": Person.objects.filter(familie__isnull=True).count(),
        "zuletzt_genutzt": _spaetester(*(z["zuletzt_genutzt"] for z in zeilen),
                                       Person.objects.aggregate(m=Max("zuletzt_aktiv"))["m"]),
        "aktiv_heute": Person.objects.filter(zuletzt_aktiv__date=heute).count(),
        "aktiv_7": Person.objects.filter(zuletzt_aktiv__gte=jetzt - timedelta(days=7)).count(),
        "links_30": tokens.count(),
        "logins_30": tokens.filter(verwendet_am__isnull=False).count(),
        "freigabe_zuletzt": Freigabe.objects.aggregate(m=Max("zuletzt_am"))["m"],
        "widget_zuletzt": Widgetzugang.objects.aggregate(m=Max("zuletzt_am"))["m"],
    }
    return {"zeilen": zeilen, "summen": summen, "gesamt": gesamt}
