// Prüft reisen/static/reisen/fahrt.js (Statistik neben der Karte) zusammen mit karte.js in jsdom. Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const wurzel = path.join(__dirname, "../..");
const karte = { orte: [], strecken: [{ punkte: [[54.3, 10.13], [54.32, 10.13]], gerade: false, text: "Hin", etappe: 7 },
                                     { punkte: [[54.32, 10.13], [54.5, 9.0]], gerade: false, text: "Weiter", etappe: 8 }] };
const reihe = [[0, 0, 0, 40, 54.3, 10.13], [60, 1.1, 66, 60, 54.31, 10.13], [120, 2.2, 0, 50, 54.32, 10.13]];
const etappe = (id, hoehe) => `<div class="fahrt-etappe" data-etappe="${id}"${id === 8 ? " hidden" : ""}><dl></dl>
  <script id="fahrt-${id}" type="application/json">${JSON.stringify({ uhrzeit: "16:37:00", reihe, hoehe })}</script></div>`;
const html = `<div id="karte" style="width:800px;height:400px"></div>
<script id="kartendaten" type="application/json">${JSON.stringify(karte)}</script>
<section class="fahrt"><select class="fahrt-wahl"><option value="7">A</option><option value="8">B</option></select>
${etappe(7, true)}${etappe(8, false)}
<div class="fahrt-diagramme" hidden><button data-achse="km" aria-pressed="true"></button><button data-achse="t" aria-pressed="false"></button>
<p class="fahrt-wert"></p><figure><div class="fahrt-diagramm" data-art="kmh"></div></figure>
<figure><div class="fahrt-diagramm" data-art="hoehe"></div></figure></div></section>`;
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "https://urlaub.example.org/reise/4/" });
const w = dom.window, d = w.document;
Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 400; } });
Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 400; } });
w.SVGElement.prototype.createSVGRect = () => ({});
w.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 });
w.SVGElement.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 120 });
w.eval(fs.readFileSync(path.join(wurzel, "static/vendor/leaflet/leaflet.js"), "utf8"));
const fehler = [];
w.addEventListener("error", (e) => fehler.push(e.message));
const L = w.L, orig = L.map; let lkarte;
L.map = (...a) => (lkarte = orig(...a));
w.eval(fs.readFileSync(path.join(wurzel, "reisen/static/reisen/karte.js"), "utf8"));
w.eval(fs.readFileSync(path.join(wurzel, "reisen/static/reisen/fahrt.js"), "utf8"));
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
const linien = () => { const l = []; lkarte.eachLayer((x) => { if (x instanceof L.Polyline) l.push(x); }); return l; };
const punkte = () => { const p = []; lkarte.eachLayer((x) => { if (x instanceof L.CircleMarker) p.push(x); }); return p; };
const [kmh, hoehe] = d.querySelectorAll(".fahrt-diagramm");

ok("keine Skriptfehler", fehler.length, 0);
ok("Diagramme sichtbar", d.querySelector(".fahrt-diagramme").hidden, false);
ok("Geschwindigkeitslinie", kmh.querySelectorAll("path").length, 1);
ok("Höhe mit Fläche", hoehe.querySelectorAll("path").length, 2);
ok("erste Etappe hervorgehoben", linien()[0].options.color, "#2E7D6E");

kmh.dispatchEvent(new w.MouseEvent("pointermove", { clientX: 220, bubbles: true }));
ok("Wert unter dem Mauszeiger", d.querySelector(".fahrt-wert").textContent, "16:38 Uhr · 1,1 km · 0:01 h · 66 km/h · 60 m");
ok("Position auf der Karte", punkte().length === 1 && punkte()[0].getLatLng().lat, 54.31);
kmh.dispatchEvent(new w.MouseEvent("pointerleave"));
ok("Position wieder weg", punkte().length, 0);

d.querySelector("[data-achse=t]").click();
ok("Achse Dauer", d.querySelector("[data-achse=t]").getAttribute("aria-pressed"), "true");
ok("Beschriftung in Stunden", [...kmh.querySelectorAll("text")].some((t) => t.textContent === "0:00 h"), true);

const wahl = d.querySelector(".fahrt-wahl");
wahl.value = "8"; wahl.dispatchEvent(new w.Event("change"));
ok("zweite Etappe sichtbar", d.querySelector('[data-etappe="8"]').hidden, false);
ok("erste Etappe versteckt", d.querySelector('[data-etappe="7"]').hidden, true);
ok("ohne Höhe kein Höhendiagramm", hoehe.closest("figure").hidden, true);
ok("Hervorhebung gewechselt", linien()[0].options.color + " " + linien()[1].options.color, "#173F73 #2E7D6E");

linien()[0].fire("click");
ok("Klick auf die Linie wählt die Etappe", wahl.value, "7");
