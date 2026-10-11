// Prüft reisen/static/reisen/eingabe.js mit nachgebautem Admin-Formular. Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const zeile = (p, i, f) => `<tr class="form-row" id="${p}-${i}">${f.map(([n, v, t]) =>
  t === "select" ? `<td><select name="${p}-${i}-${n}" id="id_${p}-${i}-${n}">${v ? `<option value="${v[0]}" selected>${v[1]}</option>` : '<option value=""></option>'}</select></td>`
                 : `<td><input type="${t || "date"}" name="${p}-${i}-${n}" value="${v || ""}"></td>`).join("")}</tr>`;
const html = `<input type="date" id="id_von" value="2027-08-27"><input type="date" id="id_bis" value="2027-09-20">

<div id="etappen-group"><table><tbody>
${zeile("etappen", 0, [["datum", "2027-08-27"], ["von_ort", ["1", "Zuhause"], "select"], ["nach_ort", ["2", "Rheincamping"], "select"]])}
${zeile("etappen", 1, [["datum", ""], ["von_ort", null, "select"], ["nach_ort", null, "select"]])}
<tr class="form-row empty-form" id="etappen-empty"><td><input type="date" name="etappen-__prefix__-datum"></td></tr>
</tbody></table></div>
<div id="buchungen-group"><table><tbody>
${zeile("buchungen", 0, [["von", "2027-08-27"], ["bis", "2027-08-28"]])}
${zeile("buchungen", 1, [["von", ""], ["bis", ""]])}
</tbody></table></div>`;
const dom = new JSDOM(html, { runScripts: "outside-only" });
const w = dom.window, d = w.document;
w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
d.dispatchEvent(new w.Event("DOMContentLoaded"));
const q = (n) => d.querySelector(`[name='${n}']`);
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
// neue Etappe hinzugefügt (wie Djangos „Weitere Etappe hinzufügen“)
q("etappen-1-datum").closest("tr").dispatchEvent(new w.CustomEvent("formset:added", { bubbles: true, detail: { formsetName: "etappen" } }));
ok("Etappe 2: Datum vorbelegt", q("etappen-1-datum").value, "2027-08-27");
ok("Etappe 2: Von = Nach der vorigen", q("etappen-1-von_ort").value, "2");
ok("Etappe 2: Von-Text", q("etappen-1-von_ort").selectedOptions[0].text, "Rheincamping");
ok("Etappe 2: frühestes Datum", q("etappen-1-datum").min, "2027-08-27");
ok("Etappe 2: spätestes Datum", q("etappen-1-datum").max, "2027-09-20");
ok("Etappe 1: frühestes Datum = Reisebeginn", q("etappen-0-datum").min, "2027-08-27");
// Feierabend-Abfahrt eintragen → Grenzen der ersten Etappe
d.getElementById("id_von").value = "2027-08-26";
d.getElementById("id_von").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("Etappe 1 nach früherer Abfahrt: frühestes Datum", q("etappen-0-datum").min, "2027-08-26");
// erste Etappe auf späteren Tag → Grenze der zweiten wandert mit
q("etappen-0-datum").value = "2027-08-28";
q("etappen-0-datum").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("Etappe 2 folgt Etappe 1", q("etappen-1-datum").min, "2027-08-28");
// neue Buchung
q("buchungen-1-von").closest("tr").dispatchEvent(new w.CustomEvent("formset:added", { bubbles: true, detail: { formsetName: "buchungen" } }));
ok("Buchung 2: Anreise = Abreise der vorigen", q("buchungen-1-von").value, "2027-08-28");
ok("Buchung 2: Abreise frühestens", q("buchungen-1-bis").min, "2027-08-29");
ok("Buchung 1: Abreise frühestens", q("buchungen-0-bis").min, "2027-08-28");
