#!/usr/bin/env bash
# Start API (:8765) + selected module Vue apps; API reverse-proxies /mod/<module>.
# Usage: scripts/run_dev.sh [base] [wiki] [sale] ...
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "${ROOT}/scripts/webui_url.sh"

module_port() {
  case "$1" in
    base) echo 5175 ;;
    wiki) echo 5176 ;;
    sale) echo 5177 ;;
    skill) echo 5178 ;;
    doc) echo 5179 ;;
    fleet) echo 5180 ;;
    freight) echo 5181 ;;
    capacity) echo 5182 ;;
    dispatch) echo 5183 ;;
    flow) echo 5184 ;;
    *) echo "" ;;
  esac
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

MODULES=("$@")
if [[ ${#MODULES[@]} -eq 0 ]]; then
  echo "usage: make dev <module> [module...]"
  echo "  modules: base wiki sale skill doc fleet freight capacity dispatch flow"
  echo "  (sync is tools-only — no vite webui)"
  echo "  example: make dev base"
  echo "           make dev base wiki"
  exit 1
fi

PIDS=()
API_PID=""
PROXY_PARTS=()

cleanup() {
  trap - EXIT INT TERM
  local pid
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  done
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

set -a
# shellcheck disable=SC1091
source .env
set +a
modoor_load_webui_url

# Same root as modoor.core.settings.modoor_modules_root (MODOOR_ADDON_ROOT).
addon_root() {
  local root="${MODOOR_ADDON_ROOT:-${ROOT}/addon}"
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

start_webui() {
  local name="$1"
  local dir="${ADDON_ROOT}/${name}/webui"
  if [[ ! -d "${dir}" ]]; then
    dir="${ROOT}/builtin/${name}/webui"
  fi
  local p
  p="$(module_port "${name}")"
  if [[ ! -d "${dir}" ]]; then
    echo ">> skip ${name}: no webui/ (tools-only module)" >&2
    return 0
  fi
  if [[ -z "${p}" ]]; then
    echo ">> skip ${name}: no vite port mapping in run_dev.sh" >&2
    return 0
  fi
  free_port "${p}"
  PROXY_PARTS+=("${name}=http://127.0.0.1:${p}")
  (
    cd "${dir}"
    export MODOOR_PUBLIC_HOST="${HOST}"
    export MODOOR_PUBLIC_PORT="${PORT}"
    # Prefer pnpm workspace when addon root lives in a pro-style repo.
    local pkg_root=""
    if [[ -f "${ADDON_ROOT}/../pnpm-workspace.yaml" ]]; then
      pkg_root="$(cd "${ADDON_ROOT}/.." && pwd)"
    elif [[ -f "${ROOT}/pnpm-workspace.yaml" && "${dir}" == "${ROOT}"/* ]]; then
      pkg_root="${ROOT}"
    fi
    if [[ -n "${pkg_root}" ]] && command -v pnpm >/dev/null 2>&1; then
      if [[ ! -d "${pkg_root}/node_modules" || ! -f "${pkg_root}/pnpm-lock.yaml" ]]; then
        echo ">> pnpm install (${pkg_root})"
        (cd "${pkg_root}" && pnpm install)
      fi
      pnpm run dev
    else
      if [[ ! -d node_modules ]]; then
        echo ">> npm install (${name})"
        npm install
      fi
      npm run dev
    fi
  ) &
  PIDS+=($!)
}

for mid in "${MODULES[@]:-}"; do
  [[ -z "${mid}" ]] && continue
  start_webui "${mid}"
done

# Join proxies: base=http://127.0.0.1:5175,wiki=... → mounted as /mod/base, /mod/wiki
# Empty array + set -u → unbound; guard before expanding.
if [[ ${#PROXY_PARTS[@]} -gt 0 ]]; then
  MODOOR_WEBUI_PROXIES="$(IFS=,; echo "${PROXY_PARTS[*]}")"
else
  MODOOR_WEBUI_PROXIES=""
fi
export MODOOR_WEBUI_PROXIES
export MODOOR_WEBUI_URL
export MODOOR_ADDON_ROOT="${ADDON_ROOT}"

echo ""
echo "API / login  ${MODOOR_WEBUI_URL}/login"
echo "same port    ${MODOOR_WEBUI_URL}/mod/<module>"
for mid in "${MODULES[@]:-}"; do
  [[ -z "${mid}" ]] && continue
  printf "  /mod/%-6s → vite :%s\n" "${mid}" "$(module_port "${mid}")"
done
echo "proxies      ${MODOOR_WEBUI_PROXIES}"
echo "  MCP binary: ${ROOT}/.venv/bin/modoor-mcp"
echo ""

free_port "${PORT}"
"${ROOT}/.venv/bin/python" -m modoor.web.app &
API_PID=$!
PIDS+=("${API_PID}")

wait "${API_PID}"
