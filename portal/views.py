from datetime import date
from decimal import Decimal

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from konten.models import MagicLinkToken, Person
from reisen.erinnerungen import anstehend
from reisen import mitreise as gemeinsam
from reisen.models import Buchung, Etappe, Mitreise

from . import mails


def _ip(request):
    from django.conf import settings

    if settings.HINTER_PROXY and request.META.get("HTTP_X_REAL_IP"):
        return request.META["HTTP_X_REAL_IP"]
    return request.META.get("REMOTE_ADDR")


# --- Anmeldung per Einmal-Link ---------------------------------------------


def anmelden(request):
    if request.user.is_authenticated:
        return redirect("portal:start")
    ziel = request.GET.get("next") or request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(ziel, allowed_hosts={request.get_host()}):
        ziel = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        person = Person.objects.filter(email=email, is_active=True).first()
        if person and not MagicLinkToken.zu_viele_anfragen(person, _ip(request)):
            mails.anmeldelink(person, ip=_ip(request), ziel=ziel)
        # Immer dieselbe Antwort – verrät nicht, welche Adressen hinterlegt sind.
        return redirect("portal:gesendet")
    return render(request, "portal/anmelden.html", {"next": ziel})


def gesendet(request):
    return render(request, "portal/gesendet.html")


def token(request, token):
    """GET zeigt nur einen Knopf: Mail-Programme, die Links vorab öffnen,
    verbrauchen den Einmal-Link so nicht."""
    eintrag = MagicLinkToken.finde_gueltig(token)
    if request.method == "POST":
        person = MagicLinkToken.einloesen(token)
        if person:
            login(request, person, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(eintrag.ziel if eintrag and eintrag.ziel else "portal:start")
        eintrag = None
    return render(request, "portal/token.html", {"eintrag": eintrag})


def datenschutz(request):
    from django.conf import settings
    return render(request, "portal/datenschutz.html", {
        "betreiber": settings.BETREIBER_NAME, "kontakt": settings.BETREIBER_EMAIL})


def anleitung(request):
    """Anleitung für Einsteiger – auch ohne Anmeldung lesbar (erklärt ja die Anmeldung)."""
    from django.conf import settings
    return render(request, "portal/anleitung.html", {
        "link_minuten": settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN,
        "angemeldet_tage": settings.SESSION_COOKIE_AGE // 86400})


@require_POST
def abmelden(request):
    logout(request)
    return redirect("portal:anmelden")


# --- Jahresübersicht (ersetzt das Blatt „Zusammenfassung“) -------------------


def reisen_im_jahr(familie, jahr, nur_kalender=False):
    # Jahr nach Urlaubsbeginn (ohne eigenen Urlaub: Reisebeginn); Reisen der Familie und gemeinsame
    reisen = gemeinsam.sichtbar(familie).select_related("familie").annotate(beginn=Coalesce("urlaub_von", "von")).filter(beginn__year=jahr).order_by(
        "beginn").select_related("fahrzeugprofil").prefetch_related(
        Prefetch("etappen", queryset=Etappe.objects.select_related("fahrzeugprofil")),
        Prefetch("buchungen", queryset=Buchung.objects.select_related("ort")),
        "kosten")
    if nur_kalender:
        reisen = reisen.filter(im_kalender=True)
    return gemeinsam.fuer(reisen, familie)


def _standardjahr(familie):
    naechste = gemeinsam.sichtbar(familie).filter(bis__gte=date.today()).order_by("von").first()
    return naechste.jahr if naechste else date.today().year


@login_required
def start(request, jahr=None):
    familie = request.user.familie
    if familie is None:
        return render(request, "portal/ohne_familie.html")
    jahr = jahr or _standardjahr(familie)
    reisen = reisen_im_jahr(familie, jahr)
    im_kalender = [r for r in reisen if r.im_kalender]
    summen = {
        "urlaubstage": sum(r.urlaubstage for r in im_kalender),
        "entfernung": sum((r.entfernung_km for r in im_kalender), Decimal(0)),
        "naechte": sum(r.naechte for r in im_kalender),
        "kosten": sum((r.gesamtkosten for r in im_kalender), Decimal(0)),
        "offen": sum((r.offen_eur for r in im_kalender), Decimal(0)),
    }
    jahre = sorted({r.jahr for r in gemeinsam.sichtbar(familie).select_related("familie")}
                   | {jahr, date.today().year})
    return render(request, "portal/start.html", {
        "jahr": jahr, "reisen": reisen, "summen": summen, "jahre": jahre,
        "heute": date.today(), "anstehend": anstehend(date.today(), familie),
        "einladungen": Mitreise.objects.filter(familie=familie, angenommen_am__isnull=True)
                                       .select_related("reise__familie", "eingeladen_von"),
    })
