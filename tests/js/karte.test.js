// Prüft reisen/static/reisen/karte.js mit dem echten Leaflet in jsdom. Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const wurzel = path.join(__dirname, "../..");
const daten = { orte: [{ name: "Zuhause", typ: "zuhause", lat: 54.32, lon: 10.13, website: "", aufenthalte: [] },
                       { name: "Rheincamping <b>", typ: "camping", lat: 47.8, lon: 7.55, website: "https://rheincamping.example", aufenthalte: ["27.08.–28.08. (1 Nacht)"] }],
                strecken: [{ punkte: [[54.32, 10.13], [50, 8.5], [47.8, 7.55]], gerade: false, text: "27.08. Zuhause → Rheincamping · 818 km" },
                           { punkte: [[47.8, 7.55], [54.32, 10.13]], gerade: true, text: "28.08. Rheincamping → Zuhause" }] };
const html = `<div id="karte" style="width:800px;height:400px" data-tomtom="/reise/kachel/tomtom/0/0/0.png"></div>
<script id="kartendaten" type="application/json">${JSON.stringify(daten)}</script>`;
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "https://urlaub.example.org/reise/4/" });
const w = dom.window;
Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 800; } });
Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 400; } });
// jsdom kann kein SVG-Layout; Leaflet prüft nur, ob es createSVGRect gibt (echte Browser haben es)
w.SVGElement.prototype.createSVGRect = () => ({});
w.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 });
w.eval(fs.readFileSync(path.join(wurzel, "static/vendor/leaflet/leaflet.js"), "utf8"));
const fehler = [];
w.addEventListener("error", (e) => fehler.push(e.message));
// Karte und Kachelebenen nach dem Erzeugen abgreifen
const L = w.L, orig = L.map, origKacheln = L.tileLayer; let karte; const alleKacheln = [];
L.map = (...a) => (karte = orig(...a));
L.tileLayer = (...a) => { const t = origKacheln(...a); alleKacheln.push(t); return t; };
w.eval(fs.readFileSync(path.join(wurzel, "reisen/static/reisen/karte.js"), "utf8"));
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const ebenen = []; karte.eachLayer((l) => ebenen.push(l));
const kacheln = ebenen.filter((l) => l instanceof L.TileLayer);
const linien = ebenen.filter((l) => l instanceof L.Polyline && !(l instanceof L.Polygon));
const punkte = ebenen.filter((l) => l instanceof L.CircleMarker);
ok("keine Skriptfehler", fehler.length, 0);
ok("Grundkarte OSM aktiv", kacheln.length === 1 && kacheln[0]._url, "https://tile.openstreetmap.org/{z}/{x}/{y}.png");
ok("OSM mit Referer", kacheln[0].options.referrerPolicy, "strict-origin-when-cross-origin");
ok("Linien", linien.length, 2);
ok("Luftlinie gestrichelt", linien[1].options.dashArray, "6 8");
ok("Route durchgezogen", linien[0].options.dashArray, null);
ok("Orte", punkte.length, 2);
ok("Popup ohne HTML aus Daten", punkte[1].getPopup().getContent().includes("Rheincamping &lt;b&gt;"), true);
ok("Ausschnitt umfasst Rheincamping", karte.getBounds().contains([47.8, 7.55]), true);
// TomTom-Ebene aus dem Umschalter
const steuer = w.document.querySelectorAll(".leaflet-control-layers-base label");
ok("Umschalter mit zwei Grundkarten", steuer.length, 2);
ok("TomTom über eigenen Server", alleKacheln[1]._url, "/reise/kachel/tomtom/{z}/{x}/{y}.png");
ok("TomTom-Hinweis", alleKacheln[1].options.attribution.includes("TomTom"), true);
