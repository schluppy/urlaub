/* Teilen: Link kopieren, Teilen-Menü des Telefons, Schnellwahl für das Ablaufdatum. */
(function () {
  "use strict";
  document.querySelectorAll("[data-kopieren]").forEach((knopf) => {
    knopf.addEventListener("click", async () => {
      const text = knopf.dataset.kopieren;
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {   // ältere Browser oder ohne HTTPS: über ein unsichtbares Feld
        const feld = Object.assign(document.createElement("textarea"), { value: text });
        document.body.appendChild(feld); feld.select(); document.execCommand("copy"); feld.remove();
      }
      const alt = knopf.textContent;
      knopf.textContent = "Kopiert ✓";
      setTimeout(() => { knopf.textContent = alt; }, 2000);
    });
  });
  if (navigator.share) {
    document.querySelectorAll("[data-teilen]").forEach((knopf) => {
      knopf.hidden = false;
      knopf.addEventListener("click", () => {
        navigator.share({ title: knopf.dataset.titel, text: knopf.dataset.text.replace(knopf.dataset.teilen, "").trim(),
                          url: knopf.dataset.teilen }).catch(() => {});
      });
    });
  }
  document.querySelectorAll(".schnellwahl").forEach((gruppe) => {
    const feld = document.getElementById(gruppe.dataset.ziel);
    gruppe.querySelectorAll("[data-tage]").forEach((knopf) => {
      knopf.addEventListener("click", () => {
        const d = new Date();
        d.setDate(d.getDate() + Number(knopf.dataset.tage));
        const iso = d.toISOString().slice(0, 10);
        feld.value = feld.max && iso > feld.max ? feld.max : iso;
      });
    });
  });
})();
