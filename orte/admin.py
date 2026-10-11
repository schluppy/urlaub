from django.contrib import admin, messages

from konten.mandant import FamilienMixin
from reisen.routing import TomTomFehler, ort_geocodieren

from .models import Ort


@admin.register(Ort)
class OrtAdmin(FamilienMixin, admin.ModelAdmin):
    list_display = ["name", "typ", "adresse", "land", "hat_koordinaten"]
    list_filter = ["typ", "land"]
    search_fields = ["name", "adresse"]
    actions = ["koordinaten_ermitteln"]
    fieldsets = [
        (None, {"fields": ["name", "typ", "adresse", "land", "website"]}),
        ("Koordinaten", {"fields": [("breite", "laenge")],
                         "description": "Bleiben die Felder leer, ermittelt TomTom sie beim Speichern aus der "
                                        "Adresse. Zum Neuberechnen beide Felder leeren oder die Aktion "
                                        "„Koordinaten aus Adresse ermitteln“ in der Liste nutzen."}),
        ("Preise und Notizen", {"fields": ["preise", "notizen"]}),
    ]

    @admin.display(boolean=True, description="Koordinaten")
    def hat_koordinaten(self, obj):
        return obj.hat_koordinaten

    def save_model(self, request, obj, form, change):
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
