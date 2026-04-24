#!/bin/bash

set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/paths.sh
source "$script_dir/lib/paths.sh"
aegis_load_config

# Reemplazar estos valores por los de tu app de Dropbox.
readonly app_key="YOUR_DROPBOX_APP_KEY"
readonly app_secret="YOUR_DROPBOX_APP_SECRET"
readonly secrets_path="$(aegis_resolve_secrets_path)"
readonly state_dir="$(aegis_resolve_state_dir "$secrets_path")"
readonly credentials_file="$(aegis_resolve_dropbox_credentials_file "$state_dir")"

python3 "$script_dir/authenticateDropbox.py" \
  --app-key "$app_key" \
  --app-secret "$app_secret" \
  --credentials-file "$credentials_file"
