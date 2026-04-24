#!/bin/bash

set -euo pipefail
set +o history 2>/dev/null || true
umask 077
ulimit -c 0 || true

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/paths.sh
source "$script_dir/lib/paths.sh"
aegis_load_config

usage() {
  cat <<'EOF'
Uso:
  ./generateSourceFromZipFile.sh [opciones]

Restaura source desde source.7z y guarda el ultimo source_root usado.

Nota de seguridad:
  7z requiere pasar la password con -p..., lo que deja una exposicion residual
  en argv del proceso 7z. El script minimiza el tiempo de exposicion, pero no
  puede eliminarlo con la interfaz actual de 7z.

Opciones:
  --paranoid                Exige usar /dev/shm para restaurar source
  --source-root PATH        Restaura source bajo PATH/source
  --secrets-path PATH       Cambia la base persistente (default: ~/projects/security/secrets)
  -h, --help                Muestra esta ayuda
EOF
}

paranoid_mode=0
secrets_path="$(aegis_resolve_secrets_path)"
source_root_arg=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --paranoid)
      paranoid_mode=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --source-root)
      if [[ $# -lt 2 ]]; then
        printf 'Error: --source-root requiere un path.\n' >&2
        exit 1
      fi
      source_root_arg="$2"
      shift 2
      ;;
    --secrets-path)
      if [[ $# -lt 2 ]]; then
        printf 'Error: --secrets-path requiere un path.\n' >&2
        exit 1
      fi
      secrets_path="$2"
      shift 2
      ;;
    *)
      printf 'Error: argumento no soportado: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

readonly secrets_path
readonly archive_path="$secrets_path/source.7z"
readonly checksum_path="$archive_path.sha256"
readonly state_dir="$(aegis_resolve_state_dir "$secrets_path")"
readonly last_source_root_file="$state_dir/last_source_root"

default_source_root="$secrets_path"
if [[ -d "/dev/shm" && -w "/dev/shm" ]]; then
  default_source_root="/dev/shm/aegis-source-${USER:-user}-$$-$(date +%s)"
elif [[ "$paranoid_mode" == "1" ]]; then
  printf 'Error: --paranoid requiere /dev/shm escribible, pero no está disponible.\n' >&2
  exit 1
fi

source_root="${source_root_arg:-$default_source_root}"
source_path="$source_root/source"
tmp_extract_path="$source_root/tmp_extract"

cleanup() {
  rm -rf "$tmp_extract_path"
  if [[ "$source_root" != "$secrets_path" && ! -e "$source_path" ]]; then
    rmdir "$source_root" 2>/dev/null || true
  fi
}

trap cleanup EXIT

if [[ -n "${DISPLAY:-}" ]]; then
  printf 'Warning: running in graphical session (DISPLAY is set).\n' >&2
fi

command -v 7z >/dev/null 2>&1 || {
  printf 'Error: 7z not found in PATH.\n' >&2
  exit 1
}

if [[ ! -f "$archive_path" ]]; then
  printf 'Error: no existe el archivo comprimido: %s\n' "$archive_path" >&2
  exit 1
fi

if [[ -f "$checksum_path" ]]; then
  (
    cd "$secrets_path"
    sha256sum -c "$(basename "$checksum_path")"
  ) || {
    printf 'Checksum verification failed for %s\n' "$archive_path" >&2
    exit 1
  }
fi

read -rsp "Password del 7z: " zip_password
printf "\n"

if [[ -L "$source_root" || -L "$source_path" || -L "$tmp_extract_path" ]]; then
  printf 'Error: refusing to use symlinked source or temp path.\n' >&2
  exit 1
fi

if ! mkdir -p "$source_root" 2>/dev/null; then
  if [[ -z "$source_root_arg" && "$source_root" != "$secrets_path" ]]; then
    printf 'Warning: could not use RAM source root %s, falling back to %s\n' "$source_root" "$secrets_path" >&2
    source_root="$secrets_path"
    source_path="$source_root/source"
    tmp_extract_path="$source_root/tmp_extract"
    mkdir -p "$source_root"
  else
    printf 'Error: no se pudo crear source root: %s\n' "$source_root" >&2
    exit 1
  fi
fi

rm -rf "$tmp_extract_path"
mkdir -p "$tmp_extract_path"
chmod 700 "$source_root" "$tmp_extract_path"

if [[ "$source_root" != "$secrets_path" ]]; then
  printf 'Using RAM-backed source path: %s\n' "$source_path"
fi

# Residual risk: 7z requires the password in argv via -p...
7z x -y -p"$zip_password" -o"$tmp_extract_path" "$archive_path"
unset zip_password

if [[ ! -d "$tmp_extract_path/source" ]]; then
  printf 'Error: el archivo comprimido no contiene el directorio source esperado.\n' >&2
  exit 1
fi

if [[ ! -f "$tmp_extract_path/source/aegis-diario.json" ]]; then
  printf 'Error: falta el archivo esperado aegis-diario.json dentro de source.\n' >&2
  exit 1
fi

if [[ ! -f "$tmp_extract_path/source/aegis-vault.json" ]]; then
  printf 'Error: falta el archivo esperado aegis-vault.json dentro de source.\n' >&2
  exit 1
fi

rm -rf "$source_path"
mv "$tmp_extract_path/source" "$source_path"
chmod 700 "$source_path"

mkdir -p "$state_dir"
chmod 700 "$state_dir"
printf '%s\n' "$source_root" > "$last_source_root_file"
chmod 600 "$last_source_root_file"

printf 'Source generated at: %s\n' "$source_path"

unset paranoid_mode source_root_arg default_source_root
