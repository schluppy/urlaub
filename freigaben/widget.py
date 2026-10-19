"""Daten für das Handy-Widget: die nächsten Reisen mit dem Beginn der ersten Etappe.

Das Widget zählt selbst die Tage herunter und fragt nur einmal am Tag nach. Damit es nach
der Abfahrt ohne Nachfrage zur folgenden Reise wechseln kann, gehen mehrere Reisen mit.
"""
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from reisen.models import Reise

ANZAHL = 3


def beginn(reise):
    """Datum und Uhrzeit der ersten Etappe; ohne Etappen die Abfahrt (Reisezeit von) ohne Uhrzeit."""
    etappen = sorted(reise.etappen.all(), key=lambda e: (e.datum, e.startzeit is None, e.startzeit))
    if etappen:
        return etappen[0].datum, etappen[0].startzeit
    return reise.von, None


def daten(familie):
    heute = timezone.localdate()
    reisen = list(Reise.objects.filter(familie=familie, im_kalender=True).prefetch_related("etappen"))
    kommend = []
    for r in reisen:
        datum, uhrzeit = beginn(r)
        if datum >= heute:
            kommend.append((datum, uhrzeit, r))
    kommend.sort(key=lambda k: (k[0], k[1] is None, k[1]))

    eintraege = []
    for datum, uhrzeit, r in kommend[:ANZAHL]:
        # Der Ring im Widget zeigt die Wartezeit seit der Rückkehr von der Reise davor.
        frueher = [x.bis for x in reisen if x.pk != r.pk and x.bis < datum]
        eintraege.append({
            "titel": r.titel,
            "datum": datum.isoformat(),
            "uhrzeit": uhrzeit.strftime("%H:%M") if uhrzeit else None,
            "warten_seit": max(frueher).isoformat() if frueher else (datum - timedelta(days=365)).isoformat(),
            "link": settings.BASIS_URL + reverse("reisen:reise", args=[r.pk]),
        })
    return {"familie": familie.name, "zeitzone": settings.TIME_ZONE, "stand": timezone.now().isoformat(),
            "reisen": eintraege}
