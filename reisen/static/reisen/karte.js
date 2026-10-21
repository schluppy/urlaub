/* Karte auf der Reiseseite (Leaflet): Strecken als Linien, Orte als Punkte,
   Grundkarte OpenStreetMap oder TomTom (über den eigenen Server, Key bleibt dort). */
(function () {
  "use strict";
  const el = document.getElementById("karte");
  const daten = document.getElementById("kartendaten");
  if (!el || !daten || !window.L) return;
  const { orte, strecken, ausschnitt } = JSON.parse(daten.textContent);

  const FARBEN = { zuhause: "#173F73", camping: "#E39226", zwischen: "#8A4F9E", faehre: "#1F6F8B", sonstiges: "#5F6875",
                   halt: "#C0392B" };
  const SPEICHER = "urlaub.kartenart";

  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    // OSM verlangt einen Referer; die Seite selbst sendet sonst keinen an fremde Server
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
  });
  // TomTom nur angemeldet (Kacheln über den eigenen Server); geteilte Seiten zeigen nur OpenStreetMap
  const grundkarten = { "OpenStreetMap": osm };
  if (el.dataset.tomtom) {
    grundkarten.TomTom = L.tileLayer(el.dataset.tomtom.replace("/0/0/0.png", "/{z}/{x}/{y}.png"), {
      maxZoom: 20,
      attribution: '&copy; <a href="https://www.tomtom.com/">TomTom</a>',
    });
  }
  let gewaehlt = "OpenStreetMap";
  try { if (grundkarten[localStorage.getItem(SPEICHER)]) gewaehlt = localStorage.getItem(SPEICHER); } catch (e) { /* privat */ }

  const karte = L.map(el, { layers: [grundkarten[gewaehlt]], scrollWheelZoom: false });
  if (Object.keys(grundkarten).length > 1) L.control.layers(grundkarten, null, { position: "topright" }).addTo(karte);
  L.control.scale({ imperial: false }).addTo(karte);
  karte.on("baselayerchange", (ev) => { try { localStorage.setItem(SPEICHER, ev.name); } catch (e) { /* privat */ } });
  // Mausrad erst nach Klick, damit die Seite beim Scrollen nicht in der Karte hängen bleibt
  karte.on("click", () => karte.scrollWheelZoom.enable());

  const grenzen = [];
  strecken.forEach((s) => {
    const linie = L.polyline(s.punkte, {
      color: s.farbe || "#173F73", weight: s.breite || 4, opacity: 0.85, dashArray: s.gerade ? "6 8" : null,
    }).bindTooltip(s.text + (s.gerade ? " (Luftlinie – Route noch nicht berechnet)" : ""), { sticky: true });
    linie.addTo(karte);
    grenzen.push(...s.punkte);
  });

  const text = (t) => { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; };
  orte.forEach((o) => {
    let popup = "<b>" + text(o.name) + "</b>" + (o.sterne ? ' <span class="sterne">' + text(o.sterne) + "</span>" : "");
    o.aufenthalte.forEach((a) => { popup += "<br>" + text(a); });
    if (o.website) popup += '<br><a href="' + encodeURI(o.website) + '" target="_blank" rel="noopener">Website</a>';
    L.circleMarker([o.lat, o.lon], {
      radius: o.typ === "zuhause" ? 7 : o.typ === "halt" ? 10 : 8, color: "#fff", weight: 2,
      fillColor: FARBEN[o.typ] || FARBEN.sonstiges, fillOpacity: 1,
    }).bindPopup(popup).bindTooltip(o.name).addTo(karte);
    grenzen.push([o.lat, o.lon]);
  });

  // Etappe aufteilen: auf den Suchbereich zoomen statt auf die ganze Strecke
  if (ausschnitt && ausschnitt.length) karte.fitBounds(ausschnitt, { padding: [40, 40], maxZoom: 11 });
  else if (grenzen.length) karte.fitBounds(grenzen, { padding: [24, 24], maxZoom: 12 });
  else karte.setView([51.16, 10.45], 5);   // ohne Orte: Deutschland
})();
