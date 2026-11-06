#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/templates/backend"
TARGET="${1:-$ROOT/backend}"

if [[ ! -d "$SOURCE" ]]; then
  echo "Backend templates are missing: $SOURCE" >&2
  exit 1
fi
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -a "$SOURCE/." "$TARGET/"
printf 'Generated backend at %s\n' "$TARGET"
