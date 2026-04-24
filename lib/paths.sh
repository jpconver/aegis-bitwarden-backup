#!/usr/bin/env bash

aegis_default_config_dir() {
  if [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
    printf '%s/aegis\n' "${XDG_CONFIG_HOME}"
  else
    printf '%s/.config/aegis\n' "${HOME}"
  fi
}

aegis_load_config() {
  local config_dir config_file

  config_dir="$(aegis_default_config_dir)"
  config_file="${AEGIS_CONFIG_FILE:-${config_dir}/config.env}"

  if [[ -f "${config_file}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${config_file}"
    set +a
  fi
}

aegis_resolve_secrets_path() {
  printf '%s\n' "${SECRETS_PATH:-${AEGIS_SECRETS_PATH:-${HOME}/projects/security/secrets}}"
}

aegis_resolve_state_dir() {
  local secrets_path="$1"
  local default_state_dir config_parent

  default_state_dir="$(aegis_default_config_dir)"

  if [[ ! -d "${default_state_dir}" ]]; then
    config_parent="$(dirname "${default_state_dir}")"
    if [[ ! -d "${config_parent}" ]]; then
      if ! mkdir -p "${config_parent}" 2>/dev/null; then
        default_state_dir="${secrets_path}/.aegis-state"
      fi
    fi
  fi

  printf '%s\n' "${AEGIS_STATE_DIR:-${default_state_dir}}"
}

aegis_resolve_dropbox_credentials_file() {
  local state_dir="$1"
  printf '%s\n' "${AEGIS_DROPBOX_CREDENTIALS_FILE:-${state_dir}/dropbox.json}"
}
