from django.contrib import admin

from konten.mandant import NurSuperAdmin

from .models import Schulferien


@admin.register(Schulferien)
class SchulferienAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["bezeichnung", "von", "bis", "bundesland"]
    list_filter = ["bundesland"]
    date_hierarchy = "von"
