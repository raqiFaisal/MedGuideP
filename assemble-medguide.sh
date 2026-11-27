#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
output=MedGuide-8fb7441.zip
test ! -e "$output" || { printf '%s already exists\n' "$output" >&2; exit 1; }
pending=$(mktemp ./MedGuide.XXXXXX)
trap 'rm -f "$pending"' EXIT
cat MedGuide-8fb7441.zip.part-[0-9][0-9] > "$pending"
expected=$(cut -d ' ' -f1 SHA256SUMS)
if command -v sha256sum >/dev/null; then
  actual=$(sha256sum "$pending")
else
  actual=$(shasum -a 256 "$pending")
fi
test "${actual%% *}" = "$expected"
mv "$pending" "$output"
printf 'Created and verified %s\n' "$output"
