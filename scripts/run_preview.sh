#!/usr/bin/env bash
# Serve built module dist from the API process (no vite preview).
# Default: no rebuild. Pass --build / BUILD=1 to compile first.
# Usage: scripts/run_preview.sh [--build] [base] [wiki] [sale] ...
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "${ROOT}/scripts/webui_url.sh"

DO_BUILD=0
MODULES=()

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

addon_root() {
  local root="${MODOOR_MODULE_ROOT:-${ROOT}/module}"
  if [[ "${root}" != /* ]]; then
    root="${ROOT}/${root}"
  fi
  if [[ -d "${root}" ]]; then
    (cd "${root}" && pwd)
  else
    echo "${root}"
  fi
}

ADDON_ROOT="$(addon_root)"

default_modules() {
  local m
  for m in base doc wiki sale skill fleet freight capacity dispatch flow; do
    if [[ -d "${ADDON_ROOT}/${m}/webui" || -d "${ROOT}/module/${m}/webui" || -d "${ROOT}/inbuilt/${m}/webui" ]]; then
      echo "${m}"
    fi
  done
}

# First hit with index.html wins: external module, in-repo module, inbuilt.
dist_for() {
  local name="$1"
  local candidate
  local -a candidates=()
  candidates+=("${ADDON_ROOT}/${name}/webui/dist")
  if [[ "${ADDON_ROOT}" != "${ROOT}/module" ]]; then
    candidates+=("${ROOT}/module/${name}/webui/dist")
  fi
  candidates+=("${ROOT}/inbuilt/${name}/webui/dist")
  for candidate in "${candidates[@]}"; do
    if [[ -d "${candidate}" && -f "${candidate}/index.html" ]]; then
      (cd "${candidate}" && pwd)
      return 0
    fi
  done
  return 1
}

free_port() {
  local p="$1"
  [[ -z "${p}" ]] && return 0
  local pids
  pids="$(lsof -nP -iTCP:"${p}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo ">> freeing :${p} (pids: ${pids})"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.3
  fi
}

for arg in "$@"; do
  case "${arg}" in
    --build|-b) DO_BUILD=1 ;;
    *) MODULES+=("${arg}") ;;
  esac
done

if [[ "${BUILD:-0}" == "1" ]]; then
  DO_BUILD=1
fi

if [[ ${#MODULES[@]} -eq 0 ]]; then
  # shellcheck disable=SC2207
  MODULES=($(default_modules))
fi

if [[ ${#MODULES[@]} -eq 0 ]]; then
  echo "!! no module webui found under inbuilt/*/webui or module/*/webui" >&2
  exit 1
fi

if [[ "${DO_BUILD}" == "1" ]]; then
  chmod +x "${ROOT}/scripts/run_build.sh"
  "${ROOT}/scripts/run_build.sh" "${MODULES[@]}"
fi

DIST_PATHS=()
for name in "${MODULES[@]}"; do
  if ! dist="$(dist_for "${name}")"; then
    echo "!! missing dist for ${name}" >&2
    echo "   looked in ${ADDON_ROOT}/${name}/webui/dist" >&2
    if [[ "${ADDON_ROOT}" != "${ROOT}/module" ]]; then
      echo "             ${ROOT}/module/${name}/webui/dist" >&2
    fi
    echo "             ${ROOT}/inbuilt/${name}/webui/dist" >&2
    echo "   run: make build ${name}" >&2
    echo "   or:  make preview BUILD=1 ${name}" >&2
    exit 1
  fi
  DIST_PATHS+=("${dist}")
done

modoor_load_webui_url

# API serves dist itself — do not reverse-proxy vite preview.
unset MODOOR_WEBUI_PROXIES || true
export MODOOR_WEBUI_PROXIES=""
export MODOOR_WEBUI_STATIC_MODULES="$(IFS=,; echo "${MODULES[*]}")"
export MODOOR_MODULE_GATE

echo ""
echo "API / login  ${MODOOR_MODULE_GATE}/login"
echo "mode         preview (API mounts dist, no vite)"
for i in "${!MODULES[@]}"; do
  [[ -z "${MODULES[$i]}" ]] && continue
  printf "  /mod/%-8s → %s\n" "${MODULES[$i]}" "${DIST_PATHS[$i]}"
done
echo "static       ${MODOOR_WEBUI_STATIC_MODULES}"
echo ""

free_port "${PORT}"
exec "${ROOT}/.venv/bin/python" -m modoor.web.app
