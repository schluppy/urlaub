"""iCalendar-Datei (RFC 5545) mit den Urlauben einer Familie – für Kalender-Abos (Google, Apple, Outlook).

Je Reise ein ganztägiger Termin über den Urlaubszeitraum; Ort ist der Haupturlaubsort
(Platz mit den meisten Nächten, ohne Zwischenübernachtungen, Fähren und Zuhause).
"""
from datetime import timedelta
from datetime import timezone as dt_timezone
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from kalender.tage import zeitraum_text
from reisen.models import Reise


def _text(wert):
    """Text nach RFC 5545 maskieren: \\ ; , und Zeilenumbrüche."""
    return (str(wert).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _falten(zeile):
    """Zeilen länger als 75 Byte umbrechen; Fortsetzungszeilen beginnen mit einem Leerzeichen."""
    teile, aktuell, laenge = [], "", 0
    for zeichen in zeile:
        b = len(zeichen.encode("utf-8"))
        if laenge + b > (75 if not teile else 74):
            teile.append(aktuell)
            aktuell, laenge = "", 0
        aktuell += zeichen
        laenge += b
    teile.append(aktuell)
    return "\r\n ".join(teile)


def ort_text(ort):
    return f"{ort.name}, {ort.adresse}" if ort.adresse else ort.name


def beschreibung(reise, link):
    zeilen = [f"Urlaub {zeitraum_text(reise.urlaub_beginn, reise.urlaub_ende)}"]
    if reise.hat_eigenen_urlaub:
        zeilen.append(f"Unterwegs {reise.von:%d.%m.} – {reise.bis:%d.%m.%Y}"
                      + (" (Abfahrt nach Feierabend)" if reise.abfahrt_feierabend else ""))
    plaetze = []
    for b in sorted((b for b in reise.buchungen.all() if b.status != "storniert"), key=lambda b: b.von):
        plaetze.append(f"{b.von:%d.%m.}–{b.bis:%d.%m.} {b.ort.name} ({b.naechte} {'Nacht' if b.naechte == 1 else 'Nächte'})")
    if plaetze:
        zeilen += ["", "Übernachtungen:"] + plaetze
    zeilen += ["", f"Details: {link}"]
    return "\n".join(zeilen)


def kalender(familie):
    host = urlparse(settings.BASIS_URL).hostname or "urlaubsplaner"
    jetzt = timezone.now().astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Urlaubsplaner//DE", "CALSCALE:GREGORIAN",
              "METHOD:PUBLISH", f"X-WR-CALNAME:{_text('Urlaube ' + familie.name)}", "X-WR-TIMEZONE:Europe/Berlin",
              "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    reisen = (Reise.objects.filter(familie=familie, im_kalender=True).select_related("familie")
              .prefetch_related("buchungen__ort", "etappen__von_ort", "etappen__nach_ort").order_by("von"))
    for r in reisen:
        link = settings.BASIS_URL + reverse("reisen:reise", args=[r.pk])
        ereignis = ["BEGIN:VEVENT", f"UID:reise-{r.pk}@{host}", f"DTSTAMP:{jetzt}",
                    f"DTSTART;VALUE=DATE:{r.urlaub_beginn:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{r.urlaub_ende + timedelta(days=1):%Y%m%d}",   # Ende ist exklusiv
                    f"SUMMARY:{_text(r.titel)}"]
        ort = r.hauptort
        if ort:
            ereignis.append(f"LOCATION:{_text(ort_text(ort))}")
            if ort.hat_koordinaten:
                ereignis.append(f"GEO:{ort.breite};{ort.laenge}")
        ereignis += [f"DESCRIPTION:{_text(beschreibung(r, link))}", f"URL:{link}", "END:VEVENT"]
        zeilen += ereignis
    zeilen.append("END:VCALENDAR")
    return "\r\n".join(_falten(z) for z in zeilen) + "\r\n"
