/* Reise-Verwaltung: neue Etappen und Buchungen sinnvoll vorbelegen, Datumsgrenzen setzen.
   - Etappe: Datum = Tag nach der letzten Etappe, deren Folgetag noch frei ist und in der Reisezeit
             liegt (bei der ersten: Abfahrtstag); Von = Nach dieser Etappe. Jedes Datum der Reisezeit
             ist wählbar – so lassen sich bei Rundreisen Etappen zwischen Hin- und Rückfahrt einfügen.
             Nach dem Speichern sind die Etappen nach Datum sortiert.
   - Buchungen erst, wenn die Etappen gespeichert sind: Plätze kommen aus den gespeicherten Etappen.
   - „Löschen?“ in einer Zeile: Zeile wird durchgestrichen, neben „Sichern“ steht ein Hinweis
             (der rote Knopf löscht die ganze Reise).
   - Buchung: nächster noch nicht gebuchter Aufenthalt laut Etappen (Platz, Anreise, Abreise);
             sonst Anreise = Abreise der vorherigen Buchung. Abreise frühestens Anreise + 1.
             Bei Wahl eines Platzes werden Anreise/Abreise aus dessen Aufenthalt übernommen.
             Preis/Nacht ↔ Gesamtpreis: das leere Feld zeigt den umgerechneten Wert als Platzhalter.
             Beide Felder rechnen wie Excel: „=24+(2*8)+4+5“ wird beim Verlassen zu 52,00
             (die Rechnung bleibt als Tooltip stehen).
   - Etappen und Buchungen als Blöcke (mehrere Zeilen je Eintrag); Währung und Kurs nur mit Haken „Fremdwährung“.
   - Einklappen: Klick auf die Kopfzeile eines Blocks zeigt nur noch das Wesentliche (Etappe: Datum, Von → Nach;
             Buchung: Platz, Anreise–Abreise, Nächte, Status); „Alle einklappen“ an der Überschrift gilt für alle
             Blöcke und bleibt im Browser gemerkt. Blöcke mit Fehlern bleiben offen.
   - Alle Daten nur innerhalb der Reisezeit (von … bis), nicht des Urlaubs.
   - Zeitraum der Reise: „bis“ startet mit dem „von“-Datum (Urlaub und Reisezeit), die Reisezeit mit dem
             Urlaub – so öffnet die Datumsauswahl nicht beim heutigen Tag. Überschrieben werden nur leere,
             selbst vorbelegte oder zu frühe Felder; von Hand gewählte Daten bleiben. */
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

  // Zeitraum der Reise: Feld → Felder, die es vorbelegt
  const ZEITRAUM = { id_urlaub_von: ["id_urlaub_bis", "id_von"], id_urlaub_bis: ["id_bis"], id_von: ["id_bis"] };
  const BIS_ZU = { id_urlaub_bis: "id_urlaub_von", id_bis: "id_von" };   // „bis“ nicht vor seinem „von“
  function zeitraumVorbelegen(id) {
    const quelle = document.getElementById(id);
    if (!quelle || !quelle.value) return;
    ZEITRAUM[id].forEach((zielId) => {
      const ziel = document.getElementById(zielId);
      if (!ziel) return;
      const zuFrueh = BIS_ZU[zielId] && ziel.value && ziel.value < wert(BIS_ZU[zielId]);
      // vorbelegt: von derselben Quelle nachziehen, von einer anderen nur nach hinten (Reisezeit bis
      // folgt Urlaub bis, eine frühere Abfahrt verkürzt sie nicht)
      const nachziehen = ziel.dataset.vorbelegt && (ziel.dataset.vorbelegt === id || quelle.value > ziel.value);
      if (ziel.value && !nachziehen && !zuFrueh) return;
      ziel.value = quelle.value;
      ziel.dataset.vorbelegt = id;
      if (ZEITRAUM[zielId]) zeitraumVorbelegen(zielId);
    });
  }
  function zeitraumGrenzen() {
    Object.keys(BIS_ZU).forEach((bisId) => {
      const bis = document.getElementById(bisId);
      if (bis) bis.min = wert(BIS_ZU[bisId]);
    });
  }

  // sichtbare Zeilen eines Inlines in Anzeige-Reihenfolge (ohne Vorlage und gelöschte)
  function zeilen(prefix) {
    // Blöcke (StackedInline): div.inline-related; Tabellen (TabularInline): tr.form-row
    return Array.from(document.querySelectorAll("#" + prefix + "-group tr.form-row, #" + prefix + "-group div.inline-related"))
      .filter((tr) => !tr.classList.contains("empty-form") && tr.id && !tr.id.endsWith("-empty"))
      .filter((tr) => { const del = tr.querySelector("input[name$='-DELETE']"); return !(del && del.checked); });
  }
  function feld(zeile, name) { return zeile.querySelector("[name$='-" + name + "']"); }
  // Zeile bzw. Block eines Eingabefelds
  function eintrag(el) { return el.closest("tr.form-row, div.inline-related"); }

  // Währung und Kurs nur mit Haken „Fremdwährung“
  function waehrungZeigen(zeile) {
    const haken = feld(zeile, "fremdwaehrung"), waehrung = feld(zeile, "waehrung");
    if (!haken || !waehrung) return;
    const reihe = waehrung.closest(".form-row");
    if (reihe) reihe.hidden = !haken.checked;
    if (!haken.checked) {
      waehrung.value = "EUR";
      const kurs = feld(zeile, "wechselkurs");
      if (kurs) kurs.value = "1";
    } else if (waehrung.value.toUpperCase() === "EUR") {
      waehrung.value = "";
      waehrung.focus();
    }
  }

  function etappenGrenzen() {
    zeilen("etappen").forEach((z) => {
      const datum = feld(z, "datum");
      if (!datum) return;
      datum.min = reiseBeginn() || "";
      datum.max = reiseEnde() || "";
    });
  }

  // Vorlage für eine neue Etappe: die letzte Etappe, nach der noch ein freier Tag in der Reisezeit liegt
  function etappeDavor(neu) {
    const andere = zeilen("etappen").filter((z) => z !== neu && feld(z, "datum") && feld(z, "datum").value);
    const tage = new Set(andere.map((z) => feld(z, "datum").value));
    const ende = reiseEnde();
    const passend = andere.filter((z) => {
      const folgetag = plusTage(feld(z, "datum").value, 1);
      return !tage.has(folgetag) && (!ende || folgetag <= ende);
    });
    // spätestes Datum; bei mehreren Etappen am selben Tag die letzte in der Liste
    passend.sort((a, b) => feld(a, "datum").value.localeCompare(feld(b, "datum").value));
    return passend[passend.length - 1];
  }

  // Buchungen sperren, solange Etappen nicht gespeichert sind. Verglichen werden die Werte mit dem
  // geladenen Stand – nicht Ereignisse, denn Django löst beim Laden selbst „change“ auf Auswahlfeldern aus.
  let etappenStand = null;
  function etappenWerte() {
    const werte = {};
    document.querySelectorAll("#etappen-group input, #etappen-group select").forEach((el) => {
      if (!el.name || el.name.includes("__prefix__")) return;
      werte[el.name] = el.type === "checkbox" ? el.checked : el.value;
    });
    return werte;
  }
  function etappenOffen() {
    if (zeilen("etappen").some((z) => {
      const id = z.querySelector("input[name$='-id']");
      return !id || !id.value;   // neue, noch nicht gespeicherte Zeile
    })) return true;
    if (!etappenStand) return false;
    const jetzt = etappenWerte();
    return Object.keys(jetzt).some((name) => jetzt[name] !== etappenStand[name]);
  }
  function buchungenSperre() {
    const gruppe = document.getElementById("buchungen-group");
    if (!gruppe) return;
    let grund = "";
    if (etappenOffen()) grund = "Neue Buchungen erst nach dem Speichern der Etappen – die Plätze kommen aus den gespeicherten Etappen.";
    else if (!aufenthalte().length) grund = "Neue Buchungen erst, wenn Etappen mit Übernachtungen gespeichert sind.";
    gruppe.classList.toggle("buchung-gesperrt", !!grund);
    let hinweis = gruppe.querySelector(".buchung-hinweis");
    if (grund && !hinweis) {
      hinweis = document.createElement("p");
      hinweis.className = "buchung-hinweis help";
      gruppe.appendChild(hinweis);
    }
    if (hinweis) { hinweis.textContent = grund; hinweis.hidden = !grund; }
  }
  function sperrStil() {
    if (document.getElementById("buchung-sperre-stil")) return;
    const stil = document.createElement("style");
    stil.id = "buchung-sperre-stil";
    stil.textContent = "#buchungen-group.buchung-gesperrt .add-row { display: none; }" +
      " .buchung-hinweis { margin: 6px 10px 10px; font-weight: 600; color: #b5651d; }" +
      " tr.zum-loeschen td, .inline-related.zum-loeschen fieldset { text-decoration: line-through; opacity: .55; }" +
      " .loesch-hinweis { flex-basis: 100%; margin: 4px 0 0; font-weight: 600; color: #ba2121; }";
    (document.head || document.documentElement).appendChild(stil);
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
  function grenzen() { etappenGrenzen(); buchungenGrenzen(); zeilen("buchungen").forEach(preisHinweis); buchungenSperre(); }

  // Rechnung wie in Excel: Zahlen (Komma oder Punkt), + - * / und Klammern; sonst null
  function rechnen(text) {
    const zeichen = String(text).replace(/^\s*=/, "").replace(/,/g, ".").match(/\d+(?:\.\d*)?|\.\d+|[-+*\/()]|\S/g) || [];
    let i = 0;
    function summe() {
      let w = produkt();
      while (zeichen[i] === "+" || zeichen[i] === "-") w = zeichen[i++] === "+" ? w + produkt() : w - produkt();
      return w;
    }
    function produkt() {
      let w = faktor();
      while (zeichen[i] === "*" || zeichen[i] === "/") w = zeichen[i++] === "*" ? w * faktor() : w / faktor();
      return w;
    }
    function faktor() {
      const z = zeichen[i++];
      if (z === "-") return -faktor();
      if (z === "+") return faktor();
      if (z === "(") { const w = summe(); if (zeichen[i++] !== ")") throw new Error(); return w; }
      if (z !== undefined && /^[\d.]/.test(z)) return parseFloat(z);
      throw new Error();
    }
    try {
      const w = summe();
      return i === zeichen.length && isFinite(w) ? w : null;
    } catch (e) { return null; }
  }
  function betrag(w) { return w.toFixed(2).replace(".", ","); }   // deutsches Dezimalkomma
  function preisRechnen(el) {
    const text = el.value.trim();
    el.setCustomValidity("");
    if (!/^=|\d\s*[-+*\/]|[()]/.test(text)) return;   // einfacher Betrag: so lassen
    const w = rechnen(text);
    if (w === null) { el.setCustomValidity("Rechnung nicht verständlich, z. B. =24+(2*8)+4+5"); el.reportValidity && el.reportValidity(); return; }
    el.value = betrag(w);
    el.title = text;   // Rechnung zum Nachsehen
  }

  // Preis/Nacht oder Gesamtpreis: das jeweils andere Feld zeigt den umgerechneten Wert grau an
  function zahl(text) { return String(text).trim() ? rechnen(text) : null; }   // auch Rechnungen beim Tippen
  function preisHinweis(zeile) {
    const ppn = feld(zeile, "preis_pro_nacht"), gesamt = feld(zeile, "gesamtpreis");
    const von = feld(zeile, "von"), bis = feld(zeile, "bis");
    if (!ppn || !gesamt || !von || !bis) return;
    const naechte = von.value && bis.value
      ? Math.round((new Date(bis.value) - new Date(von.value)) / 86400000) : 0;
    const p = zahl(ppn.value), g = zahl(gesamt.value);
    gesamt.placeholder = p !== null && naechte > 0 ? "= " + betrag(p * naechte) : "";
    ppn.placeholder = g !== null && naechte > 0 ? "≈ " + betrag(g / naechte) : "";
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

  // Einklappen: Blöcke auf eine Kopfzeile reduzieren (Etappen, Buchungen, eigene Buchungen einer Mitreise)
  const KLAPPBAR = ["etappen", "buchungen", "eigene_buchungen"];
  function merken(prefix, wert) {
    try { localStorage.setItem("eingeklappt:" + prefix, wert ? "1" : ""); } catch (e) { /* ohne Speicher */ }
  }
  function gemerkt(prefix) {
    try { return localStorage.getItem("eingeklappt:" + prefix) === "1"; } catch (e) { return false; }
  }
  function tag(iso) { return iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) + "." : "?"; }
  function auswahlText(zeile, name) {
    const f = feld(zeile, name);
    if (!f || !f.value) return "?";
    const o = f.options ? f.options[f.selectedIndex] : null;
    return o ? o.text : f.value;
  }
  // Kurzzeile aus den aktuellen Feldwerten, damit sie auch ungespeicherte Änderungen zeigt
  function kurzText(prefix, zeile) {
    if (prefix === "etappen") {
      if (!feld(zeile, "datum")) return "";
      return tag(inhalt(zeile, "datum")) + " " + auswahlText(zeile, "von_ort") + " → " + auswahlText(zeile, "nach_ort");
    }
    const von = inhalt(zeile, "von"), bis = inhalt(zeile, "bis");
    if (!feld(zeile, "von")) return "";
    const ort = feld(zeile, "ort") ? auswahlText(zeile, "ort") + " " : "";
    const naechte = von && bis ? Math.round((new Date(bis) - new Date(von)) / 86400000) : null;
    const teile = [ort + tag(von) + "–" + tag(bis)];
    if (naechte !== null) teile.push(naechte + (naechte === 1 ? " Nacht" : " Nächte"));
    if (feld(zeile, "status")) teile.push(auswahlText(zeile, "status"));
    return teile.join(" · ");
  }
  function klappen(prefix, zeile, zu) {
    const kopf = zeile.querySelector("h3");
    if (!kopf) return;
    zeile.classList.toggle("eingeklappt", zu);
    kopf.setAttribute("aria-expanded", String(!zu));
    let kurz = kopf.querySelector(".kurzzeile");
    if (!kurz) {
      kurz = document.createElement("span");
      kurz.className = "kurzzeile";
      const label = kopf.querySelector(".inline_label");
      kopf.insertBefore(kurz, label ? label.nextSibling : null);
    }
    kurz.textContent = zu ? kurzText(prefix, zeile) : "";
    kurz.hidden = !zu || !kurz.textContent;
  }
  function alleKnopf(prefix) {
    const gruppe = document.getElementById(prefix + "-group");
    return gruppe ? gruppe.querySelector(".alle-klappen") : null;
  }
  function knopfText(prefix) {
    const knopf = alleKnopf(prefix);
    if (!knopf) return;
    const offen = zeilen(prefix).some((z) => !z.classList.contains("eingeklappt"));
    knopf.textContent = offen ? "Alle einklappen" : "Alle ausklappen";
  }
  function hatFehler(zeile) { return !!zeile.querySelector(".errorlist, .errors"); }
  function einklappenEinrichten(prefix) {
    const gruppe = document.getElementById(prefix + "-group");
    if (!gruppe) return;
    const ueberschrift = gruppe.querySelector("h2");
    if (ueberschrift && !alleKnopf(prefix)) {
      const knopf = document.createElement("button");
      knopf.type = "button";
      knopf.className = "alle-klappen";
      knopf.addEventListener("click", (ev) => {
        ev.preventDefault();   // h2 kann in einem <summary> stehen
        const zu = zeilen(prefix).some((z) => !z.classList.contains("eingeklappt"));
        zeilen(prefix).forEach((z) => klappen(prefix, z, zu));
        merken(prefix, zu);
        knopfText(prefix);
      });
      ueberschrift.appendChild(knopf);
    }
    const zu = gemerkt(prefix);
    zeilen(prefix).forEach((z) => klappen(prefix, z, zu && !hatFehler(z)));
    knopfText(prefix);
  }
  function klappStil() {
    if (document.getElementById("einklapp-stil")) return;
    const stil = document.createElement("style");
    stil.id = "einklapp-stil";
    stil.textContent = ".inline-related > h3 { cursor: pointer; }" +
      " .inline-related > h3::before { content: \"▾\"; display: inline-block; width: 1.1em; }" +
      " .inline-related.eingeklappt > h3::before { content: \"▸\"; }" +
      " .inline-related.eingeklappt > fieldset, .inline-related.eingeklappt > .errorlist { display: none; }" +
      " .inline-related.eingeklappt > h3 .inline_label { display: none; }" +
      " .kurzzeile { font-weight: 600; }" +
      " .alle-klappen { float: right; margin: -2px 0; padding: 2px 10px; font-size: .75rem; cursor: pointer; }";
    (document.head || document.documentElement).appendChild(stil);
  }
  document.addEventListener("click", (ev) => {
    const kopf = ev.target.closest && ev.target.closest(".inline-related > h3");
    if (!kopf || ev.target.closest("a, input, label, button, .delete")) return;
    const zeile = kopf.parentElement;
    const prefix = KLAPPBAR.find((p) => zeile.id.startsWith(p + "-"));
    if (!prefix || zeile.id.endsWith("-empty")) return;
    klappen(prefix, zeile, !zeile.classList.contains("eingeklappt"));
    knopfText(prefix);
  });

  document.addEventListener("formset:added", (ev) => {
    const name = ev.detail && ev.detail.formsetName;
    const neu = ev.target;
    if (KLAPPBAR.includes(name)) { klappen(name, neu, false); knopfText(name); }
    if (name === "etappen") {
      const vorige = etappeDavor(neu);
      const datum = feld(neu, "datum");
      if (datum && !datum.value) {
        datum.value = vorige ? plusTage(feld(vorige, "datum").value, 1) : reiseBeginn();
      }
      if (vorige) ortUebernehmen(feld(vorige, "nach_ort"), feld(neu, "von_ort"));
    } else if (name === "buchungen") {
      const haken = feld(neu, "fremdwaehrung"), reihe = feld(neu, "waehrung") && feld(neu, "waehrung").closest(".form-row");
      if (haken && reihe) reihe.hidden = !haken.checked;
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

  document.addEventListener("formset:removed", grenzen);

  // zum Löschen markierte Zeilen sichtbar machen und auf „Sichern“ hinweisen
  function loeschMarkierung() {
    const kaesten = Array.from(document.querySelectorAll("input[type=checkbox][name$='-DELETE']"));
    kaesten.forEach((k) => { const z = eintrag(k); if (z) z.classList.toggle("zum-loeschen", k.checked); });
    const markiert = kaesten.some((k) => k.checked);
    document.querySelectorAll(".loesch-hinweis").forEach((p) => { p.hidden = !markiert; });
  }
  document.addEventListener("change", (ev) => {
    if (ev.target.matches("input[type=checkbox][name$='-DELETE']")) loeschMarkierung();
  });
  function etappeBearbeitet(ev) {
    if (ev.target.closest && ev.target.closest("#etappen-group")) buchungenSperre();
  }
  document.addEventListener("input", etappeBearbeitet);

  document.addEventListener("change", (ev) => {
    etappeBearbeitet(ev);
    const el = ev.target;
    if (el.id in ZEITRAUM || el.id in BIS_ZU) {
      delete el.dataset.vorbelegt;   // von Hand gewählt
      if (el.id in ZEITRAUM) zeitraumVorbelegen(el.id);
      zeitraumGrenzen();
    }
    if (el.matches("input[name$='-preis_pro_nacht'], input[name$='-gesamtpreis']")) {
      preisRechnen(el);
      preisHinweis(eintrag(el));
    }
    if (el.matches("input[name$='-fremdwaehrung']")) {
      const zeile = eintrag(el);
      if (zeile) { waehrungZeigen(zeile); preisHinweis(zeile); }
    }
    if (el.matches("select[name^='buchungen-'][name$='-ort']") && el.value) {
      const zeile = eintrag(el);
      const frei = freierAufenthalt(zeile, el.value);
      // nur übernehmen, solange die Daten nicht von Hand gesetzt sind
      if (frei && (!inhalt(zeile, "bis") || zeile.dataset.auto)) aufenthaltSetzen(zeile, frei);
    } else if (el.matches("input[name^='buchungen-'][type=date]")) {
      delete eintrag(el).dataset.auto;
    }
    if (el.matches("input[type=date], input[name$='-DELETE'], select[name$='-ort']")) grenzen();
  });
  document.addEventListener("input", (ev) => {
    if (ev.target.matches("input[name$='-preis_pro_nacht'], input[name$='-gesamtpreis']")) {
      preisHinweis(eintrag(ev.target));
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    etappenStand = etappenWerte();   // vor allem anderen: so wurde die Seite geladen
    zeilen("buchungen").forEach((z) => {
      const haken = feld(z, "fremdwaehrung"), reihe = feld(z, "waehrung") && feld(z, "waehrung").closest(".form-row");
      if (haken && reihe) reihe.hidden = !haken.checked;   // nur ein-/ausblenden, Werte bleiben
    });
    sperrStil();
    klappStil();
    KLAPPBAR.forEach(einklappenEinrichten);
    zeitraumGrenzen();
    grenzen();
    loeschMarkierung();
    // Von/Nach sind Autocomplete-Felder (select2) – deren Änderung kommt nur als jQuery-Ereignis
    if (window.django && django.jQuery) django.jQuery(document).on("change", "#etappen-group select", etappeBearbeitet);
  });
})();
