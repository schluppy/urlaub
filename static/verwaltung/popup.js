/* Verwaltung, Fenster zum Anlegen/Ändern aus einem anderen Formular (z. B. Campingplatz aus den Etappen):
   Enter speichert nicht mehr sofort – übernommen wird nur mit „Sichern“, danach schließt sich das Fenster.
   In Textbereichen bleibt Enter ein Zeilenumbruch, auf Knöpfen und Links wirkt es wie gewohnt. */
(function () {
  "use strict";
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.isComposing) return;
    if (!document.querySelector("input[name='_popup']")) return;   // nur im Fenster
    const el = ev.target;
    if (!el.form || el.matches("textarea, button, input[type=submit], input[type=button], a")) return;
    ev.preventDefault();
  });
})();
