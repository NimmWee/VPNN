#!/bin/sh
set -eu
# Run from the unpacked recovery bundle; secrets are supplied as file paths.
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
apply_requested=false
for argument in "$@"; do
  if [ "$argument" = --apply ]; then apply_requested=true; fi
done
if ! python3 -c 'import cryptography' >/dev/null 2>&1; then
  if [ "$apply_requested" != true ]; then
    echo 'Dry-run requires python3-cryptography; no packages were installed.' >&2
    exit 1
  fi
  if [ "$(id -u)" != 0 ]; then
    echo 'Run with sudo; python3-cryptography is required.' >&2
    exit 1
  fi
  apt-get update
  apt-get install -y python3-cryptography
fi
exec python3 "$bundle_dir/restore_stack.py" --bundle "$bundle_dir" "$@"
