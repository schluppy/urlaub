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
