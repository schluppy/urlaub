// Prüft freigaben/static/freigaben/teilen.js und die Karte ohne TomTom (geteilte Seite). Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const wurzel = path.join(__dirname, "../..");
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));

// --- Teilen-Seite ---
const html = `<input type="date" id="id_gueltig_bis" max="2099-12-31">
<span class="schnellwahl" data-ziel="id_gueltig_bis"><button type="button" data-tage="7">1 Woche</button></span>
<button type="button" data-kopieren="https://urlaub.example.org/teilen/abc/">Link kopieren</button>
<button type="button" data-teilen="https://urlaub.example.org/teilen/abc/" data-titel="Sommerreise" data-text="Sommerreise – x:\nhttps://urlaub.example.org/teilen/abc/" hidden>Teilen …</button>`;
const dom = new JSDOM(html, { runScripts: "outside-only", url: "https://urlaub.example.org/" });
const w = dom.window, d = w.document;
let kopiert = null, geteilt = null;
Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (t) => { kopiert = t; } } });
w.navigator.share = async (daten) => { geteilt = daten; };
w.eval(fs.readFileSync(path.join(wurzel, "freigaben/static/freigaben/teilen.js"), "utf8"));
d.querySelector("[data-tage]").click();
const erwartet = new Date(); erwartet.setDate(erwartet.getDate() + 7);
ok("Schnellwahl 1 Woche", d.getElementById("id_gueltig_bis").value, erwartet.toISOString().slice(0, 10));
d.querySelector("[data-kopieren]").click();
const teilen = d.querySelector("[data-teilen]");
ok("Teilen-Knopf sichtbar, wenn das Telefon teilen kann", teilen.hidden, false);
teilen.click();
setTimeout(() => {
  ok("Link kopiert", kopiert, "https://urlaub.example.org/teilen/abc/");
  ok("Teilen mit Link", geteilt && geteilt.url, "https://urlaub.example.org/teilen/abc/");
  ok("Teilen-Text ohne doppelten Link", geteilt && geteilt.text, "Sommerreise – x:");

  // --- Karte auf geteilter Seite: nur OpenStreetMap, kein Umschalter ---
  const daten = { orte: [{ name: "Seecamping", typ: "camping", lat: 47.8, lon: 7.55, website: "", aufenthalte: [] }],
                  strecken: [{ punkte: [[54.29, 10.13], [47.8, 7.55]], gerade: true, text: "x" }] };
  const kdom = new JSDOM(`<div id="karte"></div><script id="kartendaten" type="application/json">${JSON.stringify(daten)}</script>`,
                         { runScripts: "outside-only", pretendToBeVisual: true, url: "https://urlaub.example.org/teilen/abc/" });
  const kw = kdom.window;
  Object.defineProperty(kw.HTMLElement.prototype, "clientWidth", { get() { return 800; } });
  Object.defineProperty(kw.HTMLElement.prototype, "clientHeight", { get() { return 400; } });
  kw.SVGElement.prototype.createSVGRect = () => ({});
  kw.eval(fs.readFileSync(path.join(wurzel, "static/vendor/leaflet/leaflet.js"), "utf8"));
  const kacheln = []; const orig = kw.L.tileLayer;
  kw.L.tileLayer = (...a) => { const t = orig(...a); kacheln.push(t); return t; };
  kw.eval(fs.readFileSync(path.join(wurzel, "reisen/static/reisen/karte.js"), "utf8"));
  ok("nur eine Grundkarte", kacheln.length, 1);
  ok("…und zwar OpenStreetMap", kacheln[0]._url, "https://tile.openstreetmap.org/{z}/{x}/{y}.png");
  ok("kein Umschalter", kdom.window.document.querySelectorAll(".leaflet-control-layers").length, 0);
}, 50);
