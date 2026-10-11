/* Reise-Verwaltung: neue Etappen und Buchungen sinnvoll vorbelegen, Datumsgrenzen setzen.
   - Etappe: Datum = Datum der vorherigen Etappe (bei der ersten: Abfahrtstag),
             Von = Nach der vorherigen Etappe; frühestes Datum = vorherige Etappe.
   - Buchung: nächster noch nicht gebuchter Aufenthalt laut Etappen (Platz, Anreise, Abreise);
             sonst Anreise = Abreise der vorherigen Buchung. Abreise frühestens Anreise + 1.
             Bei Wahl eines Platzes werden Anreise/Abreise aus dessen Aufenthalt übernommen.
             Preis/Nacht ↔ Gesamtpreis: das leere Feld zeigt den umgerechneten Wert als Platzhalter.
   - Alle Daten nur innerhalb der Reisezeit (von … bis), nicht des Urlaubs. */
(function () {
  "use strict";

  function wert(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
  }
  function reiseBeginn() { return wert("id_von"); }   // Reisezeit von
  function reiseEnde() { return wert("id_bis"); }
  function plusTage(iso, tage) {
    if (!iso) return "";
    const d = new Date(iso + "T12:00:00");
    d.setDate(d.getDate() + tage);
    return d.toISOString().slice(0, 10);
  }

  // sichtbare Zeilen eines Inlines in Anzeige-Reihenfolge (ohne Vorlage und gelöschte)
  function zeilen(prefix) {
    return Array.from(document.querySelectorAll("#" + prefix + "-group tr.form-row"))
      .filter((tr) => !tr.classList.contains("empty-form") && tr.id && !tr.id.endsWith("-empty"))
      .filter((tr) => { const del = tr.querySelector("input[name$='-DELETE']"); return !(del && del.checked); });
  }
  function feld(zeile, name) { return zeile.querySelector("[name$='-" + name + "']"); }

  function etappenGrenzen() {
    let vorher = reiseBeginn();
    zeilen("etappen").forEach((z) => {
      const datum = feld(z, "datum");
      if (!datum) return;
      datum.min = vorher || "";
      datum.max = reiseEnde() || "";
      if (datum.value) vorher = datum.value;
    });
  }
  function buchungenGrenzen() {
    zeilen("buchungen").forEach((z) => {
      const von = feld(z, "von"), bis = feld(z, "bis");
      if (!von || !bis) return;
      von.min = reiseBeginn() || ""; von.max = plusTage(reiseEnde(), -1);
      bis.min = von.value ? plusTage(von.value, 1) : (reiseBeginn() || "");
      bis.max = reiseEnde() || "";
    });
  }
  function grenzen() { etappenGrenzen(); buchungenGrenzen(); zeilen("buchungen").forEach(preisHinweis); }

  // Preis/Nacht oder Gesamtpreis: das jeweils andere Feld zeigt den umgerechneten Wert grau an
  function zahl(text) { const n = parseFloat(String(text).replace(",", ".")); return isNaN(n) ? null : n; }
  function preisHinweis(zeile) {
    const ppn = feld(zeile, "preis_pro_nacht"), gesamt = feld(zeile, "gesamtpreis");
    const von = feld(zeile, "von"), bis = feld(zeile, "bis");
    if (!ppn || !gesamt || !von || !bis) return;
    const naechte = von.value && bis.value
      ? Math.round((new Date(bis.value) - new Date(von.value)) / 86400000) : 0;
    const p = zahl(ppn.value), g = zahl(gesamt.value);
    gesamt.placeholder = p !== null && naechte > 0 ? "= " + (p * naechte).toFixed(2) : "";
    ppn.placeholder = g !== null && naechte > 0 ? "≈ " + (g / naechte).toFixed(2) : "";
  }

  // Aufenthalte laut gespeicherten Etappen: [{ort, von, bis}], vom Server als JSON eingebettet
  function aufenthalte() {
    const el = document.getElementById("aufenthalte");
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }
  function inhalt(zeile, name) { const f = feld(zeile, name); return f ? f.value : ""; }
  function gebucht(ausser) {
    return zeilen("buchungen").filter((z) => z !== ausser)
      .map((z) => inhalt(z, "ort") + "|" + inhalt(z, "von"));
  }
  function freierAufenthalt(zeile, ort) {
    const schon = gebucht(zeile);
    return aufenthalte().find((a) => (!ort || String(a.ort) === ort) && !schon.includes(a.ort + "|" + a.von));
  }
  function aufenthaltSetzen(zeile, a) {
    const ort = feld(zeile, "ort"), von = feld(zeile, "von"), bis = feld(zeile, "bis");
    if (!ort || !von || !bis) return;
    if (!ort.value) ort.value = String(a.ort);
    von.value = a.von;
    bis.value = a.bis;
    zeile.dataset.auto = "1";   // Daten stammen aus den Etappen, nicht von Hand
  }

  // Auswahl eines Autocomplete-Felds (select2) aus einem anderen übernehmen
  function ortUebernehmen(quelle, ziel) {
    if (!quelle || !ziel || !quelle.value || ziel.value) return;
    const text = quelle.options[quelle.selectedIndex] ? quelle.options[quelle.selectedIndex].text : "";
    const option = new Option(text, quelle.value, true, true);
    if (window.django && django.jQuery) {
      django.jQuery(ziel).append(option).trigger("change");
    } else {
      ziel.appendChild(option);
    }
  }

  document.addEventListener("formset:added", (ev) => {
    const name = ev.detail && ev.detail.formsetName;
    const neu = ev.target;
    if (name === "etappen") {
      const alle = zeilen("etappen");
      const vorige = alle[alle.indexOf(neu) - 1];
      const datum = feld(neu, "datum");
      if (datum && !datum.value) {
        datum.value = (vorige && feld(vorige, "datum").value) || reiseBeginn();
      }
      if (vorige) ortUebernehmen(feld(vorige, "nach_ort"), feld(neu, "von_ort"));
    } else if (name === "buchungen") {
      const frei = freierAufenthalt(neu, "");
      if (frei) {
        aufenthaltSetzen(neu, frei);
      } else {
        const alle = zeilen("buchungen");
        const vorige = alle[alle.indexOf(neu) - 1];
        const von = feld(neu, "von");
        if (von && !von.value) von.value = (vorige && feld(vorige, "bis").value) || wert("id_von");
      }
    }
    grenzen();
  });

  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el.matches("select[name^='buchungen-'][name$='-ort']") && el.value) {
      const zeile = el.closest("tr");
      const frei = freierAufenthalt(zeile, el.value);
      // nur übernehmen, solange die Daten nicht von Hand gesetzt sind
      if (frei && (!inhalt(zeile, "bis") || zeile.dataset.auto)) aufenthaltSetzen(zeile, frei);
    } else if (el.matches("input[name^='buchungen-'][type=date]")) {
      delete el.closest("tr").dataset.auto;
    }
    if (el.matches("input[type=date], input[name$='-DELETE'], select[name$='-ort']")) grenzen();
  });
  document.addEventListener("input", (ev) => {
    if (ev.target.matches("input[name$='-preis_pro_nacht'], input[name$='-gesamtpreis']")) {
      preisHinweis(ev.target.closest("tr"));
    }
  });
  document.addEventListener("DOMContentLoaded", grenzen);
})();
