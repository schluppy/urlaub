from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from kalender.views import _kontext as kalender_kontext
from kalender.views import kalender_dokument
from reisen import dokumente
from reisen.models import Reise
from reisen.views import _kontext as reise_kontext
from reisen.views import kartendaten

from .forms import FreigabeForm
from .models import MAX_TAGE, Art, Freigabe


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
    antwort = HttpResponse(kalender_dokument(freigabe.familie, freigabe.jahr).write_pdf(),
                           content_type="application/pdf")
    antwort["Content-Disposition"] = f'inline; filename="Urlaubskalender_{freigabe.jahr}.pdf"'
    return _oeffentlich(antwort)
