"""Alle E-Mails der Anwendung an einer Stelle."""
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from konten.models import MagicLinkToken


def _link(pfad):
    return settings.BASIS_URL + pfad


def _senden(person, betreff, vorlage, kontext):
    kontext = {"person": person, **kontext}
    text = render_to_string(f"portal/mail/{vorlage}.txt", kontext)
    send_mail(betreff, text, settings.DEFAULT_FROM_EMAIL, [person.email])


def anmeldelink(person, ip=None, ziel=""):
    token = MagicLinkToken.erzeugen(person, ip=ip, ziel=ziel)
    _senden(person, "Dein Anmeldelink – Urlaubsplaner", "anmeldelink", {
        "link": _link(reverse("portal:token", args=[token])),
        "minuten": settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN,
    })


def einladung(mitreise):
    """An alle Mitglieder der eingeladenen Familie."""
    reise = mitreise.reise
    for person in mitreise.familie.personen.filter(is_active=True):
        _senden(person, f"Einladung: {reise.titel} – Urlaubsplaner", "einladung", {
            "reise": reise, "von": mitreise.eingeladen_von or f"Familie {reise.familie}",
            "link": _link(reverse("reisen:einladung", args=[mitreise.pk])),
        })
