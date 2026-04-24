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
  ./zipSource.sh [opciones]

Comprime source en source.7z y genera source.7z.sha256.

Nota de seguridad:
  7z requiere pasar la password con -p..., lo que deja una exposicion residual
  en argv del proceso 7z. El script minimiza el tiempo de exposicion, pero no
  puede eliminarlo con la interfaz actual de 7z.

Opciones:
  --use-last-source         Fuerza usar el ultimo source_root guardado
  --source-root PATH        Usa source/ bajo PATH/source
  --secrets-path PATH       Cambia la base persistente (default: ~/projects/security/secrets)
  --backup                  Mantiene backup del zip anterior (default)
  --no-backup               No guarda backup del zip anterior
  --cleanup-last-source     Limpia source en RAM despues de comprimir (default)
  --no-cleanup-last-source  No limpia source en RAM despues de comprimir
  -h, --help                Muestra esta ayuda
EOF
}

secrets_path="$(aegis_resolve_secrets_path)"
source_root_arg=""
use_last_source=0
backup_enabled=1
using_last_source=0
cleanup_last_source=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --use-last-source)
      use_last_source=1
      shift
      ;;
    --backup)
      backup_enabled=1
      shift
      ;;
    --no-backup)
      backup_enabled=0
      shift
      ;;
    --cleanup-last-source)
      cleanup_last_source=1
      shift
      ;;
    --no-cleanup-last-source)
      cleanup_last_source=0
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
readonly state_dir="$(aegis_resolve_state_dir "$secrets_path")"
readonly last_source_root_file="$state_dir/last_source_root"

if [[ "$use_last_source" == "1" && -n "$source_root_arg" ]]; then
  printf 'Error: --use-last-source no se puede combinar con --source-root.\n' >&2
  exit 1
fi

if [[ -z "$source_root_arg" && ! -d "$secrets_path/source" && -f "$last_source_root_file" ]]; then
  source_root_arg="$(<"$last_source_root_file")"
  using_last_source=1
elif [[ "$use_last_source" == "1" ]]; then
  if [[ -f "$last_source_root_file" ]]; then
    source_root_arg="$(<"$last_source_root_file")"
    using_last_source=1
  else
    printf 'Error: no existe last source root guardado en %s\n' "$last_source_root_file" >&2
    exit 1
  fi
fi

readonly source_root="${source_root_arg:-$secrets_path}"
readonly source_path="$source_root/source"
readonly archive_path="$secrets_path/source.7z"
readonly checksum_path="$archive_path.sha256"
readonly backup_dir="$secrets_path/backups"

if [[ -n "${DISPLAY:-}" ]]; then
  printf 'Warning: running in graphical session (DISPLAY is set).\n' >&2
fi

command -v 7z >/dev/null 2>&1 || {
  printf 'Error: 7z not found in PATH.\n' >&2
  exit 1
}

if [[ ! -d "$source_path" ]]; then
  printf 'Error: no existe el directorio a comprimir: %s\n' "$source_path" >&2
  exit 1
fi

if [[ -L "$source_root" || -L "$source_path" ]]; then
  printf 'Error: refusing to use symlinked source path.\n' >&2
  exit 1
fi

chmod 700 "$source_root" "$source_path"

if [[ "$source_root" != "$secrets_path" ]]; then
  printf 'Using RAM-backed source path: %s\n' "$source_path"
fi

if [[ "$using_last_source" == "1" ]]; then
  printf 'Using last saved source root: %s\n' "$source_root"
fi

read -rsp "Password del 7z: " zip_password
printf "\n"
read -rsp "Repeat password del 7z: " zip_password_confirm
printf "\n"

if [[ -z "$zip_password" ]]; then
  printf 'Error: la password del 7z no puede estar vacia.\n' >&2
  exit 1
fi

if [[ "$zip_password" != "$zip_password_confirm" ]]; then
  printf 'Error: las passwords del 7z no coinciden.\n' >&2
  exit 1
fi

unset zip_password_confirm

if [[ "$backup_enabled" == "1" && -f "$archive_path" ]]; then
  mkdir -p "$backup_dir"
  chmod 700 "$backup_dir"
  backup_timestamp="$(date +%Y%m%d%H%M)"
  backup_path="$backup_dir/source_${backup_timestamp}.7z"
  cp "$archive_path" "$backup_path"
fi

rm -f "$archive_path"
# Residual risk: 7z requires the password in argv via -p...
7z a -p"$zip_password" -mhe=on -m0=lzma2 -mx=9 "$archive_path" "$source_path"
sha256sum "$archive_path" > "$checksum_path"

if [[ "$cleanup_last_source" == "1" && "$source_root" == /dev/shm/aegis-source* ]]; then
  rm -rf -- "$source_root"
  if [[ -f "$last_source_root_file" ]]; then
    saved_source_root="$(<"$last_source_root_file")"
    if [[ "$saved_source_root" == "$source_root" ]]; then
      rm -f -- "$last_source_root_file"
    fi
  fi
  printf 'Cleaned last RAM source root: %s\n' "$source_root"
fi

unset zip_password
unset source_root_arg use_last_source backup_enabled using_last_source cleanup_last_source
