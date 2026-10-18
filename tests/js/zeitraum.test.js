// Prüft die Vorbelegung des Reisezeitraums in reisen/static/reisen/eingabe.js. Aufruf siehe README.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const html = `<input type="date" id="id_urlaub_von" value=""><input type="date" id="id_urlaub_bis" value="">
<input type="date" id="id_von" value=""><input type="date" id="id_bis" value="">`;
const dom = new JSDOM(html, { runScripts: "outside-only" });
const w = dom.window, d = w.document;
w.eval(fs.readFileSync(require("path").join(__dirname, "../../reisen/static/reisen/eingabe.js"), "utf8"));
d.dispatchEvent(new w.Event("DOMContentLoaded"));
const f = (id) => d.getElementById(id);
const waehle = (id, datum) => { f(id).value = datum; f(id).dispatchEvent(new w.Event("change", { bubbles: true })); };
const ok = (name, ist, soll) => console.log((ist === soll ? "OK    " : "FEHLER") + ` ${name}: ${ist}` + (ist === soll ? "" : ` (erwartet ${soll})`));

waehle("id_urlaub_von", "2027-08-23");
ok("Urlaub bis startet mit Urlaub von", f("id_urlaub_bis").value, "2027-08-23");
ok("Urlaub bis frühestens Urlaub von", f("id_urlaub_bis").min, "2027-08-23");
ok("Reisezeit von startet mit Urlaub von", f("id_von").value, "2027-08-23");
ok("Reisezeit bis startet mit Reisezeit von", f("id_bis").value, "2027-08-23");
waehle("id_urlaub_bis", "2027-09-12");
ok("Reisezeit bis folgt Urlaub bis", f("id_bis").value, "2027-09-12");
waehle("id_von", "2027-08-22");   // Abfahrt nach Feierabend
ok("Reisezeit bis bleibt", f("id_bis").value, "2027-09-12");
ok("Reisezeit bis frühestens Reisezeit von", f("id_bis").min, "2027-08-22");
waehle("id_bis", "2027-09-10");
waehle("id_urlaub_von", "2027-08-20");
ok("von Hand gewähltes Urlaub bis bleibt", f("id_urlaub_bis").value, "2027-09-12");
ok("von Hand gewählte Reisezeit von bleibt", f("id_von").value, "2027-08-22");
waehle("id_urlaub_von", "2027-09-20");
ok("zu frühes Urlaub bis wird nachgezogen", f("id_urlaub_bis").value, "2027-09-20");
waehle("id_von", "2027-09-15");
ok("zu frühe Reisezeit bis wird nachgezogen", f("id_bis").value, "2027-09-15");
