"""Gemeinsam reisen: welche Reisen eine Familie sieht und wie sie für eine mitreisende Familie aussehen.

Die Reise gehört einer Familie. Eine eingeladene Familie, die angenommen hat, sieht sie vollständig,
aber mit ihren eigenen Angaben (Mitreise): Fahrzeug und Kraftstoffpreis, Notizen, Status und Preise
der Buchungen, Kosten und GPX-Tracks. Urlaubstage zählen nach ihrem Bundesland.
"""
from django.db.models import Prefetch, Q

from .models import Mitreise, MitreiseBuchung, Reise


def angenommen(familie):
    return Mitreise.objects.filter(familie=familie, angenommen_am__isnull=False)


def sichtbar(familie, reisen=None):
    """Eigene Reisen und die, bei denen die Familie mitreist."""
    reisen = Reise.objects.all() if reisen is None else reisen
    return reisen.filter(Q(familie=familie) | Q(pk__in=angenommen(familie).values("reise")))


def _vorgeladen(objekt, name, eintraege):
    """`objekt.<name>.all()` liefert ab jetzt `eintraege`, ohne die Datenbank zu fragen."""
    manager = getattr(objekt, name)
    qs = manager.none()
    qs._result_cache, qs._prefetch_done = list(eintraege), True
    objekt._prefetched_objects_cache[name] = qs   # Schlüssel = related_name


def anwenden(reise, mitreise):
    """Reise in der Sicht der mitreisenden Familie – nur im Speicher."""
    reise.mitreise = mitreise
    reise.fahrzeugprofil = mitreise.fahrzeugprofil
    reise.verbrauch_l_100km = mitreise.verbrauch_l_100km
    reise.dieselpreis = mitreise.dieselpreis
    reise.notizen = mitreise.notizen
    if not hasattr(reise, "_prefetched_objects_cache"):
        reise._prefetched_objects_cache = {}
    eigene = {mb.buchung_id: mb for mb in mitreise.buchungen.all()}
    _vorgeladen(reise, "buchungen", [(eigene.get(b.pk) or MitreiseBuchung()).als_buchung(b)
                                     for b in reise.buchungen.all()])
    _vorgeladen(reise, "kosten", mitreise.kosten.all())
    # Abweichende Fahrzeuge einzelner Etappen und TomTom-Liter gehören zum Gespann der anderen Familie:
    # hier zählt km × eigener Verbrauch.
    etappen = list(reise.etappen.all())
    for e in etappen:
        e.reise = reise
        e.fahrzeugprofil = None
        e.routing_details = {k: v for k, v in (e.routing_details or {}).items() if k != "verbrauch_l"}
    _vorgeladen(reise, "etappen", etappen)
    return reise


def fuer(reisen, familie):
    """Die Reisen so, wie `familie` sie sieht. Fremde Reisen ohne angenommene Einladung fallen weg."""
    reisen = list(reisen)
    fremde = [r.pk for r in reisen if r.familie_id != familie.pk]
    mitreisen = {}
    if fremde:
        mitreisen = {m.reise_id: m for m in angenommen(familie).filter(reise__in=fremde)
                     .select_related("familie", "fahrzeugprofil").prefetch_related("buchungen", "kosten")}
    ergebnis = []
    for r in reisen:
        if r.familie_id == familie.pk:
            ergebnis.append(r)
        elif r.pk in mitreisen:
            ergebnis.append(anwenden(r, mitreisen[r.pk]))
    return ergebnis


def mitreisende(reise):
    """Für die Familie der Reise: wer reist mit (angenommen) bzw. ist eingeladen."""
    return list(reise.mitreisen.select_related("familie").order_by("angenommen_am", "eingeladen_am"))


def prefetch_familie():
    return Prefetch("mitreisen", queryset=Mitreise.objects.filter(angenommen_am__isnull=False)
                    .select_related("familie"), to_attr="mit_dabei")
