from django.contrib import admin, messages
from django.db.models import Count, Max, Q

from konten.mandant import FamilienMixin
from reisen.routing import TomTomFehler, ort_geocodieren

from .forms import OrtForm
from .models import Ort


@admin.register(Ort)
class OrtAdmin(FamilienMixin, admin.ModelAdmin):
    form = OrtForm
    list_display = ["name", "typ", "sterne_anzeige", "aufenthalte", "zuletzt", "land", "hat_koordinaten"]
    list_filter = ["typ", "bewertung", "land"]
    radio_fields = {"bewertung": admin.HORIZONTAL}
    search_fields = ["name", "adresse"]
    actions = ["koordinaten_ermitteln"]
    fieldsets = [
        (None, {"fields": ["name", "typ", "bewertung", "adresse", "land", "website"]}),
        ("Koordinaten", {"fields": ["google", ("breite", "laenge")],
                         "description": "Bleiben die Felder leer, ermittelt TomTom sie beim Speichern aus der "
                                        "Adresse. Findet TomTom den Ort nicht richtig, den Link aus Google Maps "
                                        "einfügen oder Breite und Länge von Hand eintragen. Zum Neuberechnen aus "
                                        "der Adresse beide Felder leeren oder die Aktion „Koordinaten aus Adresse "
                                        "ermitteln“ in der Liste nutzen."}),
        ("Preise und Notizen", {"fields": ["preise", "notizen"]}),
    ]

    def get_queryset(self, request):
        # Aufenthalte und letzter Besuch aus den (nicht stornierten) Buchungen
        gueltig = ~Q(buchungen__status="storniert")
        return super().get_queryset(request).annotate(
            n_aufenthalte=Count("buchungen", filter=gueltig), zuletzt_dort=Max("buchungen__bis", filter=gueltig))

    @admin.display(description="Bewertung", ordering="bewertung")
    def sterne_anzeige(self, obj):
        return obj.sterne or "–"

    @admin.display(description="Aufenthalte", ordering="n_aufenthalte")
    def aufenthalte(self, obj):
        return obj.n_aufenthalte or "–"

    @admin.display(description="zuletzt dort", ordering="zuletzt_dort")
    def zuletzt(self, obj):
        return f"{obj.zuletzt_dort:%d.%m.%Y}" if obj.zuletzt_dort else "–"

    @admin.display(boolean=True, description="Koordinaten")
    def hat_koordinaten(self, obj):
        return obj.hat_koordinaten

    def save_model(self, request, obj, form, change):
        if getattr(form, "von_google", False):     # Koordinaten aus Google Maps gehen vor TomTom
            super().save_model(request, obj, form, change)
            messages.info(request, f"Koordinaten aus Google Maps übernommen: {obj.breite}, {obj.laenge}.")
            return
        adresse_neu = change and "adresse" in form.changed_data and not \
            {"breite", "laenge"} & set(form.changed_data)
        if obj.adresse and (not obj.hat_koordinaten or adresse_neu):
            try:
                f = ort_geocodieren(obj, speichern=False)
                messages.info(request, f"Koordinaten von TomTom: {f.adresse} ({f.genauigkeit}).")
            except TomTomFehler as e:
                messages.warning(request, f"Koordinaten nicht ermittelt: {e}")
        super().save_model(request, obj, form, change)

    @admin.action(description="Koordinaten aus Adresse ermitteln (TomTom)")
    def koordinaten_ermitteln(self, request, queryset):
        ok = 0
        for ort in queryset:
            try:
                ort_geocodieren(ort)
                ok += 1
            except TomTomFehler as e:
                messages.error(request, f"{ort}: {e}")
        if ok:
            messages.success(request, f"{ok} Ort{'e' if ok != 1 else ''} aktualisiert.")
