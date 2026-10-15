// Buchungen als Blöcke (StackedInline): Haken „Fremdwährung“ blendet Währung und Kurs ein (eingabe.js).
const { JSDOM } = require("jsdom");
const fs = require("fs");
const block = (i, fremd, waehrung, kurs) => `<div class="inline-related has_original" id="buchungen-${i}">
  <h3><input type="checkbox" name="buchungen-${i}-DELETE"></h3><fieldset class="module">
  <div class="form-row"><select name="buchungen-${i}-ort"><option value="2" selected>See</option></select>
    <input type="date" name="buchungen-${i}-von" value="2027-08-01"><input type="date" name="buchungen-${i}-bis" value="2027-08-05"></div>
  <div class="form-row"><input name="buchungen-${i}-preis_pro_nacht" value=""><input name="buchungen-${i}-gesamtpreis" value="">
    <input type="checkbox" name="buchungen-${i}-fremdwaehrung"${fremd ? " checked" : ""}></div>
  <div class="form-row field-waehrung"><input name="buchungen-${i}-waehrung" value="${waehrung}"><input name="buchungen-${i}-wechselkurs" value="${kurs}"></div>
  </fieldset></div>`;
const html = `<input type="date" id="id_von" value="2027-08-01"><input type="date" id="id_bis" value="2027-08-05">
<div id="buchungen-group">${block(0, false, "EUR", "1")}${block(1, true, "GBP", "0.85")}
<div class="inline-related empty-form" id="buchungen-empty"></div><div class="add-row"><a href="#">Weitere</a></div></div>
<script id="aufenthalte" type="application/json">[{"ort": 2, "von": "2027-08-01", "bis": "2027-08-05"}]</script>`;
const dom = new JSDOM(html, { runScripts: "outside-only" });
const w = dom.window, d = w.document;
w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
d.dispatchEvent(new w.Event("DOMContentLoaded"));
const q = (n) => d.querySelector(`[name='${n}']`);
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const reihe = (i) => q(`buchungen-${i}-waehrung`).closest(".form-row");
ok("Euro-Buchung: Währung ausgeblendet", reihe(0).hidden, true);
ok("GBP-Buchung: Währung sichtbar", reihe(1).hidden, false);
q("buchungen-0-fremdwaehrung").checked = true;
q("buchungen-0-fremdwaehrung").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("Haken setzen: sichtbar", reihe(0).hidden, false);
ok("Haken setzen: Währung leer zum Eintragen", q("buchungen-0-waehrung").value, "");
q("buchungen-1-fremdwaehrung").checked = false;
q("buchungen-1-fremdwaehrung").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("Haken entfernen: ausgeblendet", reihe(1).hidden, true);
ok("Haken entfernen: Euro", q("buchungen-1-waehrung").value + " " + q("buchungen-1-wechselkurs").value, "EUR 1");
// Preis-Hinweis und Löschmarkierung funktionieren im Block
q("buchungen-1-preis_pro_nacht").value = "30";
q("buchungen-1-preis_pro_nacht").dispatchEvent(new w.Event("input", { bubbles: true }));
ok("Block: Gesamtpreis-Hinweis", q("buchungen-1-gesamtpreis").placeholder, "= 120.00");
q("buchungen-1-DELETE").checked = true;
q("buchungen-1-DELETE").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("Block: Löschmarkierung", d.getElementById("buchungen-1").classList.contains("zum-loeschen"), true);
