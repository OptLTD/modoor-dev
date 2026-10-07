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

default_modules() {
  local m
  for m in base doc wiki sale skill fleet freight capacity dispatch flow; do
    if [[ -d "${ROOT}/addon/${m}/webui" || -d "${ROOT}/builtin/${m}/webui" ]]; then
      echo "${m}"
    fi
  done
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
  echo "!! no module webui found under builtin/*/webui or addon/*/webui" >&2
  exit 1
fi

if [[ "${DO_BUILD}" == "1" ]]; then
  chmod +x "${ROOT}/scripts/run_build.sh"
  "${ROOT}/scripts/run_build.sh" "${MODULES[@]}"
fi

for name in "${MODULES[@]}"; do
  dist="${ROOT}/addon/${name}/webui/dist"
  if [[ ! -d "${dist}" ]]; then
    dist="${ROOT}/builtin/${name}/webui/dist"
  fi
  if [[ ! -d "${dist}" || ! -f "${dist}/index.html" ]]; then
    echo "!! missing dist for ${name}: addon|builtin/${name}/webui/dist" >&2
    echo "   run: make build ${name}" >&2
    echo "   or:  make preview BUILD=1 ${name}" >&2
    exit 1
  fi
done

set -a
# shellcheck disable=SC1091
source .env
set +a
modoor_load_webui_url

# API serves dist itself — do not reverse-proxy vite preview.
unset MODOOR_WEBUI_PROXIES || true
export MODOOR_WEBUI_PROXIES=""
export MODOOR_WEBUI_STATIC_MODULES="$(IFS=,; echo "${MODULES[*]}")"
export MODOOR_WEBUI_URL

echo ""
echo "API / login  ${MODOOR_WEBUI_URL}/login"
echo "mode         preview (API mounts dist, no vite)"
for mid in "${MODULES[@]:-}"; do
  [[ -z "${mid}" ]] && continue
  if [[ -d "${ROOT}/builtin/${mid}/webui/dist" ]]; then
    printf "  /mod/%-6s → builtin/%s/webui/dist\n" "${mid}" "${mid}"
  else
    printf "  /mod/%-6s → addon/%s/webui/dist\n" "${mid}" "${mid}"
  fi
done
echo "static       ${MODOOR_WEBUI_STATIC_MODULES}"
echo ""

free_port "${PORT}"
exec "${ROOT}/.venv/bin/python" -m modoor.web.app
