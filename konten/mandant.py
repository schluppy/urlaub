"""Trennung der Familien in der Verwaltung (Django-Admin).

FamilienMixin: alles, was einer Familie gehört (Reisen, Orte, Fahrzeugprofile, Erinnerungen
und die Inlines einer Reise). Jede Person – auch der Super-Admin – sieht und bearbeitet nur
die Daten der eigenen Familie: Listen, Suche (auch die Autocomplete-Suche), Auswahlfelder,
Eindeutigkeitsprüfung und Speichern.

NurSuperAdmin: Familien, Personen, TomTom-Schlüssel, Nutzung, Schulferien.
"""
from django.contrib.admin import RelatedFieldListFilter


def _hat_familie(modell):
    return any(f.name == "familie" for f in modell._meta.get_fields()) and modell._meta.label != "konten.Person"


class EigeneFamilieFilter(RelatedFieldListFilter):
    """Seitenfilter auf Fahrzeugprofile, Orte … – zur Auswahl stehen nur die der eigenen Familie."""

    def field_choices(self, field, request, model_admin):
        familie = familie_von(request)
        qs = field.related_model._default_manager.filter(familie=familie) if familie else field.related_model.objects.none()
        ordnung = self.field_admin_ordering(field, request, model_admin)
        if ordnung:
            qs = qs.order_by(*ordnung)
        return [(obj.pk, str(obj)) for obj in qs]


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
        if _hat_familie(modell):
            familie = familie_von(request)
            kwargs["queryset"] = modell.objects.filter(familie=familie) if familie else modell.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_list_filter(self, request):
        filter_ = []
        for eintrag in super().get_list_filter(request):
            if isinstance(eintrag, str) and "__" not in eintrag:
                feld = self.model._meta.get_field(eintrag)
                if feld.is_relation and feld.related_model and _hat_familie(feld.related_model):
                    eintrag = (eintrag, EigeneFamilieFilter)
            filter_.append(eintrag)
        return filter_

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        feld = super().formfield_for_dbfield(db_field, request, **kwargs)
        # kein rotes ✕ neben Auswahlfeldern: es löscht den ausgewählten Ort/das Fahrzeug selbst,
        # nicht die Zeile – gelöscht wird in der eigenen Liste
        if feld is not None and hasattr(feld.widget, "can_delete_related"):
            feld.widget.can_delete_related = False
        return feld

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
