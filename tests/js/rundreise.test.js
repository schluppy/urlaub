// Rundreise: erste und letzte Etappe stehen, dazwischen wird eine Etappe eingefügt (eingabe.js).
const { JSDOM } = require("jsdom");
const fs = require("fs");
const zeile = (i, id, datum, von, nach) => `<tr class="form-row" id="etappen-${i}">
  <td><input type="hidden" name="etappen-${i}-id" value="${id}"></td>
  <td><input type="date" name="etappen-${i}-datum" value="${datum}"></td>
  <td><select name="etappen-${i}-von_ort">${von ? `<option value="${von[0]}" selected>${von[1]}</option>` : '<option value=""></option>'}</select></td>
  <td><select name="etappen-${i}-nach_ort">${nach ? `<option value="${nach[0]}" selected>${nach[1]}</option>` : '<option value=""></option>'}</select></td>
  <td><input type="checkbox" name="etappen-${i}-DELETE"></td></tr>`;
const html = `<input type="date" id="id_von" value="2027-08-01"><input type="date" id="id_bis" value="2027-08-20">
<div id="etappen-group"><table><tbody>
${zeile(0, "1", "2027-08-01", ["1", "Zuhause"], ["2", "Seecamping"])}
${zeile(1, "2", "2027-08-20", ["2", "Seecamping"], ["1", "Zuhause"])}
${zeile(2, "", "", null, null)}
</tbody></table></div>
<div id="buchungen-group"><table><tbody><tr class="add-row"><td><a href="#">Weitere Buchung</a></td></tr></tbody></table></div>
<script id="aufenthalte" type="application/json">[{"ort": 2, "von": "2027-08-01", "bis": "2027-08-20"}]</script>`;
const dom = new JSDOM(html, { runScripts: "outside-only" });
const w = dom.window, d = w.document;
w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
d.dispatchEvent(new w.Event("DOMContentLoaded"));
const q = (n) => d.querySelector(`[name='${n}']`);
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const gruppe = d.getElementById("buchungen-group");

// vor dem Hinzufügen: Zeile 2 ist eine leere neue Zeile → gesperrt; ohne sie wäre frei
q("etappen-2-id").closest("tr").remove();
d.getElementById("id_bis").dispatchEvent(new w.Event("change", { bubbles: true }));
ok("gespeicherte Etappen: Buchungen frei", gruppe.classList.contains("buchung-gesperrt"), false);

d.querySelector("#etappen-group tbody").insertAdjacentHTML("beforeend", zeile(2, "", "", null, null));
q("etappen-2-datum").closest("tr").dispatchEvent(new w.CustomEvent("formset:added", { bubbles: true, detail: { formsetName: "etappen" } }));
ok("eingefügte Etappe: Tag nach der Hinfahrt", q("etappen-2-datum").value, "2027-08-02");
ok("eingefügte Etappe: Von = Seecamping", q("etappen-2-von_ort").value, "2");
ok("frühestes Datum = Reisebeginn", q("etappen-2-datum").min, "2027-08-01");
ok("spätestes Datum = Reiseende", q("etappen-2-datum").max, "2027-08-20");
ok("Buchungen gesperrt nach neuer Etappe", gruppe.classList.contains("buchung-gesperrt"), true);

// noch eine: 02.08. ist belegt → 03.08.
d.querySelector("#etappen-group tbody").insertAdjacentHTML("beforeend", zeile(3, "", "", null, null));
q("etappen-3-datum").closest("tr").dispatchEvent(new w.CustomEvent("formset:added", { bubbles: true, detail: { formsetName: "etappen" } }));
ok("zweite eingefügte Etappe: 03.08.", q("etappen-3-datum").value, "2027-08-03");

// Änderung an einer gespeicherten Etappe sperrt ebenfalls
const dom2 = new JSDOM(html.replace(zeile(2, "", "", null, null), ""), { runScripts: "outside-only" });
dom2.window.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
dom2.window.document.dispatchEvent(new dom2.window.Event("DOMContentLoaded"));
const g2 = dom2.window.document.getElementById("buchungen-group");
ok("ohne Änderung frei", g2.classList.contains("buchung-gesperrt"), false);
const datum2 = dom2.window.document.querySelector("[name='etappen-1-datum']");
datum2.value = "2027-08-19";
datum2.dispatchEvent(new dom2.window.Event("change", { bubbles: true }));
ok("geänderte Etappe sperrt", g2.classList.contains("buchung-gesperrt"), true);

// Löschen? markiert die Zeile und zeigt den Hinweis
const dom3 = new JSDOM(html + '<p class="loesch-hinweis" hidden>x</p>', { runScripts: "outside-only" });
dom3.window.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
dom3.window.document.dispatchEvent(new dom3.window.Event("DOMContentLoaded"));
const kasten = dom3.window.document.querySelector("[name='etappen-1-DELETE']");
kasten.checked = true;
kasten.dispatchEvent(new dom3.window.Event("change", { bubbles: true }));
ok("Zeile durchgestrichen", kasten.closest("tr").classList.contains("zum-loeschen"), true);
ok("Hinweis bei Sichern sichtbar", dom3.window.document.querySelector(".loesch-hinweis").hidden, false);

// Django löst beim Laden „change“ auf Auswahlfeldern aus (RelatedObjectLookups) – das sperrt nicht
const dom4 = new JSDOM(html.replace(zeile(2, "", "", null, null), ""), { runScripts: "outside-only" });
dom4.window.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
dom4.window.document.dispatchEvent(new dom4.window.Event("DOMContentLoaded"));
dom4.window.document.querySelectorAll("#etappen-group select").forEach((s) => s.dispatchEvent(new dom4.window.Event("change", { bubbles: true })));
const g4 = dom4.window.document.getElementById("buchungen-group");
ok("change ohne Änderung sperrt nicht", g4.classList.contains("buchung-gesperrt"), false);
// Änderung zurückgenommen → wieder frei
const d4 = dom4.window.document.querySelector("[name='etappen-1-datum']");
d4.value = "2027-08-19"; d4.dispatchEvent(new dom4.window.Event("change", { bubbles: true }));
ok("Änderung sperrt", g4.classList.contains("buchung-gesperrt"), true);
d4.value = "2027-08-20"; d4.dispatchEvent(new dom4.window.Event("change", { bubbles: true }));
ok("zurückgenommen: wieder frei", g4.classList.contains("buchung-gesperrt"), false);
