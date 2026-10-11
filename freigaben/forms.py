from django import forms

from reisen.formulare import DatumEingabe

from .models import Freigabe


class FreigabeForm(forms.ModelForm):
    class Meta:
        model = Freigabe
        fields = ["gueltig_bis", "fuer", "mit_details"]
        widgets = {"gueltig_bis": DatumEingabe}
