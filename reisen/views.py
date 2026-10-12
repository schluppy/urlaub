import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from kalender.kalender import MONATSFARBEN
from orte.models import Ortstyp

from . import dokumente
from .models import Reise
from .routing import TomTomFehler, kachel, profil_hinweis, reise_routen

KOSTENFARBEN = {"Diesel": "#2F5D8C", "Übernachtungen": "#E39226", "Fähre": "#1F6F8B",
                "Vignette": "#8A4F9E", "Maut": "#6F7F22", "Sonstiges": "#7A4A2E"}


def _laden(request, pk):
    """Nur Reisen der eigenen Familie; fremde Reisen sind „nicht gefunden“."""
    if request.user.familie is None:
        raise Http404
    try:
        return dokumente.reise_laden(pk, request.user.familie)
    except Reise.DoesNotExist:
        raise Http404


ZUHAUSE_RADIUS_KM = 3   # öffentliche Karte: so weit um Zuhause wird nichts gezeigt


def _km(a, b):
    """Entfernung zweier Punkte [lat, lon] in km (Haversine)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _rand(innen, aussen, mitte, radius):
    """Punkt auf der Strecke innen→außen, der `radius` km von `mitte` entfernt liegt (Bisektion)."""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        t = (lo + hi) / 2
        p = [innen[0] + t * (aussen[0] - innen[0]), innen[1] + t * (aussen[1] - innen[1])]
        lo, hi = (t, hi) if _km(p, mitte) < radius else (lo, t)
    return [round(innen[0] + hi * (aussen[0] - innen[0]), 5), round(innen[1] + hi * (aussen[1] - innen[1]), 5)]


def ohne_zuhause(punkte, zuhause, radius=ZUHAUSE_RADIUS_KM):
    """Streckenpunkte im Umkreis von Zuhause entfernen; an der Kreisgrenze sauber abschneiden,
    damit Anfang und Ende der Linie nicht verraten, wo die Familie wohnt."""
    for mitte in zuhause:
        innen = [_km(p, mitte) < radius for p in punkte]
        if not any(innen):
            continue
        neu = []
        for i, p in enumerate(punkte):
            if innen[i]:
                if i + 1 < len(punkte) and not innen[i + 1]:
                    neu.append(_rand(p, punkte[i + 1], mitte, radius))   # Linie verlässt den Kreis
                continue
            neu.append(p)
            if i + 1 < len(punkte) and innen[i + 1]:
                neu.append(_rand(punkte[i + 1], p, mitte, radius))       # Linie betritt den Kreis
        punkte = neu
    return punkte


def kartendaten(reise, oeffentlich=False):
    """Orte (Markierungen) und Strecken (Linien) für Leaflet. Öffentlich ohne Zuhause."""
    etappen = list(reise.etappen.all())
    orte = {}
    zuhause = {(float(o.breite), float(o.laenge)) for e in etappen for o in (e.von_ort, e.nach_ort)
               if o.typ == Ortstyp.ZUHAUSE and o.hat_koordinaten} if oeffentlich else set()

    def ort_eintragen(ort):
        if oeffentlich and ort.typ == Ortstyp.ZUHAUSE:
            return
        if ort.hat_koordinaten and ort.pk not in orte:
            orte[ort.pk] = {"name": ort.name, "typ": ort.typ, "lat": float(ort.breite), "lon": float(ort.laenge),
                            "website": ort.website, "aufenthalte": [],
                            "sterne": "" if oeffentlich else ort.sterne}

    for e in etappen:
        ort_eintragen(e.von_ort)
        ort_eintragen(e.nach_ort)
    for b in reise.buchungen.all():
        ort_eintragen(b.ort)
    for ort, an, ab in reise.aufenthalte():
        if ort.pk in orte:
            n = (ab - an).days
            orte[ort.pk]["aufenthalte"].append(f"{an:%d.%m.}–{ab:%d.%m.} ({n} {'Nacht' if n == 1 else 'Nächte'})")

    strecken = []
    for e in etappen:
        if not (e.von_ort.hat_koordinaten and e.nach_ort.hat_koordinaten):
            continue
        linie = (e.routing_details or {}).get("linie") or []
        text = f"{e.datum:%d.%m.} {e.von_ort} → {e.nach_ort}"
        if e.entfernung_km:
            text += f" · {e.entfernung_km:.0f} km"
        punkte = linie or [[float(e.von_ort.breite), float(e.von_ort.laenge)],
                           [float(e.nach_ort.breite), float(e.nach_ort.laenge)]]
        if zuhause:
            punkte = ohne_zuhause(punkte, zuhause)
            if len(punkte) < 2:
                continue
        strecken.append({"punkte": punkte, "gerade": not linie, "text": text})
    return {"orte": list(orte.values()), "strecken": strecken}


@require_GET
@login_required
def tomtom_kachel(request, z, x, y):
    try:
        if request.user.familie is None:
            raise ValueError("ohne Familie")
        inhalt = kachel(z, x, y, familie=request.user.familie)
    except ValueError:
        raise Http404
    except TomTomFehler:
        return HttpResponse(status=502)
    antwort = HttpResponse(inhalt, content_type="image/png")
    antwort["Cache-Control"] = "private, max-age=86400"
    return antwort


def _kontext(reise):
    posten = reise.kostenaufstellung()
    gesamt = sum(b for _, b in posten)
    balken, x = [], 0.0
    for name, betrag in posten:
        breite = float(betrag / gesamt * 100) if gesamt else 0
        balken.append({"name": name, "betrag": betrag, "x": x, "breite": breite,
                       "farbe": KOSTENFARBEN.get(name, "#4F6470"), "anteil": round(breite)})
        x += breite
    return {
        "reise": reise, "etappen": list(reise.etappen.all()), "buchungen": list(reise.buchungen.all()),
        "kosten": list(reise.kosten.all()), "links": list(reise.links.all()),
        "posten": posten, "balken": balken, "hinweise": reise.hinweise(),
        "farbe": MONATSFARBEN[reise.urlaub_beginn.month - 1],
        "karte": kartendaten(reise),
    }


@login_required
def reise(request, pk):
    r = _laden(request, pk)
    return render(request, "reisen/reise.html", _kontext(r))


@require_POST
@login_required
def route(request, pk):
    r = _laden(request, pk)
    if not r.etappen.exists():
        messages.warning(request, "Diese Reise hat noch keine Etappen.")
        return redirect("reisen:reise", pk)
    ok, fehler = reise_routen(r)
    if ok:
        messages.success(request, f"{ok} Etappe{'n' if ok != 1 else ''} mit TomTom berechnet.")
    for etappe, text in fehler:
        messages.error(request, f"{etappe}: {text}")
    if hinweis := profil_hinweis(r):
        messages.warning(request, hinweis)
    return redirect("reisen:reise", pk)


def _datei(inhalt, name, typ, anzeigen=False):
    antwort = HttpResponse(inhalt, content_type=typ)
    antwort["Content-Disposition"] = f'{"inline" if anzeigen else "attachment"}; filename="{name}"'
    return antwort


@login_required
def excel(request, pk):
    r = _laden(request, pk)
    stand = dokumente.stand_jetzt()
    return _datei(dokumente.excel(r, stand), dokumente.dateiname(r, "xlsx", stand),
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@login_required
def pdf(request, pk):
    r = _laden(request, pk)
    stand = dokumente.stand_jetzt()
    return _datei(dokumente.pdf(r, _kontext(r), stand), dokumente.dateiname(r, "pdf", stand), "application/pdf",
                  anzeigen=True)
