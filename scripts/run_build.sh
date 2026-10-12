#!/usr/bin/env bash
# Build selected module webuis (dist only).
# Usage: scripts/run_build.sh <module> [module...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODULES=("$@")
if [[ ${#MODULES[@]} -eq 0 ]]; then
  echo "usage: make build <module> [module...]"
  echo "  modules: base wiki sale skill doc fleet freight capacity dispatch flow"
  echo "  (sync is tools-only — no vite webui)"
  echo "  example: make build base"
  echo "           make build base wiki"
  exit 1
fi

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

pkg_root_for() {
  local dir="$1"
  if [[ -f "${ADDON_ROOT}/../pnpm-workspace.yaml" && "${dir}" == "${ADDON_ROOT}"/* ]]; then
    (cd "${ADDON_ROOT}/.." && pwd)
    return
  fi
  if [[ -f "${ROOT}/pnpm-workspace.yaml" && "${dir}" == "${ROOT}"/* ]]; then
    echo "${ROOT}"
    return
  fi
  echo ""
}

ensure_pnpm() {
  local pkg_root="$1"
  if [[ -z "${pkg_root}" ]] || ! command -v pnpm >/dev/null 2>&1; then
    return 1
  fi
  if [[ ! -d "${pkg_root}/node_modules" || ! -f "${pkg_root}/pnpm-lock.yaml" ]]; then
    echo ">> pnpm install (${pkg_root})"
    (cd "${pkg_root}" && pnpm install)
  fi
  return 0
}

for name in "${MODULES[@]}"; do
  [[ -z "${name}" ]] && continue
  dir="${ADDON_ROOT}/${name}/webui"
  if [[ ! -d "${dir}" ]]; then
    dir="${ROOT}/builtin/${name}/webui"
  fi
  if [[ ! -d "${dir}" ]]; then
    echo ">> skip ${name}: no webui/ (tools-only module)" >&2
    continue
  fi
  pkg_root="$(pkg_root_for "${dir}")"
  (
    cd "${dir}"
    if ensure_pnpm "${pkg_root}"; then
      echo ">> pnpm run build (${name})"
      pnpm run build
    else
      if [[ ! -d node_modules ]]; then
        echo ">> npm install (${name})"
        npm install
      fi
      echo ">> npm run build (${name})"
      npm run build
    fi
  )
done

echo "build ok: ${MODULES[*]}"
