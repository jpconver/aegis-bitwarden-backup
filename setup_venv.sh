#!/usr/bin/env bash
set -euo pipefail

is_sourced() {
  # Works for bash. If executed, $0 equals this file path (or name).
  [[ "${BASH_SOURCE[0]}" != "${0}" ]]
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-"${SCRIPT_DIR}/.venv"}"
PYTHON="${PYTHON:-python3}"
VENV_SYSTEM_SITE_PACKAGES="${VENV_SYSTEM_SITE_PACKAGES:-0}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "ERROR: '${PYTHON}' no existe en PATH. Instalá Python 3 y reintentá." >&2
  return 127 2>/dev/null || exit 127
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  venv_args=()
  if [[ "${VENV_SYSTEM_SITE_PACKAGES}" == "1" ]]; then
    venv_args+=(--system-site-packages)
  fi
  "${PYTHON}" -m venv "${venv_args[@]}" "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip >/dev/null 2>&1 || true
if ! python -m pip install -r "${SCRIPT_DIR}/requirements.txt"; then
  echo "ERROR: no pude instalar dependencias con pip." >&2
  echo "Si estás sin internet, probá alguna de estas opciones:" >&2
  echo "  - Reintentá con conectividad a PyPI (pip)" >&2
  echo "  - (Debian/Ubuntu) instalá el paquete del sistema y recreá el venv con:" >&2
  echo "      VENV_SYSTEM_SITE_PACKAGES=1 rm -rf .venv && source ./setup_venv.sh" >&2
  echo "      sudo apt-get install -y python3-cryptography" >&2
  return 1 2>/dev/null || exit 1
fi

if ! is_sourced; then
  echo "OK: dependencias instaladas en ${VENV_DIR}"
  echo "Nota: para mantener el venv activado en tu shell actual, ejecutá:"
  echo "  source ./setup_venv.sh"
else
  echo "OK: venv activado (${VENV_DIR}) y dependencias instaladas."
fi
