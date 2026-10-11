#!/bin/sh
# Tests für das Admin-Skript (jsdom) in einem Wegwerf-Container; auf dem Server gibt es kein Node.
# Aufruf: sh tests/js/lauf.sh   – Ausgabe „FEHLER“ bedeutet: Test fehlgeschlagen.
set -eu
cd "$(dirname "$0")/../.."
docker run --rm -v "$PWD":/app:ro -w /tmp node:22-slim sh -c \
  'npm install --silent jsdom@24 >/dev/null 2>&1 && for t in /app/tests/js/*.test.js; do echo "--- $t"; NODE_PATH=/tmp/node_modules node "$t"; done' \
  | tee /dev/stderr | grep -q FEHLER && exit 1 || exit 0
