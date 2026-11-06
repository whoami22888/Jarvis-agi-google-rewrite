#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/templates/android"
TARGET="${1:-$ROOT/android}"

if [[ ! -d "$SOURCE" ]]; then
  echo "Android templates are missing: $SOURCE" >&2
  exit 1
fi
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -a "$SOURCE/." "$TARGET/"
printf 'Generated Android project at %s\n' "$TARGET"
