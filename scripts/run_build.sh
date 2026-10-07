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

for name in "${MODULES[@]}"; do
  [[ -z "${name}" ]] && continue
  dir="${ROOT}/addon/${name}/webui"
  if [[ ! -d "${dir}" ]]; then
    dir="${ROOT}/builtin/${name}/webui"
  fi
  if [[ ! -d "${dir}" ]]; then
    echo ">> skip ${name}: no webui/ (tools-only module)" >&2
    continue
  fi
  (
    cd "${dir}"
    if [[ ! -d node_modules ]]; then
      echo ">> npm install (${name})"
      npm install
    fi
    echo ">> npm run build (${name})"
    npm run build
  )
done

echo "build ok: ${MODULES[*]}"
