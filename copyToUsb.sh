#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/paths.sh
source "$script_dir/lib/paths.sh"
aegis_load_config

usage() {
  cat <<'EOF'
Uso:
  ./copyToUsb.sh [mountpoint_usb]

Si no se pasa mountpoint, el script intenta detectar automaticamente un unico
dispositivo removible montado. Si encuentra cero o mas de uno, aborta.

Archivos copiados a data/ dentro del USB:
  backups/
  source.7z
  source.7z.sha256

Luego verifica en el USB:
  sha256sum -c source.7z.sha256
EOF
}

secrets_path="$(aegis_resolve_secrets_path)"
archive_path="$secrets_path/source.7z"
checksum_path="$archive_path.sha256"
backup_dir="$secrets_path/backups"
target_dir_name="data"

detect_usb_mountpoint() {
  local -a mounts

  mapfile -t mounts < <(
    lsblk -nrpo RM,TYPE,MOUNTPOINT |
      awk '$1 == 1 && $2 == "part" && $3 != "" { print $3 }'
  )

  if [[ ${#mounts[@]} -eq 0 ]]; then
    printf 'Error: no se encontro ningun USB removible montado.\n' >&2
    exit 1
  fi

  if [[ ${#mounts[@]} -gt 1 ]]; then
    printf 'Error: se encontro mas de un USB removible montado.\n' >&2
    printf 'Mountpoints detectados:\n' >&2
    printf '  %s\n' "${mounts[@]}" >&2
    printf 'Pasa la ruta manualmente para evitar ambiguedad.\n' >&2
    exit 1
  fi

  printf '%s\n' "${mounts[0]}"
}

if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
  usage
  exit 0
fi

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 1
fi

command -v lsblk >/dev/null 2>&1 || {
  printf 'Error: lsblk no esta disponible en PATH.\n' >&2
  exit 1
}

command -v sha256sum >/dev/null 2>&1 || {
  printf 'Error: sha256sum no esta disponible en PATH.\n' >&2
  exit 1
}

if [[ $# -eq 1 ]]; then
  usb_mountpoint="$1"
else
  usb_mountpoint="$(detect_usb_mountpoint)"
fi

if [[ ! -d "$usb_mountpoint" ]]; then
  printf 'Error: el mountpoint no existe o no es directorio: %s\n' "$usb_mountpoint" >&2
  exit 1
fi

if [[ ! -f "$archive_path" ]]; then
  printf 'Error: no existe %s\n' "$archive_path" >&2
  exit 1
fi

if [[ ! -f "$checksum_path" ]]; then
  printf 'Error: no existe %s\n' "$checksum_path" >&2
  exit 1
fi

if [[ ! -d "$backup_dir" ]]; then
  printf 'Error: no existe %s\n' "$backup_dir" >&2
  exit 1
fi

target_dir="$usb_mountpoint/$target_dir_name"

mkdir -p "$target_dir"

printf 'USB detectado: %s\n' "$usb_mountpoint"
printf 'Copiando backups/, source.7z y source.7z.sha256 a %s...\n' "$target_dir"

cp -a "$backup_dir" "$target_dir/"
cp -a "$archive_path" "$target_dir/"
cp -a "$checksum_path" "$target_dir/"

sync

printf 'Verificando checksum en %s...\n' "$target_dir"

(
  cd "$target_dir"
  sha256sum -c "source.7z.sha256"
)

printf 'Copia y verificacion finalizadas.\n'
