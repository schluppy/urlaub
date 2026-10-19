#!/bin/sh
# Tägliche Sicherung des Urlaubsplaners. Cron (crontab -e als root):
#   30 3 * * *  /opt/urlaub/betrieb/backup.sh >> /var/log/urlaub-backup.log 2>&1
#
# Sichert nach $ZIEL (Standard /var/backups/urlaub), höchstens $BACKUP_TAGE Tage (Standard 14):
#   db-JJJJ-MM-TT.dump       Datenbank (pg_dump, Custom-Format)
#   konfig-JJJJ-MM-TT.tgz    .env, msmtprc, msmtp.env, die Dateien aus betrieb/backup-dateien.txt
#                            und der Signierschlüssel des Handy-Widgets (~/.urlaubswidget des Projekteigentümers)
# Optional zusätzlich: BACKUP_EXTERN=/pfad (in .env), z. B. ein eingebundenes Netzlaufwerk.
# Schlägt die Kopie nach außen fehl, bleibt die lokale Sicherung erhalten (Exit-Code 2).
set -eu
PROJEKT=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJEKT"

wert() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }
ZIEL=${ZIEL:-/var/backups/urlaub}
BACKUP_TAGE=${BACKUP_TAGE:-$(wert BACKUP_TAGE)}
BACKUP_TAGE=${BACKUP_TAGE:-14}
# -mtime +N löscht erst ab N+1 vollen Tagen; mit N = BACKUP_TAGE-1 bleiben höchstens BACKUP_TAGE Tagesstände
ALTER=$((BACKUP_TAGE - 1))
EXTERN=${BACKUP_EXTERN:-$(wert BACKUP_EXTERN)}
DB=$(wert POSTGRES_DB); DB=${DB:-urlaub}
DB_USER=$(wert POSTGRES_USER); DB_USER=${DB_USER:-urlaub}
STAMP=$(date +%F)
# Signierschlüssel des Handy-Widgets (android/bauen.sh): ohne ihn lassen sich keine App-Updates installieren.
# Liegt im Home des Projekteigentümers, nicht von root; abweichend in .env: WIDGET_SCHLUESSEL=/pfad
WIDGET=${WIDGET_SCHLUESSEL:-$(wert WIDGET_SCHLUESSEL)}
WIDGET=${WIDGET:-$(getent passwd "$(stat -c %U "$PROJEKT")" | cut -d: -f6)/.urlaubswidget}

mkdir -p "$ZIEL"
chmod 700 "$ZIEL"

# 1. Datenbank – erst in eine Teildatei, damit ein Abbruch keine halbe Sicherung hinterlässt
docker compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB" > "$ZIEL/db-$STAMP.dump.teil"
mv "$ZIEL/db-$STAMP.dump.teil" "$ZIEL/db-$STAMP.dump"

# 2. Konfiguration und private Dateien (nur vorhandene; Zeilen mit # sind Kommentare)
LISTE=$(mktemp)
for f in .env msmtprc msmtp.env; do [ -e "$f" ] && echo "$f" >> "$LISTE"; done
if [ -f betrieb/backup-dateien.txt ]; then
    grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' betrieb/backup-dateien.txt | while read -r f; do
        [ -e "$f" ] && echo "$f" >> "$LISTE" || echo "Hinweis: $f fehlt, nicht gesichert"
    done
fi
if [ -d "$WIDGET" ]; then
    # landet im Archiv als .urlaubswidget/…
    tar czf "$ZIEL/konfig-$STAMP.tgz" -T "$LISTE" -C "$(dirname "$WIDGET")" "$(basename "$WIDGET")"
else
    echo "Hinweis: $WIDGET fehlt, Widget-Schlüssel nicht gesichert"
    tar czf "$ZIEL/konfig-$STAMP.tgz" -T "$LISTE"
fi
rm -f "$LISTE"
chmod 600 "$ZIEL/db-$STAMP.dump" "$ZIEL/konfig-$STAMP.tgz"

find "$ZIEL" -maxdepth 1 -type f \( -name 'db-*' -o -name 'konfig-*' \) -mtime +"$ALTER" -delete
echo "$(date '+%F %T') lokal: $(ls -1 "$ZIEL" | wc -l) Dateien in $ZIEL, heute $(du -ch "$ZIEL"/*-"$STAMP".* | tail -1 | cut -f1)"

# 3. Optional: Kopie in ein weiteres Verzeichnis
if [ -n "$EXTERN" ]; then
    if mkdir -p "$EXTERN" && cp "$ZIEL/db-$STAMP.dump" "$ZIEL/konfig-$STAMP.tgz" "$EXTERN/"; then
        find "$EXTERN" -maxdepth 1 -type f \( -name 'db-*' -o -name 'konfig-*' \) -mtime +"$ALTER" -delete
        echo "$(date '+%F %T') extern: kopiert nach $EXTERN"
    else
        echo "$(date '+%F %T') FEHLER: Kopie nach $EXTERN fehlgeschlagen – lokale Sicherung ist vorhanden" >&2
        exit 2
    fi
fi
