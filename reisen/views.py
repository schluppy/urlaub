import math
from datetime import time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from kalender.kalender import MONATSFARBEN
from orte.models import Ortstyp

from . import aufteilen as teilung
from . import dokumente
from . import gpx
from . import mitreise as gemeinsam
from .formulare import AufteilenForm, TeilenForm
from .models import Mitreise, Reise, Track
from .routing import TomTomFehler, kachel, profil_hinweis, reise_routen

KOSTENFARBEN = {"Kraftstoff": "#2F5D8C", "Übernachtungen": "#E39226", "Fähre": "#1F6F8B",
                "Vignette": "#8A4F9E", "Maut": "#6F7F22", "Sonstiges": "#7A4A2E"}


def _laden(request, pk, mitreisend=True):
    """Eigene Reisen und (mit `mitreisend`) gemeinsame, bei denen die Familie mitreist;
    andere Reisen sind „nicht gefunden“."""
    if request.user.familie is None:
        raise Http404
    try:
        return dokumente.reise_laden(pk, request.user.familie, mitreisend=mitreisend)
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
        strecken.append({"punkte": punkte, "gerade": not linie, "text": text, "etappe": e.pk})
    return {"orte": list(orte.values()), "strecken": strecken, "luftlinie": any(s["gerade"] for s in strecken)}


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
        "kosten": list(reise.kosten.all()), "links": list(reise.links.all()), "tracks": list(reise.eigene_tracks().defer("gpx", "linie")),
        "posten": posten, "balken": balken, "hinweise": reise.hinweise(),
        "farbe": MONATSFARBEN[reise.urlaub_beginn.month - 1],
        "karte": kartendaten(reise), "fahrten": gpx.fahrten(reise),
    }


@login_required
def reise(request, pk):
    r = _laden(request, pk)
    return render(request, "reisen/reise.html", _kontext(r))


@require_POST
@login_required
def route(request, pk):
    r = _laden(request, pk, mitreisend=False)   # Etappen pflegt die Familie, der die Reise gehört
    if not r.etappen.exists():
        messages.warning(request, "Diese Reise hat noch keine Etappen.")
        return redirect("reisen:reise", pk)
    if request.POST.get("quelle") == "gpx":
        anzahl, ohne = gpx.reise_aus_tracks(r)
        if anzahl:
            messages.success(request, f"{anzahl} Etappe{'n' if anzahl != 1 else ''} aus GPX-Tracks übernommen.")
        for track in ohne:
            messages.warning(request, f"{track}: keine Etappe am {timezone.localtime(track.beginn):%d.%m.} – nicht übernommen.")
        return redirect("reisen:reise", pk)
    ok, fehler = reise_routen(r)
    if ok:
        messages.success(request, f"{ok} Etappe{'n' if ok != 1 else ''} mit TomTom berechnet.")
    for etappe, text in fehler:
        messages.error(request, f"{etappe}: {text}")
    if hinweis := profil_hinweis(r):
        messages.warning(request, hinweis)
    return redirect("reisen:reise", pk)


@login_required
def aufteilen(request, pk, etappe):
    """Lange Etappe: Haltepunkt nach x Stunden Fahrt zeigen und die Etappe an einem Platz teilen."""
    r = _laden(request, pk, mitreisend=False)
    etappe = next((e for e in r.etappen.all() if e.pk == etappe), None)
    if etappe is None:
        raise Http404
    anfrage = request.POST if request.method == "POST" else request.GET
    form = AufteilenForm(anfrage if "fahrzeit" in anfrage else None, initial={
        "start": etappe.startzeit or time(8),
        "fahrzeit": request.session.get("aufteilen_fahrzeit", "08:00"),
        "pause": etappe.pause})
    vorschlag, orte, teilen_form = None, [], None
    if form.is_bound and form.is_valid():
        d = form.cleaned_data
        request.session["aufteilen_fahrzeit"] = form["fahrzeit"].value()
        try:
            vorschlag = teilung.vorschlag(etappe, d["start"], d["fahrzeit"], d["pause"])
        except TomTomFehler as e:
            messages.error(request, str(e))
    if vorschlag:
        orte = teilung.orte_in_der_naehe(etappe, vorschlag["lat"], vorschlag["lon"])
        teilen_form = TeilenForm(request.POST if request.method == "POST" else None, orte=orte, familie=r.familie,
                                 initial={"weiter_um": request.session.get("aufteilen_weiter", "08:00")})
        if request.method == "POST" and teilen_form.is_valid():
            t = teilen_form.cleaned_data
            request.session["aufteilen_weiter"] = teilen_form["weiter_um"].value()
            if t["ort"]:
                ort = next(o for _, o in orte if o.pk == t["ort"])
            else:
                ort = teilung.neuer_ort(r.familie, t["name"], t["breite"], t["laenge"], t["website"])
            neu, fehler = teilung.teilen(etappe, ort, t["weiter_um"])
            for text in fehler:
                messages.error(request, text)
            if neu.ist_lang:
                messages.success(request, f"Etappe geteilt: Übernachtung in {ort}. Jetzt kannst du den nächsten Tag aufteilen.")
                return redirect("reisen:aufteilen", r.pk, neu.pk)
            messages.success(request, f"Etappe geteilt: Übernachtung in {ort}.")
            return redirect("reisen:reise", r.pk)
    karte = None
    if vorschlag:
        karte = {"orte": [{"name": f"Haltepunkt bei {vorschlag['ort_name']}", "typ": "halt", "lat": vorschlag["lat"], "lon": vorschlag["lon"], "website": "",
                           "aufenthalte": [], "sterne": ""}]
                 + [{"name": o.name, "typ": o.typ, "lat": float(o.breite), "lon": float(o.laenge),
                     "website": o.website, "aufenthalte": [f"{d} km vom Haltepunkt"], "sterne": o.sterne}
                    for d, o in orte],
                 "strecken": [{"punkte": vorschlag["linie"], "gerade": False, "text": str(etappe)},
                              {"punkte": vorschlag["bereich"], "gerade": False, "farbe": "#E39226", "breite": 8,
                               "text": "Hier lohnt die Suche"}],
                 "ausschnitt": vorschlag["bereich"]}
    return render(request, "reisen/aufteilen.html", {
        "reise": r, "etappe": etappe, "form": form, "vorschlag": vorschlag, "teilen_form": teilen_form,
        "folgetag": etappe.datum + timedelta(days=1), "karte": karte, "farbe": MONATSFARBEN[r.urlaub_beginn.month - 1]})


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
def track_gpx(request, pk, track):
    """Hochgeladenen GPX-Track unverändert herunterladen – nur eigene Tracks (bei gemeinsamen Reisen
    hat jede Familie ihre eigenen)."""
    familie = request.user.familie
    if familie is None:
        raise Http404
    t = Track.objects.filter(Q(mitreise__isnull=True, reise__familie=familie) | Q(mitreise__familie=familie),
                             pk=track, reise_id=pk).first()
    if t is None:
        raise Http404
    return _datei(t.gpx, t.dateiname, "application/gpx+xml")


@login_required
def pdf(request, pk):
    r = _laden(request, pk)
    stand = dokumente.stand_jetzt()
    return _datei(dokumente.pdf(r, _kontext(r), stand), dokumente.dateiname(r, "pdf", stand), "application/pdf",
                  anzeigen=True)


# --- Gemeinsam reisen: Einladung an eine andere Familie ---------------------------


@require_POST
@login_required
def einladen(request, pk):
    """Eine Person einladen – angenommen wird für ihre ganze Familie; alle Mitglieder bekommen eine Mail."""
    from konten.models import Person
    from portal import mails

    r = _laden(request, pk, mitreisend=False)
    zurueck = reverse("freigaben:reise", args=[pk]) + "#gemeinsam"
    email = (request.POST.get("email") or "").strip().lower()
    person = Person.objects.filter(email=email, is_active=True, familie__isnull=False).select_related("familie").first()
    if person is None:
        messages.error(request, f"Unter „{email}“ ist niemand im Urlaubsplaner angemeldet.")
        return redirect(zurueck)
    if person.familie_id == r.familie_id:
        messages.error(request, f"{person} gehört zu eurer Familie und sieht die Reise schon.")
        return redirect(zurueck)
    try:
        with transaction.atomic():
            m = Mitreise.objects.create(reise=r, familie=person.familie, eingeladen_von=request.user,
                                        dieselpreis=r.dieselpreis)
    except IntegrityError:
        messages.info(request, f"Familie {person.familie} ist schon eingeladen.")
        return redirect(zurueck)
    mails.einladung(m)
    messages.success(request, f"Familie {person.familie} ist eingeladen – alle ihre Mitglieder bekommen eine Mail.")
    return redirect(zurueck)


@require_POST
@login_required
def mitreise_beenden(request, pk):
    """Einladung zurückziehen bzw. Familie aus der gemeinsamen Reise nehmen (Familie der Reise)."""
    if request.user.familie is None:
        raise Http404
    m = get_object_or_404(Mitreise.objects.select_related("familie", "reise"), pk=pk,
                          reise__familie=request.user.familie)
    m.delete()
    messages.success(request, f"Familie {m.familie} sieht „{m.reise.titel}“ nicht mehr.")
    return redirect(reverse("freigaben:reise", args=[m.reise_id]) + "#gemeinsam")


@login_required
def einladung(request, pk):
    """Einladung ansehen, annehmen oder ablehnen – für die eingeladene Familie."""
    if request.user.familie is None:
        raise Http404
    m = get_object_or_404(Mitreise.objects.select_related("reise__familie", "eingeladen_von"), pk=pk,
                          familie=request.user.familie)
    if m.angenommen_am:
        return redirect("reisen:reise", m.reise_id)
    if request.method == "POST":
        if request.POST.get("aktion") == "annehmen":
            m.angenommen_am = timezone.now()
            m.save(update_fields=["angenommen_am"])
            m.buchungen_ergaenzen()
            messages.success(request, f"Ihr reist mit! Euer Fahrzeug, eure Buchungsdetails und Kosten tragt ihr unter "
                                      f"„Bearbeiten“ ein.")
            return redirect("reisen:reise", m.reise_id)
        m.delete()
        messages.info(request, f"Einladung zu „{m.reise.titel}“ abgelehnt.")
        return redirect("portal:start")
    return render(request, "reisen/einladung.html", {"m": m, "reise": m.reise,
                                                     "farbe": MONATSFARBEN[m.reise.urlaub_beginn.month - 1]})
