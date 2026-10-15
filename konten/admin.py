from django import forms
from django.contrib import admin, messages
from django.db import models
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.html import format_html

from .mandant import NurSuperAdmin
from .models import ApiNutzung, ApiSchluessel, Familie, MagicLinkToken, Person


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "email", "familie", "is_active", "is_superuser"]
        labels = {"is_superuser": "Super-Admin"}
        help_texts = {"is_superuser": "legt Familien, Personen und TomTom-Schlüssel an und pflegt die Schulferien"}


@admin.register(Person)
class PersonAdmin(NurSuperAdmin, admin.ModelAdmin):
    form = PersonForm
    list_display = ["name", "email", "familie", "is_active", "is_superuser"]
    list_filter = ["familie", "is_active", "is_superuser"]
    search_fields = ["name", "email"]

    def save_model(self, request, obj, form, change):
        obj.is_staff = True   # alle Personen arbeiten in der Verwaltung, sehen dort aber nur ihre Familie
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


class PersonInline(admin.TabularInline):
    model = Person
    fields = ["name", "email", "is_active"]
    readonly_fields = ["name", "email", "is_active"]
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Familie)
class FamilieAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["name", "bundesland", "schluessel_anzeige", "personen_anzahl", "abrufe_30_tage"]
    list_filter = ["bundesland"]
    search_fields = ["name"]
    fields = ["name", "bundesland", "api_schluessel"]
    inlines = [PersonInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_schluessel").annotate(
            n_personen=Count("personen", distinct=True))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from datetime import date

        from kalender.schulferien import SchulferienFehler, fehlen, laden
        jahre = fehlen(obj.bundesland, [date.today().year, date.today().year + 1])
        if not jahre:
            return
        try:
            neu, _ = laden(obj.bundesland, jahre)
            messages.info(request, f"Schulferien {obj.bundesland_name} {', '.join(map(str, jahre))}: "
                                   f"{len(neu)} Termine abgerufen (OpenHolidays API).")
        except SchulferienFehler as e:
            messages.warning(request, f"Schulferien konnten nicht abgerufen werden: {e} "
                                      "Bitte unter Schulferien → „Schulferien abrufen“ nachholen.")

    @admin.display(description="TomTom-Schlüssel")
    def schluessel_anzeige(self, obj):
        return str(obj.api_schluessel) if obj.api_schluessel else "Standard (.env)"

    @admin.display(description="Personen", ordering="n_personen")
    def personen_anzahl(self, obj):
        return obj.n_personen

    @admin.display(description="TomTom-Abrufe (30 Tage)")
    def abrufe_30_tage(self, obj):
        from datetime import timedelta

        from django.utils import timezone
        seit = timezone.localdate() - timedelta(days=30)
        return obj.apinutzung_set.filter(datum__gte=seit).aggregate(s=Sum("anzahl"))["s"] or 0


class ApiSchluesselForm(forms.ModelForm):
    """Der Schlüssel wird nach dem Speichern nicht wieder angezeigt; leer lassen = unverändert."""

    schluessel = forms.CharField(label="API-Schlüssel", required=False, widget=forms.PasswordInput(render_value=False),
                                 help_text="developer.tomtom.com → Keys. Bei Änderungen leer lassen, um ihn zu behalten.")

    class Meta:
        model = ApiSchluessel
        fields = ["name", "schluessel", "aktiv", "notiz", "kontingent_kacheln", "kontingent_anfragen"]

    def clean_schluessel(self):
        wert = self.cleaned_data["schluessel"].strip()
        if not wert and not self.instance.pk:
            raise forms.ValidationError("Bitte den Schlüssel eintragen.")
        return wert or self.instance.schluessel


@admin.register(ApiSchluessel)
class ApiSchluesselAdmin(NurSuperAdmin, admin.ModelAdmin):
    form = ApiSchluesselForm
    list_display = ["name", "gekuerzt", "aktiv", "familien_liste", "notiz"]

    @admin.display(description="Schlüssel")
    def gekuerzt(self, obj):
        return obj.gekuerzt

    @admin.display(description="Familien")
    def familien_liste(self, obj):
        return ", ".join(f.name for f in obj.familien.all()) or "–"


def _kontingent_text(genutzt, kontingent):
    anteil = genutzt * 100 / kontingent if kontingent else 0
    farbe = "#ba2121" if anteil >= 90 else "#b5651d" if anteil >= 70 else "inherit"
    return format_html('<span style="color:{}">{} von {} ({} %)</span>', farbe, _tausend(genutzt),
                       _tausend(kontingent), f"{anteil:.1f}".replace(".", ","))


def _tausend(n):
    return f"{n:,}".replace(",", ".")


@admin.register(ApiNutzung)
class ApiNutzungAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["datum", "familie", "schluessel_anzeige", "art", "anzahl", "kontingent_anzeige"]
    list_filter = ["art", "familie", "schluessel"]
    date_hierarchy = "datum"

    @admin.display(description="Schlüssel")
    def schluessel_anzeige(self, obj):
        return str(obj.schluessel) if obj.schluessel else "Standard (.env)"

    @admin.display(description="Tageskontingent des Schlüssels")
    def kontingent_anzeige(self, obj):
        """Alle Familien mit diesem Schlüssel an diesem Tag; Routing und Suche teilen sich ein Kontingent."""
        return _kontingent_text(ApiNutzung.genutzt(obj.datum, obj.schluessel, obj.art),
                                ApiNutzung.kontingent_von(obj.schluessel, obj.art))

    def changelist_view(self, request, extra_context=None):
        heute = timezone.localdate()
        schluessel = [None, *ApiSchluessel.objects.filter(
            models.Q(aktiv=True) | models.Q(apinutzung__datum=heute)).distinct()]
        heute_liste = [{
            "name": str(s) if s else "Standard (.env)",
            "kacheln": _kontingent_text(ApiNutzung.genutzt(heute, s, "kachel"), ApiNutzung.kontingent_von(s, "kachel")),
            "anfragen": _kontingent_text(ApiNutzung.genutzt(heute, s, "routing"), ApiNutzung.kontingent_von(s, "routing")),
        } for s in schluessel]
        return super().changelist_view(request, {"kontingente_heute": heute_liste, "heute": heute,
                                                 **(extra_context or {})})

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["person", "erstellt_am", "gueltig_bis", "verwendet_am", "angefordert_von_ip"]
    readonly_fields = [f.name for f in MagicLinkToken._meta.fields]

    def has_add_permission(self, request, *args):
        return False
