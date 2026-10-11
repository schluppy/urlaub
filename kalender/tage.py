"""Feiertage und Urlaubstage – reine Datumslogik ohne Datenbank."""
from datetime import timedelta
from functools import lru_cache

import holidays
from django.conf import settings

# Kurzformen für die Kalenderzellen; alles andere wie vom Paket `holidays` geliefert.
KURZNAMEN = {
    "Erster Mai": "Tag der Arbeit",
    "Erster Weihnachtstag": "1. Weihnachtstag",
    "Zweiter Weihnachtstag": "2. Weihnachtstag",
}


@lru_cache(maxsize=16)
def feiertage(jahr, bundesland=None):
    """Gesetzliche Feiertage {date: Name} für ein Jahr und Bundesland."""
    bundesland = bundesland or settings.BUNDESLAND
    tage = holidays.country_holidays("DE", subdiv=bundesland, years=jahr, language="de")
    return {tag: KURZNAMEN.get(name, name) for tag, name in sorted(tage.items())}


def ist_feiertag(tag, bundesland=None):
    return tag in feiertage(tag.year, bundesland)


def tage_zwischen(von, bis):
    """Alle Tage von … bis einschließlich."""
    tag = von
    while tag <= bis:
        yield tag
        tag += timedelta(days=1)


def urlaubstage(von, bis, bundesland=None):
    """Mo–Fr im Zeitraum, ohne gesetzliche Feiertage des Bundeslands."""
    return sum(1 for t in tage_zwischen(von, bis) if t.weekday() < 5 and not ist_feiertag(t, bundesland))


def wochentag_kurz(tag):
    return ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][tag.weekday()]


def zeitraum_text(von, bis):
    """26.–29.03. bzw. 27.08.–20.09. bzw. 30.12.2026–02.01.2027"""
    if von.year != bis.year:
        return f"{von:%d.%m.%Y}–{bis:%d.%m.%Y}"
    if von == bis:
        return f"{von:%d.%m.}"
    if von.month == bis.month:
        return f"{von:%d.}–{bis:%d.%m.}"
    return f"{von:%d.%m.}–{bis:%d.%m.}"
