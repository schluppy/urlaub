from django import forms

from .google import KeineKoordinaten, koordinaten, runden
from .models import Ort


class KoordinatenFeld(forms.CharField):
    """Breite oder Länge mit Punkt oder Komma und beliebig vielen Nachkommastellen (z. B. 7 aus
    Google Maps); gespeichert wird auf 6 Stellen gerundet – das sind etwa 10 cm."""

    def __init__(self, grenze, **kwargs):
        self.grenze = grenze
        super().__init__(required=False, widget=forms.TextInput(attrs={"size": 14, "inputmode": "decimal"}), **kwargs)

    def to_python(self, value):
        text = (super().to_python(value) or "").strip().replace(",", ".")
        if not text:
            return None
        try:
            wert = runden(text)
        except Exception:
            raise forms.ValidationError("Bitte eine Zahl eingeben, z. B. 50.1110033.")
        if abs(wert) > self.grenze:
            raise forms.ValidationError(f"Erlaubt sind Werte von −{self.grenze} bis {self.grenze}.")
        return wert

    def prepare_value(self, value):
        return "" if value is None else str(value)


class OrtForm(forms.ModelForm):
    breite = KoordinatenFeld(90, label="Breite")
    laenge = KoordinatenFeld(180, label="Länge")
    google = forms.CharField(
        label="Google Maps", required=False, widget=forms.TextInput(attrs={"size": 60}),
        help_text="Link aus Google Maps einfügen (Ort anklicken → „Teilen“ → „Link kopieren“) oder kopierte "
                  "Koordinaten wie „50.1110033, -3.2225803“. Beim Sichern werden Breite und Länge daraus übernommen. "
                  "Am genauesten: in Google Maps mit der rechten Maustaste (am Handy: lange tippen) auf die Einfahrt "
                  "klicken und oben auf die Koordinaten – sie sind dann kopiert.")

    class Meta:
        model = Ort
        fields = "__all__"

    def clean(self):
        daten = super().clean()
        self.von_google = False
        if daten.get("google"):
            try:
                daten["breite"], daten["laenge"] = koordinaten(daten["google"])
                self.von_google = True
            except KeineKoordinaten as e:
                self.add_error("google", str(e))
        elif (daten.get("breite") is None) != (daten.get("laenge") is None):
            self.add_error("laenge" if daten.get("laenge") is None else "breite",
                           "Bitte Breite und Länge eintragen – oder beide leer lassen.")
        return daten
