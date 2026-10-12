"""Schulferien aus der OpenHolidays API (https://www.openholidaysapi.org, offene Daten).

Regionale Ausnahmen (z. B. in Schleswig-Holstein die Inseln Sylt, Föhr, Amrum, Helgoland und
die Halligen) sind dort als „Exception“ markiert und werden übersprungen. Unterscheidet ein Land
Schularten (Mecklenburg-Vorpommern: allgemeinbildende „…-ABS“ und berufliche Schulen „…-BBS“),
zählen die allgemeinbildenden. Für 2026–2028 SH mit der Seite des Landes abgeglichen (Oktober 2026).
"""
from datetime import date

import requests

from .models import Schulferien

API = "https://openholidaysapi.org/SchoolHolidays"
# Namen wie bisher in der App; der freie Tag nach Christi Himmelfahrt heißt in der API nur „Himmelfahrt“
NAMEN = {"Himmelfahrt": "Ferientag nach Himmelfahrt"}


class SchulferienFehler(Exception):
    pass


def abrufen(bundesland, jahr):
    """[(Bezeichnung, von, bis)] für ein Bundesland (z. B. „SH“) und Kalenderjahr, ohne Ausnahmen."""
    try:
        antwort = requests.get(API, timeout=20, headers={"Accept": "application/json"}, params={
            "countryIsoCode": "DE", "subdivisionCode": f"DE-{bundesland}", "languageIsoCode": "DE",
            "validFrom": f"{jahr}-01-01", "validTo": f"{jahr}-12-31"})
    except requests.RequestException as e:
        raise SchulferienFehler(f"OpenHolidays API nicht erreichbar: {e.__class__.__name__}")
    if antwort.status_code != 200:
        raise SchulferienFehler(f"OpenHolidays API meldet Fehler {antwort.status_code}.")
    ergebnis = []
    for eintrag in antwort.json():
        if "Exception" in (eintrag.get("tags") or []):
            continue   # z. B. Inseln und Halligen
        gruppen = [g.get("code", "") for g in (eintrag.get("groups") or [])]
        if gruppen and not any(g.endswith("-ABS") for g in gruppen):
            continue   # nur berufliche Schulen
        namen = eintrag.get("name") or []
        name = next((n["text"] for n in namen if n.get("language") == "DE"), namen[0]["text"] if namen else "Ferien")
        ergebnis.append((NAMEN.get(name, name), date.fromisoformat(eintrag["startDate"]), date.fromisoformat(eintrag["endDate"])))
    return sorted(set(ergebnis), key=lambda e: e[1])


def laden(bundesland, jahre):
    """Holt und speichert die Ferien; vorhandene Termine (gleiches Bundesland, gleicher Beginn) bleiben.
    `bundesland` ist ein Kürzel oder eine Liste von Kürzeln. Liefert (neu angelegte, schon vorhandene)."""
    if not isinstance(bundesland, str):
        neu, vorhanden = [], []
        for land in bundesland:
            n, v = laden(land, jahre)
            neu += n
            vorhanden += v
        return neu, vorhanden
    neu, vorhanden = [], []
    for jahr in jahre:
        for name, von, bis in abrufen(bundesland, jahr):
            eintrag, angelegt = Schulferien.objects.get_or_create(
                bundesland=bundesland, von=von, defaults={"bezeichnung": name, "bis": bis})
            ziel = neu if angelegt else vorhanden
            if eintrag not in neu + vorhanden:
                ziel.append(eintrag)
    return neu, vorhanden


def fehlen(bundesland, jahre):
    """Jahre, für die in einem Bundesland noch keine Schulferien eingetragen sind."""
    return [j for j in jahre if not Schulferien.objects.filter(bundesland=bundesland, von__year=j).exists()]
