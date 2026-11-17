#!/usr/bin/env bash
# Exécuter la simulation locale ; Docker fournit GHDL sous Windows.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

host_available() {
  command -v make >/dev/null 2>&1 && command -v ghdl >/dev/null 2>&1 || return 1
  local major
  major=$(ghdl --version | sed -n '1s/^GHDL \([0-9][0-9]*\).*/\1/p')
  [[ "${major}" =~ ^[0-9]+$ ]] && [[ "${major}" -ge 3 ]]
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

main() {
  cd "${ROOT}"
  if host_available; then
    make -C hw/sim TEST="${TEST:-smoke}"
    return
  fi
  if ! docker_available; then
    echo "error: simulation requires Make and GHDL >= 3, or Docker." >&2
    return 3
  fi
  docker build -f hw/sim/Dockerfile -t saam-hw-sim:t1.10 .
  # Le code testé est copié dans l'image ; aucun wallet, port ou carte n'est monté.
  docker run --rm --network none -e TEST="${TEST:-smoke}" saam-hw-sim:t1.10
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
