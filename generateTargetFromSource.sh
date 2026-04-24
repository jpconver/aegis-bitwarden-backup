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
  ./generateTargetFromSource.sh [opciones]

Genera target a partir del source actual. target es derivado temporal.

Opciones:
  --paranoid                Exige usar /dev/shm para target
  --keep-target             Conserva target al finalizar. Default: cleanup automatico
  --use-last-source         Fuerza usar el ultimo source_root guardado
  --source-root PATH        Lee source desde PATH/source
  --target-root PATH        Escribe target en PATH/target
  --secrets-path PATH       Cambia la base persistente (default: ~/projects/security/secrets)
  -h, --help                Muestra esta ayuda
EOF
}

paranoid_mode=0
secrets_path="$(aegis_resolve_secrets_path)"
source_root_arg=""
target_root_arg=""
use_last_source=0
using_last_source=0
keep_target=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --paranoid)
      paranoid_mode=1
      shift
      ;;
    --keep-target)
      keep_target=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --use-last-source)
      use_last_source=1
      shift
      ;;
    --source-root)
      if [[ $# -lt 2 ]]; then
        printf 'Error: --source-root requiere un path.\n' >&2
        exit 1
      fi
      source_root_arg="$2"
      shift 2
      ;;
    --target-root)
      if [[ $# -lt 2 ]]; then
        printf 'Error: --target-root requiere un path.\n' >&2
        exit 1
      fi
      target_root_arg="$2"
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
readonly aegis_decoder_path="${AEGIS_DECODER_PATH:-$script_dir/decodeAegis.py}"
readonly bitwarden_decoder_path="${BITWARDEN_DECODER_PATH:-$script_dir/decodeBitwarden.py}"
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

default_target_root="$secrets_path"
if [[ -d "/dev/shm" && -w "/dev/shm" ]]; then
  default_target_root="/dev/shm/aegis-target-${USER:-user}-$$-$(date +%s)"
elif [[ "$paranoid_mode" == "1" ]]; then
  printf 'Error: --paranoid requiere /dev/shm escribible, pero no está disponible.\n' >&2
  exit 1
fi

readonly target_root="${target_root_arg:-$default_target_root}"
readonly target_path="$target_root/target"
cleanup_target_on_exit=1

cleanup() {
  if [[ "$cleanup_target_on_exit" -eq 1 ]]; then
    rm -rf "$target_path"
    if [[ "$target_root" != "$secrets_path" ]]; then
      rmdir "$target_root" 2>/dev/null || true
    fi
  fi
}

trap cleanup EXIT

if [[ -n "${DISPLAY:-}" ]]; then
  printf 'Warning: running in graphical session (DISPLAY is set).\n' >&2
fi

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    printf 'Error: no existe el archivo requerido: %s\n' "$file_path" >&2
    exit 1
  fi
}

run_decoder_with_stdin() {
  local password_value="$1"
  shift
  printf '%s\n' "$password_value" | python3 "$@"
}

if [[ ! -d "$source_path" ]]; then
  printf 'Error: no existe el directorio source: %s\n' "$source_path" >&2
  exit 1
fi

read -rsp "Password del export de Aegis: " aegis_password
printf "\n"

if [[ -L "$source_root" || -L "$source_path" || -L "$target_root" || -L "$target_path" ]]; then
  printf 'Error: refusing to use symlinked source or target path.\n' >&2
  exit 1
fi

rm -rf "$target_path"
mkdir -p "$target_path"
chmod 700 "$target_root" "$target_path"

if [[ "$using_last_source" == "1" ]]; then
  printf 'Using last saved source root: %s\n' "$source_root"
fi

if [[ "$source_root" != "$secrets_path" ]]; then
  printf 'Using RAM-backed source path: %s\n' "$source_path"
fi

if [[ "$target_root" != "$secrets_path" ]]; then
  printf 'Using RAM-backed target path: %s\n' "$target_path"
fi

require_file "$source_path/aegis-diario.json"
require_file "$source_path/aegis-vault.json"

run_decoder_with_stdin "$aegis_password" \
  "$aegis_decoder_path" \
  --password-stdin \
  -o "$target_path/aegis-diario-json" \
  "$source_path/aegis-diario.json"

run_decoder_with_stdin "$aegis_password" \
  "$aegis_decoder_path" \
  --password-stdin \
  -o "$target_path/aegis-vault-json" \
  "$source_path/aegis-vault.json"

unset aegis_password

shopt -s nullglob
bitwarden_files=("$source_path"/bitwarden*.json)
shopt -u nullglob

if (( ${#bitwarden_files[@]} > 0 )); then
  read -rsp "Password del export de Bitwarden: " bitwarden_password
  printf "\n"

  for bitwarden_file in "${bitwarden_files[@]}"; do
    base_name="$(basename "$bitwarden_file" .json)"
    run_decoder_with_stdin "$bitwarden_password" \
      "$bitwarden_decoder_path" \
      --password-stdin \
      -o "$target_path/${base_name}-json" \
      "$bitwarden_file"
  done

  unset bitwarden_password
fi

printf 'Target generated at: %s\n' "$target_path"

if [[ "$keep_target" == "1" ]]; then
  cleanup_target_on_exit=0
  printf 'WARNING: keeping plaintext target at %s\n' "$target_path" >&2
else
  printf 'Target will be cleaned automatically on exit: %s\n' "$target_path"
fi

unset paranoid_mode source_root_arg target_root_arg default_target_root use_last_source using_last_source keep_target
