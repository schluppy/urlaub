from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.html import format_html

from kalender.tage import zeitraum_text
from konten.mandant import FamilienMixin
from orte.models import Ort
from portal.templatetags.urlaub import dauer, euro, km

from .formulare import PickerMixin
from .models import Buchung, Erinnerung, Etappe, Kostenposition, Link, Reise
from .routing import profil_hinweis, reise_routen


class EtappeForm(forms.ModelForm):
    class Meta:
        model = Etappe
        fields = "__all__"
        widgets = {"entfernung_km": forms.NumberInput(attrs={"style": "width:7em", "step": "0.1"})}


class EtappeInline(FamilienMixin, PickerMixin, admin.StackedInline):
    """Je Etappe ein Block mit wenigen Zeilen – passt in den Rahmen statt seitlich hinauszuragen."""

    familien_pfad = "reise__familie"
    model = Etappe
    form = EtappeForm
    extra = 0
    fieldsets = [(None, {"fields": [
        ("datum", "von_ort", "nach_ort"),
        ("startzeit", "pause", "fahrzeit", "ankunft_anzeige", "entfernung_km"),
        "routing_anzeige",
    ]})]
    readonly_fields = ["ankunft_anzeige", "routing_anzeige"]
    autocomplete_fields = ["von_ort", "nach_ort"]

    @admin.display(description="Routing")
    def routing_anzeige(self, obj):
        if not obj.pk or not obj.routing_stand:
            return "–"
        return routing_text(obj)

    @admin.display(description="Ankunft")
    def ankunft_anzeige(self, obj):
        a = obj.ankunft if obj.pk else None
        if a is None:
            return "–"
        return f"{a:%H:%M}" if a.date() == obj.datum else f"{a:%d.%m. %H:%M}"


def routing_text(etappe):
    d = etappe.routing_details or {}
    teile = [f"{etappe.routing_stand:%d.%m.%y %H:%M}"]
    if d.get("laender"):
        teile.append(" → ".join(d["laender"]))
    if d.get("vignetten"):
        teile.append("Vignette: " + ", ".join(d["vignetten"]))
    if d.get("faehre"):
        teile.append("Fähre")
    if etappe.tomtom_liter is not None:
        teile.append(f"{etappe.tomtom_liter} L Kraftstoff".replace(".", ","))
    if d.get("verkehr_min"):
        teile.append(f"+{d['verkehr_min']} min Verkehr")
    if not d.get("abfahrt"):
        teile.append("ohne Verkehrsprognose")
    return " · ".join(teile)


class BuchungForm(forms.ModelForm):
    """Währung und Kurs nur bei Fremdwährung (Haken); ohne Haken gilt Euro."""

    fremdwaehrung = forms.BooleanField(label="Fremdwährung", required=False)

    class Meta:
        model = Buchung
        fields = "__all__"
        widgets = {"waehrung": forms.TextInput(attrs={"size": 4, "maxlength": 3}),
                   "wechselkurs": forms.NumberInput(attrs={"style": "width:7em", "step": "0.0001"}),
                   "anzahlung": forms.NumberInput(attrs={"style": "width:7em", "step": "0.01"}),
                   "preis_pro_nacht": forms.NumberInput(attrs={"style": "width:7em", "step": "0.01"}),
                   "gesamtpreis": forms.NumberInput(attrs={"style": "width:7em", "step": "0.01"}),
                   "buchungsnummer": forms.TextInput(attrs={"size": 14})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fremdwaehrung"].initial = self.instance.pk is not None and self.instance.ist_fremdwaehrung

    def clean(self):
        daten = super().clean()
        if not daten.get("fremdwaehrung"):
            daten["waehrung"], daten["wechselkurs"] = "EUR", Decimal(1)
        elif (daten.get("waehrung") or "").upper() in ("", "EUR"):
            self.add_error("waehrung", "Bitte die Fremdwährung angeben, z. B. GBP.")
        return daten


class BuchungInline(FamilienMixin, PickerMixin, admin.StackedInline):
    """Je Buchung ein Block mit wenigen Zeilen statt einer sehr breiten Tabellenzeile."""

    familien_pfad = "reise__familie"
    model = Buchung
    form = BuchungForm
    extra = 0
    fieldsets = [(None, {"fields": [
        ("ort", "von", "bis", "status", "buchungsnummer"),
        ("preis_pro_nacht", "gesamtpreis", "anzahlung", "rest_faellig_am", "fremdwaehrung"),
        ("waehrung", "wechselkurs"),          # nur sichtbar mit Haken „Fremdwährung“ (eingabe.js)
        "summe_anzeige",
    ]})]
    readonly_fields = ["summe_anzeige"]

    def get_formset(self, request, obj=None, **kwargs):
        """Platz nur aus den Übernachtungsorten der gespeicherten Etappen (plus bereits gebuchte)."""
        formset = super().get_formset(request, obj, **kwargs)

        class OhnePlatzLeer(formset.form):
            """Neue Buchungszeile ohne Platz gilt als leer statt als Fehler – sonst blockiert sie das
            Speichern, solange der Platz noch nicht in einer gespeicherten Etappe steht."""

            def has_changed(self):
                if not self.instance.pk and not self.data.get(self.add_prefix("ort")):
                    return False
                return super().has_changed()

        OhnePlatzLeer.__name__ = formset.form.__name__
        formset.form = OhnePlatzLeer     # vor dem Anpassen der Felder: Unterklassen bauen base_fields neu
        feld = formset.form.base_fields["ort"]
        ids = set()
        if obj is not None and obj.pk:
            ids = {ort.pk for ort, _, _ in obj.aufenthalte()} | set(obj.buchungen.values_list("ort_id", flat=True))
        feld.queryset = Ort.objects.filter(pk__in=ids).order_by("name")
        feld.help_text = ("Zur Auswahl stehen die Übernachtungsorte aus den Etappen. Neue Etappen erst speichern; "
                          "Anreise und Abreise werden beim Auswählen aus den Etappen übernommen.")
        # kein „+“/Stift: neue Orte entstehen über die Etappen
        feld.widget.can_add_related = feld.widget.can_change_related = feld.widget.can_view_related = False
        return formset

    @admin.display(description="Nächte / Summe / Rest")
    def summe_anzeige(self, obj):
        if not obj.pk:
            return "–"
        text = f"{obj.naechte} N. · {euro(obj.summe_eur)} · Rest {euro(obj.rest_eur)}"
        if obj.ist_fremdwaehrung:
            text += f" ({obj.summe:.2f} {obj.waehrung})"
        return text


class KostenInline(FamilienMixin, admin.TabularInline):
    familien_pfad = "reise__familie"
    model = Kostenposition
    extra = 0


class LinkInline(FamilienMixin, admin.TabularInline):
    familien_pfad = "reise__familie"
    model = Link
    extra = 0


class ErinnerungInline(FamilienMixin, PickerMixin, admin.TabularInline):
    model = Erinnerung
    extra = 0
    fields = ["datum", "text", "erledigt", "gesendet_am"]
    readonly_fields = ["gesendet_am"]


@admin.register(Erinnerung)
class ErinnerungAdmin(FamilienMixin, PickerMixin, admin.ModelAdmin):
    list_display = ["datum", "text", "reise", "gesendet_am", "erledigt"]
    list_filter = ["erledigt"]
    list_editable = ["erledigt"]
    search_fields = ["text", "reise__titel"]
    autocomplete_fields = ["reise"]
    readonly_fields = ["gesendet_am"]


@admin.register(Reise)
class ReiseAdmin(FamilienMixin, PickerMixin, admin.ModelAdmin):
    list_display = ["titel", "urlaub_anzeige", "von", "bis", "urlaubstage_anzeige", "entfernung_anzeige", "kosten_anzeige",
                    "im_kalender"]
    list_filter = ["im_kalender", "fahrzeugprofil"]
    search_fields = ["titel", "notizen"]
    date_hierarchy = "von"
    save_on_top = True
    inlines = [EtappeInline, BuchungInline, KostenInline, LinkInline, ErinnerungInline]
    fieldsets = [
        (None, {"fields": ["titel", "im_kalender"]}),
        ("Urlaub", {"fields": [("urlaub_von", "urlaub_bis")],
                    "description": "Urlaubstage inkl. Vor- und Nachbereitung – bestimmen Kalender und Urlaubstage."}),
        ("Reisezeit", {"fields": [("von", "bis")],
                       "description": "Mit dem Gespann unterwegs – Grundlage für Etappen, Buchungen und Nächte. "
                                      "Abfahrt an einem Arbeitstag vor dem Urlaub = „Abfahrt nach Feierabend“."}),
        ("Fahrt", {"fields": ["fahrzeugprofil", ("verbrauch_l_100km", "dieselpreis"), "vignetten_meiden"]}),
        ("Berechnet", {"fields": ["berechnet"]}),
        (None, {"fields": ["notizen"]}),
    ]
    readonly_fields = ["berechnet"]

    class Media:
        js = ["reisen/eingabe.js"]

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        # Aufenthalte laut Etappen für die Vorbelegung der Buchungsdaten (eingabe.js)
        context["aufenthalte"] = [{"ort": o.pk, "von": f"{a:%Y-%m-%d}", "bis": f"{b:%Y-%m-%d}"}
                                  for o, a, b in obj.aufenthalte()] if obj and obj.pk else []
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_urls(self):
        return [path("<int:pk>/route/", self.admin_site.admin_view(self.route_aktualisieren),
                     name="reisen_reise_route")] + super().get_urls()

    def route_aktualisieren(self, request, pk):
        if request.method != "POST":
            return redirect("admin:reisen_reise_change", pk)
        reise = get_object_or_404(self.get_queryset(request), pk=pk)
        if not reise.etappen.exists():
            messages.warning(request, "Diese Reise hat noch keine Etappen.")
            return redirect("admin:reisen_reise_change", pk)
        ok, fehler = reise_routen(reise)
        if ok:
            messages.success(request, f"{ok} Etappe{'n' if ok != 1 else ''} mit TomTom berechnet.")
        for etappe, text in fehler:
            messages.error(request, f"{etappe}: {text}")
        if hinweis := profil_hinweis(reise):
            messages.warning(request, hinweis)
        return redirect("admin:reisen_reise_change", pk)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            Prefetch("etappen", queryset=Etappe.objects.select_related("fahrzeugprofil")),
            Prefetch("buchungen", queryset=Buchung.objects.select_related("ort")),
            "kosten").select_related("fahrzeugprofil")

    @admin.display(description="Urlaub", ordering="urlaub_von")
    def urlaub_anzeige(self, obj):
        return zeitraum_text(obj.urlaub_beginn, obj.urlaub_ende) + f" {obj.urlaub_ende:%Y}"

    @admin.display(description="Urlaubstage")
    def urlaubstage_anzeige(self, obj):
        return obj.urlaubstage

    @admin.display(description="Entfernung")
    def entfernung_anzeige(self, obj):
        return km(obj.entfernung_km)

    @admin.display(description="Kosten")
    def kosten_anzeige(self, obj):
        return euro(obj.gesamtkosten)

    @admin.display(description="Übersicht")
    def berechnet(self, obj):
        if not obj.pk:
            return "Wird nach dem Speichern berechnet."
        zeilen = [
            ("Urlaubstage", obj.urlaubstage or "kein Urlaubstag"),
            ("Nächte (Buchungen)", obj.naechte),
            ("Entfernung", km(obj.entfernung_km)),
            ("Fahrzeit", dauer(obj.fahrzeit)),
            ("Kraftstoff", f"{euro(obj.dieselkosten)} ({obj.dieselliter:.0f} L × {obj.dieselpreis} €; {obj.diesel_quelle})"
             if obj.dieselliter else "Verbrauch fehlt (Fahrzeugprofil oder Feld oben)"),
            ("Buchungen", euro(obj.buchungen_eur)),
            ("Weitere Kosten", euro(obj.kostenpositionen_eur)),
            ("Gesamt", euro(obj.gesamtkosten)),
            ("Noch offen", euro(obj.offen_eur)),
        ]
        return format_html("<table>{}</table>", format_html("".join(
            format_html("<tr><th style='padding-right:1em'>{}</th><td>{}</td></tr>", k, v) for k, v in zeilen)))
