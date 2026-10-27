# Urlaubsplaner

Selbst gehostete Web-App für die Urlaubsplanung mit Wohnwagen-Gespann – für eine oder mehrere
Familien. Reisen mit Etappen, Buchungen und Kosten planen, Routen passend fürs Gespann mit
TomTom berechnen und einen Jahres-Urlaubskalender mit Schulferien und Feiertagen als PDF drucken.

Django 5.2, PostgreSQL, Docker Compose; Oberfläche mit Django-Templates ohne JS-Framework.

Wie der Urlaubsplaner entstanden ist und wie er im Alltag aussieht, mit Bildern, steht im Blogbeitrag
[Unsere Urlaubstabelle hat ausgedient – der Urlaubsplaner](https://schluppeck.com/unsere-urlaubstabelle-hat-ausgedient-der-urlaubsplaner/).

## Was die App kann

- **Reisen** mit zwei Zeiträumen: *Urlaub* (inkl. Vor- und Nachbereitung, bestimmt Kalender und
  Urlaubstage) und *Reisezeit* (mit dem Gespann unterwegs). Beginnt die Reise an einem Arbeitstag
  vor dem Urlaub, gilt das als „Abfahrt nach Feierabend“.
- **Etappen** mit Start, Pause, Fahrzeit und Ankunft; **Buchungen** mit Preis pro Nacht oder
  Gesamtpreis, Fremdwährung, Anzahlung, Rest und Fälligkeit; **Kosten** (Fähre, Vignette, Maut …)
  und **Links**.
- **Berechnet statt eingetragen:** Nächte, Ankunft, Kraftstoffkosten, Summen in Euro, offene Beträge,
  Urlaubstage (Mo–Fr ohne Feiertage des Bundeslands).
- **Hinweise** auf Lücken: Etappen ohne Route, Nächte ohne Buchung, fällige Restzahlungen.
- **TomTom-Routing** auf Knopfdruck mit Fahrzeugmaßen (Länge, Breite, Höhe, Gewicht, Achsen,
  Höchstgeschwindigkeit), Ländern, Vignettenpflicht und Fähren; Adressen werden geocodiert.
- **Lange Etappen aufteilen:** Wo ist man nach x Stunden Fahrt (ab Startzeit, Pause verschiebt nur die
  Ankunft)? Suchbereich ±30 Min. auf der Karte, Link zu Campingplätzen in Google Maps; die Etappe wird
  dann am gefundenen Platz geteilt, die neue Etappe am Folgetag lässt sich weiter aufteilen.
- **Karte** je Reise (Leaflet) mit Routenverlauf, umschaltbar zwischen OpenStreetMap und TomTom.
- **Jahreskalender** als Seite und PDF (A4 quer): Monatsfarben, Feiertage, Schulferien, Urlaube.
- **Exporte** je Reise: PDF und Excel mit echten Formeln; PDFs und Excel tragen den Stand (Datum und Uhrzeit)
  im Dokument und im Dateinamen.
- **Kalender-Abo** (iCal) für Google, Apple oder Outlook: je Reise ein ganztägiger Termin über den Urlaub,
  Ort = Haupturlaubsort mit Adresse (Platz mit den meisten Nächten, ohne Zwischenübernachtungen und Fähren);
  geheimer Link je Person, jederzeit erneuerbar oder beendbar.
- **Erinnerungen per Mail:** Restzahlungen, eigene Erinnerungen („Fähre buchbar ab …“),
  Reisecheck 14 Tage vor Abfahrt.
- **Teilen per Link** mit Ablaufdatum – eine Reise oder den Jahreskalender per WhatsApp, E-Mail
  oder Teilen-Menü des Telefons; ohne Anmeldung, nur zum Ansehen, jederzeit beendbar. Das Zuhause
  wird dabei nie gezeigt (Route beginnt erst 3 km entfernt), Kosten nur auf Wunsch.
- **Handy-Apps** (Android, APK zum Download): Countdown-Widget bis zur nächsten Reise und **Tracking**,
  das Fahrten von selbst aufzeichnet – Start, wenn an einem Etappentag das Auto per Bluetooth verbunden
  wird, Ende beim Trennen nahe einem Etappenziel; Pausen lassen sich vor dem GPX-Export zusammenfügen.
  Die fertige Fahrt lädt die App direkt zu einer Reise hoch; „Route aktualisieren“ übernimmt dann die
  gefahrene Strecke statt der geplanten.
  Gebaut im Container mit `android/bauen.sh` bzw. `android-tracking/bauen.sh`. Der Bau braucht gut
  1,5 GB Arbeitsspeicher – auf einem knappen Server besser auf einem anderen Rechner bauen und nur die
  APK nach `widget/` kopieren (mit demselben Signierschlüssel).
- **Gemeinsam reisen:** Über „Teilen“ eine andere Familie im Urlaubsplaner einladen (per E-Mail-Adresse
  einer Person; alle ihre Mitglieder bekommen eine Mail). Nimmt jemand an, sieht die ganze Familie die Reise
  vollständig – in der Jahresübersicht, im Kalender, im Kalender-Abo und in den Handy-Apps. Zeitraum, Etappen,
  Plätze und Links pflegt die Familie der Reise; Fahrzeug und Kraftstoffpreis, Notizen, Status, Nummer,
  Stellplatz und Preise der Buchungen, Kosten, Erinnerungen und GPX-Tracks hat jede Familie für sich.
- **Mehrere Familien** (Mandanten) mit eigenem Bundesland und optional eigenem TomTom-Schlüssel;
  jede Familie sieht nur ihre eigenen Daten.
- **Anmeldung ohne Passwort** über einmalig gültige Links per E-Mail.

## Aufbau

| App         | Inhalt |
|-------------|--------|
| `konten`    | Familien mit Bundesland, Personen, TomTom-Schlüssel, Nutzungszähler, Anmeldelinks; Trennung der Familien (`mandant.py`) |
| `orte`      | Zuhause, Campingplätze, Fährterminals mit Adresse, Koordinaten, Website, Preisen |
| `fahrzeuge` | Fahrzeugprofile (Maße, Gewichte, Höchstgeschwindigkeit, Verbrauch) |
| `reisen`    | Reisen, Etappen, Buchungen, Kosten, Links, Erinnerungen; TomTom (`routing.py`), Exporte, Karte |
| `kalender`  | Schulferien, Feiertage (Paket `holidays`), Jahreskalender |
| `freigaben` | Links mit Ablaufdatum für Reisen und Kalender, öffentliche Ansicht unter `/teilen/<token>/` |
| `portal`    | Anmeldung, Jahresübersicht, Datenschutzhinweis, gemeinsame Vorlagen |

Eingegeben wird in der Django-Verwaltung (`/verwaltung/`), angepasst mit nativen Datums- und
Uhrzeitfeldern und einer Vorbelegung neuer Etappen und Buchungen (`reisen/static/reisen/eingabe.js`).

## Rollen

| Rolle | Darf |
|---|---|
| **Mitglied** | Reisen, Orte, Fahrzeugprofile und Erinnerungen der eigenen Familie bearbeiten |
| **Super-Admin** | zusätzlich Familien, Personen, TomTom-Schlüssel, Nutzung und Schulferien verwalten – die Reisen anderer Familien sieht auch er nicht |

## Installation

Voraussetzungen: Docker mit Compose, ein Reverse Proxy für HTTPS (Vorlage für Nginx in
`betrieb/nginx-urlaub.conf`), ein SMTP-Konto und ein kostenloser
[TomTom-API-Schlüssel](https://developer.tomtom.com/).

    git clone https://github.com/schluppy/urlaub.git && cd urlaub
    cp .env.example .env && chmod 600 .env          # Werte eintragen, s. Kommentare in der Datei
    cp betrieb/msmtprc.beispiel msmtprc && chmod 600 msmtprc
    printf 'MSMTP_PASSWORD=geheim\n' > msmtp.env && chmod 600 msmtp.env
    docker compose up -d --build
    docker compose exec web python manage.py beispieldaten          # optional: Familie „Muster“
    docker compose exec web python manage.py person_anlegen du@example.org "Dein Name" --familie Muster --super-admin

Die Anwendung lauscht auf `127.0.0.1:8020`. Weitere Familien und Personen legt der Super-Admin
in der Verwaltung an. Schulferien pflegt er je Bundesland (Verwaltung → Schulferien);
`beispieldaten` trägt die Schulferien Schleswig-Holstein 2027 ein.

Ohne Mailserver zum Ausprobieren: in `.env`
`EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` – der Anmeldelink steht dann
im Log (`docker compose logs web | grep anmelden/link`).

Nach Änderungen an `.env`: `docker compose up -d --force-recreate web`.
Nach Codeänderungen: `docker compose up -d --build`.

### Regelmäßige Aufgaben (Cron)

    0 7 * * *   cd /pfad/zu/urlaub && docker compose exec -T web python manage.py erinnerungen >> erinnerungen.log 2>&1
    30 3 * * *  /pfad/zu/urlaub/betrieb/backup.sh >> /var/log/urlaub-backup.log 2>&1

`backup.sh` sichert täglich die Datenbank (`db-DATUM.dump`) und die Konfiguration (`konfig-DATUM.tgz`:
`.env`, `msmtprc`, `msmtp.env` und die Dateien aus `betrieb/backup-dateien.txt`) nach `/var/backups/urlaub`
und behält höchstens `BACKUP_TAGE` Tage (Standard 14). Mit `BACKUP_EXTERN` in `.env` kommt optional eine
Kopie in ein weiteres Verzeichnis, etwa ein eingebundenes Netzlaufwerk.

### Weitere Befehle

| Befehl | Zweck |
|---|---|
| `erinnerungen --trocken --heute 2027-08-20` | zeigt, was an einem Tag verschickt würde |
| `routenlinien` | lädt den Streckenverlauf für die Karte nach, ohne Entfernung und Fahrzeit zu ändern |
| `schulferien_laden SH 2026 2028` | Schulferien aus der [OpenHolidays API](https://www.openholidaysapi.org) laden – ein Kürzel oder `ALLE` Bundesländer (auch per Knopf in der Verwaltung → Schulferien). Regionale Ausnahmen (z. B. Inseln in SH) werden übersprungen, bei getrennten Schularten (MV) zählen die allgemeinbildenden. Beim Anlegen einer Familie werden fehlende Schulferien ihres Landes für dieses und nächstes Jahr automatisch geholt. |
| `beispieldaten` | Beispielfamilie mit Reisen 2027 |
| `person_anlegen` | erste Person bzw. Super-Admin anlegen |

## TomTom

`reisen/routing.py` kapselt TomTom (Routing API v1, Search/Geocoding, Map Display).

- `travelMode=bus` berücksichtigt Länge, Breite, Höhe, Gewicht, Achslast und Achszahl
  (geprüft mit `report=effectiveSettings`).
- `avoidVignette` funktioniert nur im JSON-Body einer POST-Anfrage; ein leerer Body wird abgelehnt.
  Daher GET ohne, POST mit Vignetten-Vorgabe.
- `departAt` nur für künftige Abfahrten; vergangene Etappen ohne Verkehrsprognose.
- Etappe aufteilen (`reisen/aufteilen.py`): `extendedRouteRepresentation=travelTime,distance` liefert
  Fahrzeit und Strecke entlang der Linie (`progress`); Ortsnamen per Reverse Geocoding. Ein Vorschlag
  kostet 1 Routing- und 3 Geocoding-Abrufe und bleibt 6 h im Cache.
- Kartenkacheln holt der Server ab, damit der API-Schlüssel nicht im Browser landet.
- Familien ohne eigenen Schlüssel nutzen `TOMTOM_API_KEY` aus `.env`; jeder Abruf wird je Tag,
  Familie und Art gezählt (Verwaltung → TomTom-Nutzung).

## Tests

    docker build -t urlaub-web .
    docker run --rm -u 1000:1000 -v "$PWD":/app urlaub-web python manage.py test tests
    sh tests/js/lauf.sh        # Skripte der Oberfläche mit jsdom (Node-Container)

`tests/test_familien.py` prüft die Trennung der Familien (Listen, Suche, Auswahl, Seiten,
Exporte, Mails), `tests/test_kalender.py` Urlaubstage, Feiertage und Kalenderzellen.

## Lizenzen

Code: MIT (siehe `LICENSE`). Mitgeliefert: Leaflet 1.9.4 (BSD-2-Clause,
`static/vendor/leaflet/LICENSE`), Schrift Barlow Condensed (SIL Open Font License,
`static/fonts/OFL.txt`). Karten: © OpenStreetMap-Mitwirkende, © TomTom.
