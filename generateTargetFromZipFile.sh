#!/bin/bash

set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Uso:
  ./generateTargetFromZipFile.sh [opciones]

Wrapper de conveniencia: restaura source desde source.7z y luego genera target.

Opciones:
  --paranoid                Exige usar /dev/shm para restore/generacion temporal
  --keep-target             Conserva target al finalizar. Default: cleanup automatico
  --secrets-path PATH       Cambia la base persistente (default: ~/projects/security/secrets)
  --source-root PATH        Restaura source bajo PATH/source y lo usa para generar target
  --target-root PATH        Escribe target en PATH/target
  -h, --help                Muestra esta ayuda
EOF
}

paranoid_mode=0
secrets_path_arg=""
source_root_arg=""
target_root_arg=""
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
    --secrets-path)
      if [[ $# -lt 2 ]]; then
        printf 'Error: --secrets-path requiere un path.\n' >&2
        exit 1
      fi
      secrets_path_arg="$2"
      shift 2
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
    *)
      printf 'Error: argumento no soportado: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

restore_args=()
target_args=()

if [[ "$paranoid_mode" == "1" ]]; then
  restore_args+=(--paranoid)
  target_args+=(--paranoid)
fi
if [[ -n "$secrets_path_arg" ]]; then
  restore_args+=(--secrets-path "$secrets_path_arg")
  target_args+=(--secrets-path "$secrets_path_arg")
fi
if [[ -n "$source_root_arg" ]]; then
  restore_args+=(--source-root "$source_root_arg")
  target_args+=(--source-root "$source_root_arg")
fi
if [[ -n "$target_root_arg" ]]; then
  target_args+=(--target-root "$target_root_arg")
fi
if [[ "$keep_target" == "1" ]]; then
  target_args+=(--keep-target)
fi

"$script_dir/generateSourceFromZipFile.sh" "${restore_args[@]}"
"$script_dir/generateTargetFromSource.sh" "${target_args[@]}"
