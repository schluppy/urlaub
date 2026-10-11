from django.contrib import admin

from konten.mandant import FamilienMixin

from .models import Freigabe


@admin.register(Freigabe)
class FreigabeAdmin(FamilienMixin, admin.ModelAdmin):
    list_display = ["__str__", "fuer", "aktiv_anzeige", "aufrufe", "zuletzt_am", "erstellt_von"]
    list_filter = ["art"]
    fields = ["art", "reise", "jahr", "gueltig_bis", "fuer", "mit_details", "aufrufe", "zuletzt_am", "beendet_am"]
    readonly_fields = ["art", "reise", "jahr", "aufrufe", "zuletzt_am", "beendet_am"]
    actions = ["beenden"]

    def has_add_permission(self, request, *args):
        return False   # Freigaben entstehen über „Teilen“ auf der Reise- bzw. Kalenderseite

    @admin.display(boolean=True, description="aktiv")
    def aktiv_anzeige(self, obj):
        return obj.aktiv

    @admin.action(description="Ausgewählte Links beenden")
    def beenden(self, request, queryset):
        for f in queryset:
            f.beenden()
