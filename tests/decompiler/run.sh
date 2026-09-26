#!/usr/bin/env bash
set -euo pipefail
INNO_TEST_TOOL=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
INNO_TEST_SCRIPTS=$(cd "$(dirname "$0")" && pwd)
INNO_TEST_WORK=$(mktemp -d)
trap 'rm -rf "$INNO_TEST_WORK"' EXIT
while read -r digest name url; do
    curl -fsSL --retry 3 "$url" -o "$INNO_TEST_WORK/$name"
    printf '%s  %s\n' "$digest" "$INNO_TEST_WORK/$name" | shasum -a 256 -c -
done < "$INNO_TEST_SCRIPTS/fixtures.txt"
python3 "$INNO_TEST_SCRIPTS/verify_inno.py" --tool "$INNO_TEST_TOOL" \
    --output "$INNO_TEST_WORK/results.json" "$INNO_TEST_WORK"/*.exe
INSTALLER_INNOEXTRACT="$INNO_TEST_TOOL" \
INSTALLER_INNO_NEWER_FIXTURE="$INNO_TEST_WORK/innosetup-6.7.3.exe" \
    python3 "$INNO_TEST_SCRIPTS/test_inno_stream.py" -v
