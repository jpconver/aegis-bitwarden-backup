#!/bin/bash

set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/paths.sh
source "$script_dir/lib/paths.sh"
aegis_load_config

readonly secrets_path="$(aegis_resolve_secrets_path)"
readonly state_dir="$(aegis_resolve_state_dir "$secrets_path")"
readonly credentials_file="$(aegis_resolve_dropbox_credentials_file "$state_dir")"
readonly dropbox_folder="/"

python3 "$script_dir/uploadToDropbox.py" \
  --credentials-file "$credentials_file" \
  --dropbox-folder "$dropbox_folder" \
  --secrets-path "$secrets_path" \
  --include-checksum
