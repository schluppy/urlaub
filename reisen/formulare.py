"""Eingabefelder für die Verwaltung: native Datums- und Uhrzeitauswahl des Browsers
(auf dem Handy die gewohnten Picker), Zeiten und Dauern ohne Sekunden."""
import ast
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import capfirst


class DatumEingabe(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class UhrzeitEingabe(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")


class DauerFeld(forms.Field):
    """Dauer als „hh:mm“. Djangos DurationField läse „1:15“ als 1 Minute 15 Sekunden."""

    widget = UhrzeitEingabe
    MUSTER = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")

    def prepare_value(self, value):
        if isinstance(value, timedelta):
            minuten = round(value / timedelta(minutes=1))
            return f"{minuten // 60:02d}:{minuten % 60:02d}"
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, timedelta):
            return value
        treffer = self.MUSTER.match(str(value))
        if not treffer or int(treffer.group(2)) > 59:
            raise ValidationError("Bitte als Stunden:Minuten angeben, z. B. 1:15.", code="invalid")
        return timedelta(hours=int(treffer.group(1)), minutes=int(treffer.group(2)))

    def has_changed(self, initial, data):
        try:
            return self.to_python(data) != self.to_python(self.prepare_value(initial))
        except ValidationError:
            return True


class PreisFeld(forms.DecimalField):
    """Betrag direkt oder als Rechnung wie in Excel: „=24+(2*8)+4+5“ (Komma oder Punkt als Dezimalzeichen).
    eingabe.js rechnet schon beim Verlassen des Felds; hier ist die Rechnung der Rückfall ohne JavaScript."""

    widget = forms.TextInput
    OPERATOREN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                  ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}

    def __init__(self, **kwargs):
        kwargs.setdefault("localize", True)   # Anzeige mit Dezimalkomma: 53,00
        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            text = value.strip().lstrip("=").replace(",", ".")
            if re.search(r"[-+*/()]", text.lstrip("+-")):
                return self.rechnen(text)
            value = text
        return super().to_python(value)

    def rechnen(self, text):
        def wert(knoten):
            if isinstance(knoten, ast.Expression):
                return wert(knoten.body)
            if isinstance(knoten, ast.Constant) and type(knoten.value) in (int, float):
                return Decimal(str(knoten.value))
            if isinstance(knoten, ast.UnaryOp) and isinstance(knoten.op, (ast.UAdd, ast.USub)):
                return -wert(knoten.operand) if isinstance(knoten.op, ast.USub) else wert(knoten.operand)
            if isinstance(knoten, ast.BinOp) and type(knoten.op) in self.OPERATOREN:
                return self.OPERATOREN[type(knoten.op)](wert(knoten.left), wert(knoten.right))
            raise ValueError(knoten)

        try:
            if len(text) > 200:
                raise ValueError(text)
            return wert(ast.parse(text, mode="eval")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (SyntaxError, ValueError, ArithmeticError, InvalidOperation):
            raise ValidationError("Rechnung nicht verständlich – erlaubt sind Zahlen, + − * / und Klammern, "
                                  "z. B. =24+(2*8)+4+5.", code="invalid")


class PickerMixin:
    """Für ModelAdmin und Inlines: Datum, Uhrzeit und Dauer mit nativer Auswahl."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if isinstance(db_field, models.DurationField):
            return DauerFeld(label=capfirst(db_field.verbose_name), required=not db_field.blank,
                             initial=db_field.get_default())
        if isinstance(db_field, models.DateField) and not isinstance(db_field, models.DateTimeField):
            kwargs["widget"] = DatumEingabe
        elif isinstance(db_field, models.TimeField):
            kwargs["widget"] = UhrzeitEingabe
        return super().formfield_for_dbfield(db_field, request, **kwargs)
