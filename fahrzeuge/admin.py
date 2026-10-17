from django.contrib import admin

from konten.mandant import FamilienMixin

from .models import Fahrzeugprofil


@admin.register(Fahrzeugprofil)
class FahrzeugprofilAdmin(FamilienMixin, admin.ModelAdmin):
    list_display = ["name", "laenge_m", "breite_m", "hoehe_m", "gesamtgewicht_kg",
                    "hoechstgeschwindigkeit_kmh", "verbrauch_l_100km"]
    fieldsets = [
        (None, {"fields": [("name", "art")]}),
        ("Maße und Gewicht (für das Routing)", {"fields": [
            ("laenge_m", "breite_m", "hoehe_m"), ("gesamtgewicht_kg", "achslast_kg", "achszahl"),
            "hoechstgeschwindigkeit_kmh"]}),
        ("Verbrauch", {"fields": ["verbrauch_l_100km", "verbrauchskurve"]}),
        (None, {"fields": ["notizen"]}),
    ]
