from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from portal.views import reisen_im_jahr
from reisen.dokumente import stand_jetzt, stempel

from .kalender import jahreskalender

FERIEN_QUELLEN = {"SH": "https://www.schleswig-holstein.de/DE/landesregierung/themen/"
                         "bildung-hochschulen/ferientermine"}


def ferien_quelle(bundesland):
    """Amtliche Ferienseite des Landes, sonst die Übersicht der Kultusministerkonferenz."""
    return FERIEN_QUELLEN.get(bundesland, "https://www.kmk.org/service/ferien.html")


def _kontext(familie, jahr):
    return {**jahreskalender(jahr, reisen_im_jahr(familie, jahr, nur_kalender=True), familie.bundesland),
            "ferien_quelle": ferien_quelle(familie.bundesland)}


def _familie(request):
    if request.user.familie is None:
        raise Http404("Keiner Familie zugeordnet")
    return request.user.familie


@login_required
def start(request):
    return redirect("kalender:jahr", jahr=date.today().year)


@login_required
def jahr(request, jahr):
    return render(request, "kalender/seite.html", {**_kontext(_familie(request), jahr),
                                                    "jahre": range(jahr - 1, jahr + 3)})


# A4 quer: Platz für 31 Tageszeilen bei einzeiliger Fußzeile; jede weitere Fußzeilenzeile kostet Höhe.
ZEILENHOEHE_MM = 5.25
FUSSZEILE_MM = 3.0           # eine zusätzliche Textzeile in der Fußzeile
ZEICHEN_JE_FUSSZEILE = 230   # vorsichtig geschätzt für 6,8 pt Barlow Condensed auf 283 mm


def _zeilenhoehe(kontext):
    """Tageszeilen so hoch wie möglich, ohne dass lange Fußzeilen eine zweite Seite erzwingen."""
    texte = [" · ".join(f"{f['bezeichnung']} {f['zeitraum']}" for f in kontext["ferien"]),
             " · ".join(f"{u['zeitraum']} {u['titel']} (xx Urlaubstage)" for u in kontext["urlaube"])]
    extra = sum(max(0, -(-(len(t) + 40) // ZEICHEN_JE_FUSSZEILE) - 1) for t in texte)
    return round(ZEILENHOEHE_MM - extra * FUSSZEILE_MM / 31, 2)


def kalender_dateiname(jahr, stand):
    return f"Urlaubskalender_{jahr}_{stempel(stand)}.pdf"


def kalender_dokument(familie, jahr, stand=None):
    """Gesetztes Dokument (WeasyPrint) – eine Seite A4 quer, mit Zeitstempel in der Fußzeile."""
    from weasyprint import HTML

    kontext = _kontext(familie, jahr)
    html = render_to_string("kalender/pdf.html", {
        **kontext, "zeilenhoehe": _zeilenhoehe(kontext), "stand": stand or stand_jetzt(),
        "schriften": (settings.BASE_DIR / "static" / "fonts").as_uri()})
    return HTML(string=html, base_url=str(settings.BASE_DIR)).render()


def pdf_erzeugen(familie, jahr, stand=None):
    return kalender_dokument(familie, jahr, stand).write_pdf()


@login_required
def pdf(request, jahr):
    stand = stand_jetzt()
    antwort = HttpResponse(pdf_erzeugen(_familie(request), jahr, stand), content_type="application/pdf")
    antwort["Content-Disposition"] = f'inline; filename="{kalender_dateiname(jahr, stand)}"'
    return antwort
