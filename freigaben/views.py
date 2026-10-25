from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from kalender.views import _kontext as kalender_kontext
from kalender.views import kalender_dateiname, kalender_dokument
from reisen import dokumente, gpx
from reisen.dokumente import stand_jetzt
from reisen.models import Reise
from reisen.views import _kontext as reise_kontext
from reisen.views import kartendaten

from . import apk
from .forms import FreigabeForm
from .ical import kalender as ical_kalender
from .models import MAX_TAGE, Art, Freigabe, Kalenderabo, Widgetzugang
from .tracking import daten as tracking_daten_fuer
from .tracking import reisen as tracking_reisen_fuer
from .widget import daten as widget_daten_fuer


def _familie(request):
    if request.user.familie is None:
        raise Http404
    return request.user.familie


def _verwalten(request, art, reise=None, jahr=None):
    """Formular zum Anlegen und Liste der Freigaben einer Reise bzw. eines Kalenderjahrs."""
    familie = _familie(request)
    heute = date.today()
    if art == Art.REISE:
        standard = max(reise.bis, heute) + timedelta(days=7)
        zurueck = reverse("reisen:reise", args=[reise.pk])
        felder = None
    else:
        standard = date(jahr, 12, 31)
        zurueck = reverse("kalender:jahr", args=[jahr])
        felder = ["gueltig_bis", "fuer"]   # der Kalender zeigt ohnehin keine Kosten
    standard = min(standard, heute + timedelta(days=MAX_TAGE))

    form_klasse = FreigabeForm if felder is None else type("KalenderForm", (FreigabeForm,), {
        "Meta": type("Meta", (FreigabeForm.Meta,), {"fields": felder})})
    freigabe = Freigabe(familie=familie, art=art, reise=reise, jahr=jahr, erstellt_von=request.user)
    if request.method == "POST":
        form = form_klasse(request.POST, instance=freigabe)
        if form.is_valid():
            neu = form.save()
            return redirect(f"{request.path}?neu={neu.pk}")
    else:
        form = form_klasse(instance=freigabe, initial={"gueltig_bis": standard})

    vorhandene = Freigabe.objects.filter(familie=familie, art=art, reise=reise, jahr=jahr)
    neu = vorhandene.filter(pk=request.GET.get("neu")).first() if request.GET.get("neu", "").isdigit() else None
    return render(request, "freigaben/teilen.html", {
        "form": form, "titel": reise.titel if reise else f"Urlaubskalender {jahr}", "zurueck": zurueck,
        "neu": neu, "aktive": [f for f in vorhandene if f.aktiv], "alte": [f for f in vorhandene if not f.aktiv][:10],
        "jahr": jahr, "heute": heute, "max_datum": heute + timedelta(days=MAX_TAGE)})


@login_required
def reise_teilen(request, pk):
    reise = get_object_or_404(Reise.objects.filter(familie=_familie(request)), pk=pk)
    return _verwalten(request, Art.REISE, reise=reise)


@login_required
def kalender_teilen(request, jahr):
    return _verwalten(request, Art.KALENDER, jahr=jahr)


@require_POST
@login_required
def beenden(request, pk):
    freigabe = get_object_or_404(Freigabe.objects.filter(familie=_familie(request)), pk=pk)
    freigabe.beenden()
    messages.success(request, f"Der Link für „{freigabe.titel}“{f' ({freigabe.fuer})' if freigabe.fuer else ''} "
                              "funktioniert nicht mehr.")
    ziel = (reverse("freigaben:reise", args=[freigabe.reise_id]) if freigabe.art == Art.REISE
            else reverse("freigaben:kalender", args=[freigabe.jahr]))
    return redirect(ziel)


# --- Öffentliche Ansicht (ohne Anmeldung) ------------------------------------


def _oeffentlich(antwort):
    antwort["X-Robots-Tag"] = "noindex, nofollow"
    antwort["Cache-Control"] = "no-store"     # beendete Links verschwinden auch aus Zwischenspeichern
    return antwort


def _gueltig(request, token):
    freigabe = Freigabe.objects.select_related("familie", "reise").filter(token=token).first()
    if freigabe is None:
        raise Http404
    return freigabe


def ansehen(request, token):
    freigabe = _gueltig(request, token)
    if not freigabe.aktiv:
        return _oeffentlich(render(request, "freigaben/abgelaufen.html", {"beendet": bool(freigabe.beendet_am),
                                                                     "bis": freigabe.gueltig_bis}, status=410))
    freigabe.aufgerufen()
    if freigabe.art == Art.KALENDER:
        kontext = {**kalender_kontext(freigabe.familie, freigabe.jahr), "freigabe": freigabe}
        return _oeffentlich(render(request, "freigaben/kalender.html", kontext))
    reise = dokumente.reise_laden(freigabe.reise_id, freigabe.familie)
    kontext = {**reise_kontext(reise), "freigabe": freigabe, "details": freigabe.mit_details,
               "karte": kartendaten(reise, oeffentlich=True)}
    return _oeffentlich(render(request, "freigaben/reise.html", kontext))


def kalender_pdf(request, token):
    freigabe = _gueltig(request, token)
    if freigabe.art != Art.KALENDER:
        raise Http404
    if not freigabe.aktiv:
        return _oeffentlich(render(request, "freigaben/abgelaufen.html", {"beendet": bool(freigabe.beendet_am),
                                                                     "bis": freigabe.gueltig_bis}, status=410))
    stand = stand_jetzt()
    antwort = HttpResponse(kalender_dokument(freigabe.familie, freigabe.jahr, stand).write_pdf(),
                           content_type="application/pdf")
    antwort["Content-Disposition"] = f'inline; filename="{kalender_dateiname(freigabe.jahr, stand)}"'
    return _oeffentlich(antwort)


# --- Kalender-Abo (iCal, z. B. Google Kalender) --------------------------------


@login_required
def abo(request):
    """Eigenen Abo-Link anzeigen, neu erzeugen oder beenden (je Person höchstens ein aktiver Link)."""
    _familie(request)
    aktiv = request.user.kalenderabos.filter(beendet_am__isnull=True).first()
    if request.method == "POST":
        if aktiv:
            aktiv.beenden()
        if request.POST.get("aktion") == "erzeugen":
            Kalenderabo.objects.create(person=request.user)
            messages.success(request, "Neuer Abo-Link erstellt." + (" Der bisherige funktioniert nicht mehr." if aktiv else ""))
        else:
            messages.success(request, "Der Abo-Link funktioniert nicht mehr. Abonnierte Kalender zeigen keine neuen Daten.")
        return redirect("freigaben:abo")
    return render(request, "freigaben/abo.html", {"abo": aktiv})


def abo_feed(request, token):
    """Die Kalenderdatei – ohne Anmeldung, nur mit gültigem, geheimem Link."""
    abo = Kalenderabo.objects.select_related("person__familie").filter(token=token).first()
    if abo is None or not abo.aktiv:
        raise Http404
    abo.abgerufen()
    antwort = HttpResponse(ical_kalender(abo.person.familie), content_type="text/calendar; charset=utf-8")
    antwort["Content-Disposition"] = 'inline; filename="urlaube.ics"'
    antwort["X-Robots-Tag"] = "noindex, nofollow"
    antwort["Cache-Control"] = "private, max-age=3600"
    return antwort


# --- Handy-Widget (Countdown bis zum nächsten Urlaub) ----------------------------

APK = settings.BASE_DIR / "widget" / "urlaubswidget.apk"


def _zugang_seite(request, ansicht, vorlage, apk):
    """Eigenen Widget-Link anzeigen, neu erzeugen oder beenden – gilt für Widget und Tracking-App."""
    _familie(request)
    aktiv = request.user.widgetzugaenge.filter(beendet_am__isnull=True).first()
    if request.method == "POST":
        if aktiv:
            aktiv.beenden()
        if request.POST.get("aktion") == "erzeugen":
            Widgetzugang.objects.create(person=request.user)
            messages.success(request, "Neuer Widget-Link erstellt." + (" Der bisherige funktioniert nicht mehr." if aktiv else ""))
        else:
            messages.success(request, "Der Widget-Link funktioniert nicht mehr.")
        return redirect(ansicht)
    return render(request, vorlage, {"zugang": aktiv, "apk": apk.exists()})


def _apk(datei, name):
    if not datei.exists():
        raise Http404
    return FileResponse(datei.open("rb"), as_attachment=True, filename=name,
                        content_type="application/vnd.android.package-archive")


def _zugang(token):
    zugang = Widgetzugang.objects.select_related("person__familie").filter(token=token).first()
    if zugang is None or not zugang.aktiv:
        raise Http404
    return zugang


def _zugang_json(token, daten_fuer):
    """JSON für die Handy-Apps – ohne Anmeldung, nur mit gültigem, geheimem Link."""
    zugang = _zugang(token)
    zugang.abgerufen()
    antwort = JsonResponse(daten_fuer(zugang.person.familie), json_dumps_params={"ensure_ascii": False})
    antwort["X-Robots-Tag"] = "noindex, nofollow"
    antwort["Cache-Control"] = "private, no-cache"
    return antwort


@login_required
def widget(request):
    """App herunterladen und eigenen Widget-Link anzeigen, neu erzeugen oder beenden."""
    return _zugang_seite(request, "freigaben:widget", "freigaben/widget.html", APK)


@login_required
def widget_apk(request):
    return _apk(APK, "urlaubswidget.apk")


def _mit_app(daten_fuer, datei, download, token):
    """Ergänzt das JSON um die Version der App auf dem Server – für den Update-Hinweis in der App."""
    def mit_app(familie):
        app = apk.version(datei)
        if app:
            app["download"] = settings.BASIS_URL + reverse(download, args=[token])
        return {**daten_fuer(familie), "app": app}
    return mit_app


def widget_daten(request, token):
    """Die nächsten Reisen als JSON, dazu die Version der App auf dem Server."""
    return _zugang_json(token, _mit_app(widget_daten_fuer, APK, "freigaben:widget_apk_link", token))


def widget_apk_link(request, token):
    """Die App ohne Anmeldung, nur mit gültigem Widget-Link – für den Update-Knopf in der App."""
    _zugang(token)
    return _apk(APK, "urlaubswidget.apk")


# --- Handy-App „Tracking“ (Fahrten automatisch aufzeichnen) ----------------------

TRACKING_APK = settings.BASE_DIR / "widget" / "tracking.apk"


@login_required
def tracking(request):
    """Tracking-App herunterladen und mit dem Widget-Link einrichten."""
    return _zugang_seite(request, "freigaben:tracking", "freigaben/tracking.html", TRACKING_APK)


@login_required
def tracking_apk(request):
    return _apk(TRACKING_APK, "tracking.apk")


def tracking_apk_link(request, token):
    """Die Tracking-App ohne Anmeldung, nur mit gültigem Widget-Link – für den Update-Knopf in der App."""
    _zugang(token)
    return _apk(TRACKING_APK, "tracking.apk")


def tracking_daten(request, token):
    """Die Etappen der nächsten Wochen als JSON, dazu die Version der App auf dem Server."""
    return _zugang_json(token, _mit_app(tracking_daten_fuer, TRACKING_APK, "freigaben:tracking_apk_link", token))


def tracking_reisen(request, token):
    """Die zeitlich nächsten Reisen zum Fahrtdatum (?datum=JJJJ-MM-TT) – Auswahl beim Hochladen."""
    try:
        datum = date.fromisoformat(request.GET.get("datum", ""))
    except ValueError:
        datum = date.today()
    return _zugang_json(token, lambda familie: tracking_reisen_fuer(familie, datum))


@csrf_exempt
@require_POST
def tracking_hochladen(request, token, pk):
    """GPX einer Fahrt (gern gzip-komprimiert) einer Reise hinzufügen. Der geheime Link genügt als Ausweis."""
    reise = get_object_or_404(Reise, pk=pk, familie=_zugang(token).person.familie)
    try:
        track, ersetzt = gpx.speichern(reise, request.read())
    except gpx.GpxFehler as e:
        return JsonResponse({"fehler": str(e)}, status=400)
    etappe = gpx.etappe_fuer(track, list(reise.etappen.select_related("von_ort", "nach_ort")))
    return JsonResponse({
        "reise": reise.titel, "km": float(track.entfernung_km), "ersetzt": ersetzt,
        "etappe": str(etappe) if etappe else None,
    }, status=200 if ersetzt else 201, json_dumps_params={"ensure_ascii": False})
