#!/usr/bin/env bash
# Build selected module webuis (dist only).
# Usage: scripts/run_build.sh <module> [module...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# make dev sources .env; make build must too, or external addons look tools-only.
# An explicit MODOOR_MODULE_ROOT (make image) stays as passed.
if [[ -z "${MODOOR_MODULE_ROOT:-}" && -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

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

pkg_root_for() {
  local dir="$1"
  local workspace=""
  if [[ -f "${ADDON_ROOT}/../pnpm-workspace.yaml" ]]; then
    workspace="$(cd "${ADDON_ROOT}/.." && pwd)"
    if [[ "${dir}" == "${workspace}"/* ]]; then
      echo "${workspace}"
      return
    fi
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

build_vite() {
  local label="$1"
  local dir="$2"
  if [[ ! -f "${dir}/package.json" ]]; then
    return 0
  fi
  local pkg_root
  pkg_root="$(pkg_root_for "${dir}")"
  (
    cd "${dir}"
    if ensure_pnpm "${pkg_root}"; then
      echo ">> pnpm run build (${label})"
      pnpm run build
    else
      if [[ ! -d node_modules ]]; then
        echo ">> npm install (${label})"
        npm install
      fi
      echo ">> npm run build (${label})"
      npm run build
    fi
  )
}

for name in "${MODULES[@]}"; do
  [[ -z "${name}" ]] && continue
  dir="${ADDON_ROOT}/${name}/webui"
  if [[ ! -d "${dir}" ]]; then
    dir="${ROOT}/inbuilt/${name}/webui"
  fi
  if [[ -d "${dir}" ]]; then
    build_vite "${name}" "${dir}"
  else
    echo ">> skip ${name}: no webui/ (tools-only module)" >&2
  fi
  mob="$(cd "${ADDON_ROOT}/.." && pwd)/mobile/${name}"
  if [[ -f "${mob}/package.json" ]]; then
    build_vite "mob/${name}" "${mob}"
  fi
done

echo "build ok: ${MODULES[*]}"
