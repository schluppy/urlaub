"""Trennung der Familien in der Verwaltung (Django-Admin).

FamilienMixin: alles, was einer Familie gehört (Reisen, Orte, Fahrzeugprofile, Erinnerungen
und die Inlines einer Reise). Jede Person – auch der Super-Admin – sieht und bearbeitet nur
die Daten der eigenen Familie: Listen, Suche (auch die Autocomplete-Suche), Auswahlfelder,
Eindeutigkeitsprüfung und Speichern.

NurSuperAdmin: Familien, Personen, TomTom-Schlüssel, Nutzung, Schulferien.
"""


def familie_von(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    return user.familie


class FamilienMixin:
    familien_pfad = "familie"   # Lookup zur Familie, z. B. "reise__familie" bei Inlines

    def _erlaubt(self, request):
        return familie_von(request) is not None

    def has_module_permission(self, request):
        return self._erlaubt(request)

    def has_view_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_add_permission(self, request, *args):
        return self._erlaubt(request)

    def has_change_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_delete_permission(self, request, obj=None):
        return self._erlaubt(request)

    def get_queryset(self, request):
        familie = familie_von(request)
        qs = super().get_queryset(request)
        return qs.filter(**{self.familien_pfad: familie}) if familie else qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Auswahl (Orte, Fahrzeugprofile, Reisen) nur aus der eigenen Familie – auch bei der Prüfung."""
        modell = db_field.related_model
        if any(f.name == "familie" for f in modell._meta.get_fields()) and modell._meta.label != "konten.Person":
            familie = familie_von(request)
            kwargs["queryset"] = modell.objects.filter(familie=familie) if familie else modell.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        """Die Familie wählt niemand aus – sie ist immer die eigene (gesetzt in _mit_familie)."""
        ausschluss = list(super().get_exclude(request, obj) or [])
        if any(f.name == "familie" for f in self.model._meta.get_fields()) and "familie" not in ausschluss:
            ausschluss.append("familie")
        return ausschluss

    def get_form(self, request, obj=None, **kwargs):
        basis = super().get_form(request, obj, **kwargs)
        return _mit_familie(basis, familie_von(request))

    def get_formset(self, request, obj=None, **kwargs):   # für Inlines
        formset = super().get_formset(request, obj, **kwargs)
        formset.form = _mit_familie(formset.form, familie_von(request))
        return formset


def _mit_familie(formklasse, familie):
    """Formular, das die Familie schon vor der Prüfung setzt – damit greift „Name je Familie eindeutig“."""

    class MitFamilie(formklasse):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if hasattr(self.instance, "familie_id") and not self.instance.familie_id and familie:
                self.instance.familie = familie

        def _get_validation_exclusions(self):
            ausnahmen = super()._get_validation_exclusions()
            ausnahmen.discard("familie")
            return ausnahmen

    MitFamilie.__name__ = formklasse.__name__
    return MitFamilie


class NurSuperAdmin:
    def _erlaubt(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return self._erlaubt(request)

    def has_view_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_add_permission(self, request, *args):
        return self._erlaubt(request)

    def has_change_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_delete_permission(self, request, obj=None):
        return self._erlaubt(request)
