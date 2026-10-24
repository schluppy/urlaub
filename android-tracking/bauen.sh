#!/bin/sh
# Baut die App „Tracking“ im Container, lässt die Unit-Tests laufen und legt die APK unter
# widget/tracking.apk ab. Bauumgebung und Signierschlüssel teilt sie mit dem Handy-Widget
# (../android/Dockerfile, ~/.urlaubswidget) – den Schlüssel legt ../android/bauen.sh an.
# Braucht gut 1,5 GB Arbeitsspeicher: auf einem knappen Server lieber woanders bauen und nur die APK kopieren.
set -e
cd "$(dirname "$0")"
SCHLUESSEL="$HOME/.urlaubswidget"
if [ ! -f "$SCHLUESSEL/schluessel.jks" ]; then
  echo "Kein Signierschlüssel in $SCHLUESSEL – zuerst android/bauen.sh ausführen." >&2
  exit 1
fi
mkdir -p "$HOME/.cache/urlaubswidget-gradle" ../widget
docker image inspect urlaub-android-bau >/dev/null 2>&1 || docker build -t urlaub-android-bau ../android
# Passwort nur über die Umgebung, nicht auf der Kommandozeile (sonst steht es in „ps“).
# Speicher und CPU begrenzen: lieber bricht der Bau ab, als dass der Server ins Swappen gerät.
SIGNIER_PASSWORT="$(cat "$SCHLUESSEL/passwort")" docker run --rm -u "$(id -u):$(id -g)" \
  --memory=1536m --memory-swap=1536m --cpus=2 \
  -e HOME=/tmp -e GRADLE_USER_HOME=/gradle \
  -e SIGNIER_DATEI=/schluessel/schluessel.jks -e SIGNIER_PASSWORT \
  -v "$PWD:/src" -v "$SCHLUESSEL:/schluessel:ro" -v "$HOME/.cache/urlaubswidget-gradle:/gradle" \
  urlaub-android-bau gradle --no-daemon -q testReleaseUnitTest assembleRelease
cp app/build/outputs/apk/release/app-release.apk ../widget/tracking.apk
echo "fertig: widget/tracking.apk"
