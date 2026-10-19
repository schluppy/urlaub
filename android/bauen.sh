#!/bin/sh
# Baut das Handy-Widget im Container und legt die APK unter widget/urlaubswidget.apk ab.
# Der Signierschlüssel liegt außerhalb des Repositorys in ~/.urlaubswidget – unbedingt sichern:
# Ohne ihn lassen sich Updates nicht über die installierte App spielen.
set -e
cd "$(dirname "$0")"
SCHLUESSEL="$HOME/.urlaubswidget"
mkdir -p "$SCHLUESSEL" "$HOME/.cache/urlaubswidget-gradle" ../widget
chmod 700 "$SCHLUESSEL"
docker image inspect urlaub-android-bau >/dev/null 2>&1 || docker build -t urlaub-android-bau .
if [ ! -f "$SCHLUESSEL/schluessel.jks" ]; then
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$SCHLUESSEL/passwort"
  chmod 600 "$SCHLUESSEL/passwort"
  docker run --rm -u "$(id -u):$(id -g)" -v "$SCHLUESSEL:/schluessel" urlaub-android-bau \
    keytool -genkeypair -keystore /schluessel/schluessel.jks -alias urlaubswidget -keyalg RSA -keysize 3072 \
      -validity 10000 -storepass "$(cat "$SCHLUESSEL/passwort")" -dname "CN=Urlaubsplaner Widget"
  chmod 600 "$SCHLUESSEL/schluessel.jks"
fi
docker run --rm -u "$(id -u):$(id -g)" \
  -e HOME=/tmp -e GRADLE_USER_HOME=/gradle \
  -e SIGNIER_DATEI=/schluessel/schluessel.jks -e SIGNIER_PASSWORT="$(cat "$SCHLUESSEL/passwort")" \
  -v "$PWD:/src" -v "$SCHLUESSEL:/schluessel:ro" -v "$HOME/.cache/urlaubswidget-gradle:/gradle" \
  urlaub-android-bau gradle --no-daemon -q assembleRelease
cp app/build/outputs/apk/release/app-release.apk ../widget/urlaubswidget.apk
echo "fertig: widget/urlaubswidget.apk"
