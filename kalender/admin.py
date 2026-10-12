from datetime import date

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from konten.mandant import NurSuperAdmin
from konten.models import Bundesland

from .models import Schulferien
from .schulferien import SchulferienFehler, laden


class AbrufForm(forms.Form):
    bundesland = forms.ChoiceField(label="Bundesland", initial="SH",
                                   choices=[("ALLE", "Alle Bundesländer")] + list(Bundesland.choices))
    jahre = forms.CharField(label="Jahre", help_text="durch Komma oder Leerzeichen getrennt, z. B. 2026, 2028")

    def clean_jahre(self):
        teile = self.cleaned_data["jahre"].replace(",", " ").split()
        try:
            jahre = sorted({int(t) for t in teile})
        except ValueError:
            raise forms.ValidationError("Bitte nur Jahreszahlen angeben.")
        if not jahre or any(not 2000 <= j <= date.today().year + 10 for j in jahre):
            raise forms.ValidationError("Bitte Jahre zwischen 2000 und zehn Jahren in der Zukunft angeben.")
        return jahre


@admin.register(Schulferien)
class SchulferienAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["bezeichnung", "von", "bis", "bundesland"]
    list_filter = ["bundesland"]
    date_hierarchy = "von"

    def get_urls(self):
        return [path("abrufen/", self.admin_site.admin_view(self.abrufen), name="kalender_schulferien_abrufen")] \
            + super().get_urls()

    def abrufen(self, request):
        if not self.has_add_permission(request):
            return redirect("admin:index")
        form = AbrufForm(request.POST or None, initial={"jahre": f"{date.today().year}, {date.today().year + 1}"})
        if request.method == "POST" and form.is_valid():
            land, jahre = form.cleaned_data["bundesland"], form.cleaned_data["jahre"]
            try:
                neu, vorhanden = laden(Bundesland.values if land == "ALLE" else land, jahre)
            except SchulferienFehler as e:
                messages.error(request, str(e))
            else:
                name = "Alle Bundesländer" if land == "ALLE" else Bundesland(land).label
                text = f"{name} {', '.join(map(str, jahre))}: {len(neu)} neu"
                if neu and land != "ALLE":
                    text += " (" + "; ".join(f"{f.bezeichnung} {f.von:%d.%m.%Y}–{f.bis:%d.%m.%Y}" for f in neu) + ")"
                messages.success(request, text + f", {len(vorhanden)} schon vorhanden.")
                ziel = request.path.rsplit("abrufen/", 1)[0]
                return redirect(ziel if land == "ALLE" else f"{ziel}?bundesland__exact={land}")
        return TemplateResponse(request, "admin/kalender/schulferien/abrufen.html", {
            **self.admin_site.each_context(request), "form": form, "title": "Schulferien abrufen"})
