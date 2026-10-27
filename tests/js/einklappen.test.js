// Einklappen von Etappen und Buchungen (eingabe.js) mit nachgebauten Admin-Blöcken (StackedInline).
const { JSDOM } = require("jsdom");
const fs = require("fs");
const opt = (v, t) => `<option value="${v}" selected>${t}</option>`;
const etappe = (i, datum, von, nach) => `<div class="inline-related has_original" id="etappen-${i}">
  <h3><b>Etappe:</b> <span class="inline_label">alt</span> <span class="delete"><input type="checkbox" name="etappen-${i}-DELETE"><label>Löschen?</label></span></h3>
  <fieldset class="module aligned"><input type="hidden" name="etappen-${i}-id" value="${i + 1}">
  <input type="date" name="etappen-${i}-datum" value="${datum}">
  <select name="etappen-${i}-von_ort">${opt(von[0], von[1])}</select><select name="etappen-${i}-nach_ort">${opt(nach[0], nach[1])}</select></fieldset></div>`;
const buchung = (i, ort, von, bis, fehler) => `<div class="inline-related has_original" id="buchungen-${i}">
  <h3><b>Buchung:</b> <span class="inline_label">alt</span></h3>${fehler ? '<ul class="errorlist"><li>Fehler</li></ul>' : ""}
  <fieldset class="module aligned"><input type="hidden" name="buchungen-${i}-id" value="${i + 1}">
  <select name="buchungen-${i}-ort">${opt(ort[0], ort[1])}</select>
  <input type="date" name="buchungen-${i}-von" value="${von}"><input type="date" name="buchungen-${i}-bis" value="${bis}">
  <select name="buchungen-${i}-status"><option value="geplant">geplant</option>${opt("gebucht", "gebucht")}</select></fieldset></div>`;
const html = `<input type="date" id="id_von" value="2027-08-17"><input type="date" id="id_bis" value="2027-09-16">
<div id="etappen-group"><fieldset class="module"><h2>Etappen</h2>
${etappe(0, "2027-08-18", ["35", "Fährhafen"], ["36", "Seecamping"])}${etappe(1, "2027-09-13", ["42", "Waldcamping"], ["36", "Seecamping"])}</fieldset></div>
<div id="buchungen-group"><fieldset class="module"><h2>Buchungen</h2>
${buchung(0, ["36", "Seecamping"], "2027-08-18", "2027-08-19")}${buchung(1, ["42", "Waldcamping"], "2027-09-06", "2027-09-13", true)}</fieldset></div>
<script id="aufenthalte" type="application/json">[]</script>`;

function laden(gespeichert) {
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "https://urlaub.example/verwaltung/" });
  const w = dom.window;
  Object.entries(gespeichert || {}).forEach(([k, v]) => w.localStorage.setItem(k, v));
  w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  return w;
}
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const zu = (d, id) => d.getElementById(id).classList.contains("eingeklappt");
const kurz = (d, id) => d.querySelector(`#${id} .kurzzeile`).textContent;
const klick = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

let w = laden(), d = w.document;
ok("zu Beginn offen", zu(d, "etappen-0"), false);
const knopf = d.querySelector("#etappen-group .alle-klappen");
ok("Knopf an der Überschrift", knopf.textContent, "Alle einklappen");
klick(w, knopf);
ok("alle Etappen eingeklappt", zu(d, "etappen-0") && zu(d, "etappen-1"), true);
ok("Kurzzeile Etappe", kurz(d, "etappen-1"), "13.09. Waldcamping → Seecamping");
ok("Knopf jetzt Ausklappen", knopf.textContent, "Alle ausklappen");
ok("gemerkt", w.localStorage.getItem("eingeklappt:etappen"), "1");
ok("Buchungen unberührt", zu(d, "buchungen-0"), false);

klick(w, d.querySelector("#etappen-0 h3"));
ok("Klick auf Kopf klappt einzeln auf", zu(d, "etappen-0"), false);
ok("Knopf wieder Einklappen", knopf.textContent, "Alle einklappen");
klick(w, d.querySelector("#etappen-1 input[name$='-DELETE']"));
ok("Klick auf Löschen klappt nicht", zu(d, "etappen-1"), true);

klick(w, d.querySelector("#buchungen-0 h3"));
ok("Kurzzeile Buchung", kurz(d, "buchungen-0"), "Seecamping 18.08.–19.08. · 1 Nacht · gebucht");

// neu geladen mit gemerktem Zustand: eingeklappt, Block mit Fehler bleibt offen
w = laden({ "eingeklappt:buchungen": "1" }); d = w.document;
ok("gemerkt: Buchung eingeklappt", zu(d, "buchungen-0"), true);
ok("Buchung mit Fehler offen", zu(d, "buchungen-1"), false);
ok("Etappen ohne Merker offen", zu(d, "etappen-0"), false);
