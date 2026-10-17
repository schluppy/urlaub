"""Zahlen deutsch formatiert: 1.234,56 €, 3.482 km, 6:34 h."""
from datetime import timedelta
from decimal import Decimal

from django import template

register = template.Library()


def _deutsch(zahl, stellen):
    text = f"{zahl:,.{stellen}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


@register.filter
def euro(betrag):
    if betrag is None or betrag == "":
        return "–"
    return f"{_deutsch(Decimal(betrag), 2)} €"


@register.filter
def km(wert):
    if not wert:
        return "–"
    return f"{_deutsch(Decimal(wert), 0)} km"


@register.filter
def zahl(wert, stellen=0):
    if wert is None or wert == "":
        return "–"
    return _deutsch(Decimal(wert), int(stellen))


@register.filter
def dauer(wert):
    """timedelta → „6:34 h“"""
    if not wert:
        return "–"
    minuten = round(wert / timedelta(minutes=1))
    return f"{minuten // 60}:{minuten % 60:02d} h"


@register.simple_tag
def ohne_suche(cl):
    """Adresse der Verwaltungsliste ohne Suchbegriff (Filter bleiben, Seite 1)."""
    from django.contrib.admin.views.main import PAGE_VAR, SEARCH_VAR

    return cl.get_query_string(remove=[SEARCH_VAR, PAGE_VAR])



@register.filter
def vor(zeitpunkt):
    """„vor 3 Tagen“ – nur die größte Einheit."""
    if not zeitpunkt:
        return "nie"
    from django.utils import timezone
    sekunden = (timezone.now() - zeitpunkt).total_seconds()
    for laenge, eins, mehr in [(365 * 86400, "einem Jahr", "Jahren"), (30 * 86400, "einem Monat", "Monaten"),
                               (86400, "einem Tag", "Tagen"), (3600, "einer Stunde", "Stunden"),
                               (60, "einer Minute", "Minuten")]:
        n = int(sekunden // laenge)
        if n >= 1:
            return f"vor {eins}" if n == 1 else f"vor {n} {mehr}"
    return "gerade eben"
