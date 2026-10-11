/* Karte auf der Reiseseite (Leaflet): Strecken als Linien, Orte als Punkte,
   Grundkarte OpenStreetMap oder TomTom (über den eigenen Server, Key bleibt dort). */
(function () {
  "use strict";
  const el = document.getElementById("karte");
  const daten = document.getElementById("kartendaten");
  if (!el || !daten || !window.L) return;
  const { orte, strecken } = JSON.parse(daten.textContent);

  const FARBEN = { zuhause: "#173F73", camping: "#E39226", faehre: "#1F6F8B", sonstiges: "#5F6875" };
  const SPEICHER = "urlaub.kartenart";

  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    // OSM verlangt einen Referer; die Seite selbst sendet sonst keinen an fremde Server
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
  });
  const tomtom = L.tileLayer(el.dataset.tomtom.replace("/0/0/0.png", "/{z}/{x}/{y}.png"), {
    maxZoom: 20,
    attribution: '&copy; <a href="https://www.tomtom.com/">TomTom</a>',
  });
  const grundkarten = { "OpenStreetMap": osm, "TomTom": tomtom };
  let gewaehlt = "OpenStreetMap";
  try { if (grundkarten[localStorage.getItem(SPEICHER)]) gewaehlt = localStorage.getItem(SPEICHER); } catch (e) { /* privat */ }

  const karte = L.map(el, { layers: [grundkarten[gewaehlt]], scrollWheelZoom: false });
  L.control.layers(grundkarten, null, { position: "topright" }).addTo(karte);
  L.control.scale({ imperial: false }).addTo(karte);
  karte.on("baselayerchange", (ev) => { try { localStorage.setItem(SPEICHER, ev.name); } catch (e) { /* privat */ } });
  // Mausrad erst nach Klick, damit die Seite beim Scrollen nicht in der Karte hängen bleibt
  karte.on("click", () => karte.scrollWheelZoom.enable());

  const grenzen = [];
  strecken.forEach((s) => {
    const linie = L.polyline(s.punkte, {
      color: "#173F73", weight: 4, opacity: 0.85, dashArray: s.gerade ? "6 8" : null,
    }).bindTooltip(s.text + (s.gerade ? " (Luftlinie – Route noch nicht berechnet)" : ""), { sticky: true });
    linie.addTo(karte);
    grenzen.push(...s.punkte);
  });

  const text = (t) => { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; };
  orte.forEach((o) => {
    let popup = "<b>" + text(o.name) + "</b>";
    o.aufenthalte.forEach((a) => { popup += "<br>" + text(a); });
    if (o.website) popup += '<br><a href="' + encodeURI(o.website) + '" target="_blank" rel="noopener">Website</a>';
    L.circleMarker([o.lat, o.lon], {
      radius: o.typ === "zuhause" ? 7 : 8, color: "#fff", weight: 2,
      fillColor: FARBEN[o.typ] || FARBEN.sonstiges, fillOpacity: 1,
    }).bindPopup(popup).bindTooltip(o.name).addTo(karte);
    grenzen.push([o.lat, o.lon]);
  });

  if (grenzen.length) karte.fitBounds(grenzen, { padding: [24, 24], maxZoom: 12 });
  else karte.setView([51.16, 10.45], 5);   // ohne Orte: Deutschland
})();
