"""Daten für die Handy-App „Tracking“: die Etappen der nächsten Wochen mit Start- und Zielort.

Die App startet die Aufzeichnung, wenn an einem Etappentag das Auto per Bluetooth verbunden
wird, und beendet sie in der Nähe eines Etappenziels. Gestern geht mit, damit eine Fahrt über
Mitternacht ihr Ziel noch kennt.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from reisen.models import Etappe, Reise

TAGE = 30
REISEN = 5   # so viele Reisen bietet die App zum Hochladen eines Tracks an


def _ort(ort):
    return {
        "name": ort.name,
        "typ": ort.typ,
        "breite": float(ort.breite) if ort.breite is not None else None,
        "laenge": float(ort.laenge) if ort.laenge is not None else None,
    }


def daten(familie):
    heute = timezone.localdate()
    etappen = (Etappe.objects
               .filter(reise__familie=familie, reise__im_kalender=True,
                       datum__gte=heute - timedelta(days=1), datum__lte=heute + timedelta(days=TAGE))
               .select_related("reise", "von_ort", "nach_ort")
               .order_by("datum", "startzeit", "id"))
    return {
        "familie": familie.name, "zeitzone": settings.TIME_ZONE, "stand": timezone.now().isoformat(),
        "etappen": [{
            "reise": e.reise.titel,
            "datum": e.datum.isoformat(),
            "startzeit": e.startzeit.strftime("%H:%M") if e.startzeit else None,
            "von": _ort(e.von_ort),
            "nach": _ort(e.nach_ort),
        } for e in etappen],
    }


def reisen(familie, datum):
    """Reisen zur Auswahl beim Hochladen eines Tracks – die zeitlich nächste zuerst
    (Abstand des Fahrtdatums zur Reisezeit, 0 während der Reise)."""
    def abstand(r):
        return max((r.von - datum).days, (datum - r.bis).days, 0)

    liste = sorted(Reise.objects.filter(familie=familie), key=lambda r: (abstand(r), not r.im_kalender, r.von))
    return {"reisen": [{
        "id": r.pk,
        "titel": r.titel + ("" if r.im_kalender else " (Alternative)"),
        "von": r.von.isoformat(), "bis": r.bis.isoformat(),
    } for r in liste[:REISEN]]}
