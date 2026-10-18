// Prüft reisen/static/reisen/eingabe.js mit nachgebautem Admin-Formular. Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const sel = (n, v) => `<select name="${n}"><option value="">---</option><option value="2"${v === "2" ? " selected" : ""}>Rheincamping</option><option value="3"${v === "3" ? " selected" : ""}>Seecamping</option></select>`;
const zeile = (i, ort, von, bis) => `<tr class="form-row" id="buchungen-${i}"><td>${sel(`buchungen-${i}-ort`, ort)}</td>
  <td><input type="date" name="buchungen-${i}-von" value="${von}"></td><td><input type="date" name="buchungen-${i}-bis" value="${bis}"></td>
  <td><input name="buchungen-${i}-preis_pro_nacht" value=""></td><td><input name="buchungen-${i}-gesamtpreis" value=""></td></tr>`;
const html = `<input type="date" id="id_von" value="2027-08-27"><input type="date" id="id_bis" value="2027-09-19"><input type="date" id="id_abfahrt_feierabend" value="">
<div id="buchungen-group"><table><tbody>${zeile(0, "2", "2027-08-27", "2027-08-28")}${zeile(1, "", "", "")}${zeile(2, "", "", "")}${zeile(3, "", "", "")}</tbody></table></div>
<script id="aufenthalte" type="application/json">[{"ort": 2, "von": "2027-08-27", "bis": "2027-08-28"}, {"ort": 3, "von": "2027-08-28", "bis": "2027-09-18"}, {"ort": 2, "von": "2027-09-18", "bis": "2027-09-19"}]</script>`;
const dom = new JSDOM(html, { runScripts: "outside-only" });
const w = dom.window, d = w.document;
w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
d.dispatchEvent(new w.Event("DOMContentLoaded"));
const q = (n) => d.querySelector(`[name='${n}']`);
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const neu = (i) => q(`buchungen-${i}-ort`).closest("tr").dispatchEvent(new w.CustomEvent("formset:added", { bubbles: true, detail: { formsetName: "buchungen" } }));
const wahl = (i, v) => { q(`buchungen-${i}-ort`).value = v; q(`buchungen-${i}-ort`).dispatchEvent(new w.Event("change", { bubbles: true })); };
neu(1);
ok("2. Buchung: nächster freier Aufenthalt", [q("buchungen-1-ort").value, q("buchungen-1-von").value, q("buchungen-1-bis").value].join(" "), "3 2027-08-28 2027-09-18");
neu(2);
ok("3. Buchung: Rheincamping auf dem Rückweg", [q("buchungen-2-ort").value, q("buchungen-2-von").value, q("buchungen-2-bis").value].join(" "), "2 2027-09-18 2027-09-19");
neu(3);
ok("4. Buchung: alles gebucht, Anreise = vorige Abreise", [q("buchungen-3-ort").value, q("buchungen-3-von").value].join(" "), " 2027-09-19");
// Platzwechsel bei automatisch gesetzten Daten: Zeile 2 von Rheincamping auf Seecamping? (schon gebucht in Zeile 1) -> bleibt
wahl(2, "3");
ok("Wechsel auf schon gebuchten Platz ändert nichts", q("buchungen-2-von").value, "2027-09-18");
// Zeile 1 Daten von Hand ändern, dann Platz wechseln -> Daten bleiben
q("buchungen-1-bis").value = "2027-09-10"; q("buchungen-1-bis").dispatchEvent(new w.Event("change", { bubbles: true }));
wahl(1, "2");
ok("von Hand gesetzte Abreise bleibt", q("buchungen-1-bis").value, "2027-09-10");
ok("Abreise frühestens Anreise+1", q("buchungen-1-bis").min, "2027-08-29");

// Preis-Hinweise: Gesamtpreis 563 für 21 Nächte (Zeile 1: 28.08.–18.09., Daten zurücksetzen)
q("buchungen-1-bis").value = "2027-09-18";
q("buchungen-1-gesamtpreis").value = "563";
q("buchungen-1-gesamtpreis").dispatchEvent(new w.Event("input", { bubbles: true }));
ok("Hinweis Preis/Nacht aus Gesamtpreis", q("buchungen-1-preis_pro_nacht").placeholder, "≈ 26,81");
q("buchungen-1-gesamtpreis").value = "";
q("buchungen-1-preis_pro_nacht").value = "26,50";
q("buchungen-1-preis_pro_nacht").dispatchEvent(new w.Event("input", { bubbles: true }));
ok("Hinweis Gesamtpreis aus Preis/Nacht", q("buchungen-1-gesamtpreis").placeholder, "= 556,50");
ok("Hinweis Preis/Nacht leer, wenn Gesamtpreis leer", q("buchungen-1-preis_pro_nacht").placeholder, "");
