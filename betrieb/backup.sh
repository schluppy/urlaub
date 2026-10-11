#!/bin/sh
# Tägliche Sicherung des Urlaubsplaners (nur Datenbank, es gibt keine Uploads).
# Aufbewahrung 30 Tage. Cron (crontab -e als root, Zielordner unter /var/backups):
#   30 3 * * *  /opt/urlaub/betrieb/backup.sh
set -eu
cd /opt/urlaub
ZIEL=${ZIEL:-/var/backups/urlaub}
STAMP=$(date +%F)
mkdir -p "$ZIEL"
chmod 700 "$ZIEL"
docker compose exec -T db pg_dump -U urlaub -Fc urlaub > "$ZIEL/db-$STAMP.dump"
find "$ZIEL" -name 'db-*.dump' -type f -mtime +30 -delete
