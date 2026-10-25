/* Statistik der gefahrenen Strecke neben der Karte: Etappe wählen, Diagramme für Geschwindigkeit und Höhe
   (SVG, über Strecke oder Dauer). Der Wert unter dem Mauszeiger erscheint als Punkt auf der Karte (karte.js). */
(function () {
  "use strict";
  const kasten = document.querySelector(".fahrt");
  if (!kasten) return;
  const wahl = kasten.querySelector(".fahrt-wahl");
  const bereich = kasten.querySelector(".fahrt-diagramme");
  const anzeige = kasten.querySelector(".fahrt-wert");
  const diagramme = [...kasten.querySelectorAll(".fahrt-diagramm")];
  const SVG = "http://www.w3.org/2000/svg";
  const HOEHE = 120, LINKS = 34, UNTEN = 18, OBEN = 6;
  const FARBE = { kmh: "#173F73", hoehe: "#2E7D6E" };
  const SPALTE = { kmh: 2, hoehe: 3 };
  let daten = null, achse = "km", etappe = null;

  const zahl = (x, stellen) => x.toLocaleString("de-DE", { minimumFractionDigits: stellen || 0, maximumFractionDigits: stellen || 0 });
  const uhr = (s) => { s = Math.round(s) % 86400; return Math.floor(s / 3600) + ":" + String(Math.floor(s / 60) % 60).padStart(2, "0"); };
  const dauer = (s) => uhr(s) + " h";
  const startsekunde = (t) => { const [h, m, s] = t.split(":").map(Number); return h * 3600 + m * 60 + s; };

  function el(name, attrs, eltern) {
    const e = document.createElementNS(SVG, name);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (eltern) eltern.appendChild(e);
    return e;
  }

  // Runde Teilstriche: 1, 2, 5 × 10^n, höchstens `anzahl` + 1 Abschnitte
  function striche(min, max, anzahl) {
    const roh = (max - min) / anzahl || 1;
    const p = Math.pow(10, Math.floor(Math.log10(roh)));
    const schritt = [1, 2, 5, 10].map((f) => f * p).find((s) => (max - min) / s <= anzahl + 1);
    const liste = [];
    for (let v = Math.ceil(min / schritt) * schritt; v <= max + 1e-9; v += schritt) liste.push(+v.toFixed(6));
    return { liste, schritt };
  }

  function zeichnen() {
    if (!daten) return;
    const r = daten.reihe;
    const xs = r.map((p) => (achse === "km" ? p[1] : p[0]));
    const xmax = xs[xs.length - 1] || 1;
    diagramme.forEach((d) => {
      d.textContent = "";
      const art = d.dataset.art;
      d.closest("figure").hidden = art === "hoehe" && !daten.hoehe;
      if (d.closest("figure").hidden) return;
      const breite = d.clientWidth || 300;
      const punkte = r.map((p, i) => [xs[i], p[SPALTE[art]]]).filter((p) => p[1] !== null);
      let ymin = art === "kmh" ? 0 : Math.min(...punkte.map((p) => p[1]));
      let ymax = Math.max(...punkte.map((p) => p[1]), ymin + 10);
      const y = striche(ymin, ymax, 3);
      ymin = Math.floor(ymin / y.schritt) * y.schritt;
      ymax = Math.ceil(ymax / y.schritt) * y.schritt;
      const sx = (x) => LINKS + (x / xmax) * (breite - LINKS - 4);
      const sy = (v) => OBEN + (1 - (v - ymin) / (ymax - ymin || 1)) * (HOEHE - OBEN - UNTEN);

      const svg = el("svg", { width: breite, height: HOEHE, viewBox: `0 0 ${breite} ${HOEHE}`, role: "img",
        "aria-label": art === "kmh" ? "Geschwindigkeit" : "Höhe" }, d);
      striche(ymin, ymax, 3).liste.forEach((v) => {
        el("line", { x1: LINKS, x2: breite - 4, y1: sy(v), y2: sy(v), class: "gitter" }, svg);
        el("text", { x: LINKS - 4, y: sy(v) + 3.5, "text-anchor": "end", class: "beschriftung" }, svg).textContent = zahl(v);
      });
      const xt = achse === "km" ? striche(0, xmax, 4) : striche(0, xmax / 3600, 4);
      xt.liste.forEach((v) => {
        const x = sx(achse === "km" ? v : v * 3600);
        if (x > breite - 12) return;
        el("text", { x, y: HOEHE - 4, "text-anchor": "middle", class: "beschriftung" }, svg).textContent =
          achse === "km" ? zahl(v) + (v ? "" : " km") : (xt.schritt < 1 ? uhr(v * 3600) : zahl(v)) + (v ? "" : " h");
      });
      const pfad = punkte.map((p, i) => (i ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("");
      if (art === "hoehe" && punkte.length) {
        el("path", { d: pfad + `L${sx(punkte[punkte.length - 1][0]).toFixed(1)} ${sy(ymin)}L${sx(punkte[0][0]).toFixed(1)} ${sy(ymin)}Z`,
          fill: FARBE[art], "fill-opacity": 0.12, stroke: "none" }, svg);
      }
      el("path", { d: pfad, fill: "none", stroke: FARBE[art], "stroke-width": 2, "stroke-linejoin": "round" }, svg);
      const kreuz = el("line", { y1: OBEN, y2: HOEHE - UNTEN, class: "kreuz", visibility: "hidden" }, svg);
      const marke = el("circle", { r: 4, fill: FARBE[art], stroke: "#fff", "stroke-width": 2, visibility: "hidden" }, svg);
      d._zeigen = (i) => {
        const v = i === null ? null : r[i][SPALTE[art]];
        [kreuz, marke].forEach((e) => e.setAttribute("visibility", v === null ? "hidden" : "visible"));
        if (v === null) return;
        kreuz.setAttribute("x1", sx(xs[i])); kreuz.setAttribute("x2", sx(xs[i]));
        marke.setAttribute("cx", sx(xs[i])); marke.setAttribute("cy", sy(v));
      };
      d._index = (clientX) => {
        const x = ((clientX - svg.getBoundingClientRect().left - LINKS) / (breite - LINKS - 4)) * xmax;
        let best = 0;
        xs.forEach((v, i) => { if (Math.abs(v - x) < Math.abs(xs[best] - x)) best = i; });
        return best;
      };
    });
  }

  function zeigen(i) {
    diagramme.forEach((d) => d._zeigen && d._zeigen(i));
    if (i === null) {
      anzeige.innerHTML = "&nbsp;";
      document.dispatchEvent(new CustomEvent("fahrt:punkt", { detail: null }));
      return;
    }
    const p = daten.reihe[i];
    anzeige.textContent = uhr(daten.start + p[0]) + " Uhr · " + zahl(p[1], 1) + " km · " + dauer(p[0]) + " · " +
      zahl(p[2]) + " km/h" + (p[3] !== null ? " · " + zahl(p[3]) + " m" : "");
    document.dispatchEvent(new CustomEvent("fahrt:punkt", { detail: [p[4], p[5]] }));
  }

  function waehlen(id, zoomen) {
    etappe = String(id);
    kasten.querySelectorAll(".fahrt-etappe").forEach((e) => { e.hidden = e.dataset.etappe !== etappe; });
    if (wahl) wahl.value = etappe;
    const quelle = document.getElementById("fahrt-" + etappe);
    daten = quelle ? JSON.parse(quelle.textContent) : null;
    if (daten) daten.start = startsekunde(daten.uhrzeit);
    bereich.hidden = !daten || daten.reihe.length < 2;
    zeichnen();
    zeigen(null);
    document.dispatchEvent(new CustomEvent("fahrt:gewaehlt", { detail: { etappe: Number(etappe), zoomen } }));
  }

  diagramme.forEach((d) => {
    d.addEventListener("pointermove", (ev) => { if (d._index) zeigen(d._index(ev.clientX)); });
    d.addEventListener("pointerleave", () => zeigen(null));
  });
  kasten.querySelectorAll("[data-achse]").forEach((k) => k.addEventListener("click", () => {
    achse = k.dataset.achse;
    kasten.querySelectorAll("[data-achse]").forEach((b) => b.setAttribute("aria-pressed", String(b === k)));
    zeichnen();
  }));
  if (wahl) wahl.addEventListener("change", () => waehlen(wahl.value, true));
  document.addEventListener("fahrt:waehlen", (ev) => {
    if (document.getElementById("fahrt-" + ev.detail.etappe)) waehlen(ev.detail.etappe, false);
  });
  let warten;
  window.addEventListener("resize", () => { clearTimeout(warten); warten = setTimeout(zeichnen, 150); });
  waehlen(kasten.querySelector(".fahrt-etappe").dataset.etappe, false);
})();
