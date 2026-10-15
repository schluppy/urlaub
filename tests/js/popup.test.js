// Prüft static/verwaltung/popup.js: im Fenster speichert Enter nicht, außerhalb wie gewohnt.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const skript = fs.readFileSync(require("path").join(__dirname, "../../static/verwaltung/popup.js"), "utf8");
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));
function seite(popup) {
  const dom = new JSDOM(`<form>${popup ? '<input type="hidden" name="_popup" value="1">' : ""}
    <input name="name"><textarea name="notizen"></textarea><input type="submit" name="_save" value="Sichern"></form>`,
    { runScripts: "outside-only" });
  dom.window.eval(skript);
  return dom.window;
}
const enter = (w, sel) => {
  const ev = new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
  w.document.querySelector(sel).dispatchEvent(ev);
  return ev.defaultPrevented;
};
const w = seite(true);
ok("Fenster: Enter im Textfeld speichert nicht", enter(w, "[name=name]"), true);
ok("Fenster: Enter im Textbereich bleibt Zeilenumbruch", enter(w, "[name=notizen]"), false);
ok("Fenster: Enter auf Sichern speichert", enter(w, "[name=_save]"), false);
ok("normale Seite: Enter wie gewohnt", enter(seite(false), "[name=name]"), false);
