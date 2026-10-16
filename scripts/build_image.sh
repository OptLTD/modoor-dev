#!/usr/bin/env bash
# Stage core + named addons, build their webui dist, then docker build.
# Usage: scripts/build_image.sh <repo> <tag> <module> [module...]
# Example: scripts/build_image.sh optltd/modoor lyghh fleet freight
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO="${1:-}"
TAG="${2:-}"
shift 2 || true
MODULES=("$@")

if [[ -z "${REPO}" || -z "${TAG}" || ${#MODULES[@]} -eq 0 ]]; then
  echo "usage: make image <tag> <module> [module...]" >&2
  echo "  example: make image lyghh fleet freight" >&2
  exit 1
fi

if [[ ! "${TAG}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo "invalid image tag: ${TAG}" >&2
  exit 1
fi

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

PRO_ADDON="${ROOT}/../modoor-pro/addon"
if [[ -d "${PRO_ADDON}" ]]; then
  PRO_ADDON="$(cd "${PRO_ADDON}" && pwd)"
fi

resolve_module() {
  local name="$1"
  local root=""
  if [[ -n "${MODOOR_ADDON_ROOT:-}" ]]; then
    root="${MODOOR_ADDON_ROOT}"
    if [[ "${root}" != /* ]]; then
      root="${ROOT}/${root}"
    fi
    if [[ -f "${root}/${name}/module.yaml" ]]; then
      (cd "${root}/${name}" && pwd)
      echo "addon"
      return
    fi
  fi
  if [[ -f "${ROOT}/addon/${name}/module.yaml" ]]; then
    (cd "${ROOT}/addon/${name}" && pwd)
    echo "addon"
    return
  fi
  if [[ -n "${PRO_ADDON}" && -f "${PRO_ADDON}/${name}/module.yaml" ]]; then
    (cd "${PRO_ADDON}/${name}" && pwd)
    echo "addon"
    return
  fi
  if [[ -f "${ROOT}/builtin/${name}/module.yaml" ]]; then
    (cd "${ROOT}/builtin/${name}" && pwd)
    echo "builtin"
    return
  fi
  return 1
}

copy_tree() {
  local src="$1"
  local dest="$2"
  mkdir -p "${dest}"
  rsync -a \
    --exclude node_modules \
    --exclude __pycache__ \
    --exclude '*.pyc' \
    --exclude .vite \
    --exclude .DS_Store \
    --exclude tests \
    --exclude webui/src \
    --exclude 'webui/.env*' \
    "${src}/" "${dest}/"
}

PLATFORM_WEBUI=(base doc wiki skill flow)
ADDON_NAMES=()
ADDON_PATHS=()

for name in "${MODULES[@]}"; do
  if [[ ! "${name}" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "invalid module id: ${name}" >&2
    exit 1
  fi
  if ! resolved="$(resolve_module "${name}")"; then
    echo "unknown module: ${name}" >&2
    echo "  looked in ./addon, MODOOR_ADDON_ROOT, ../modoor-pro/addon, ./builtin" >&2
    exit 1
  fi
  kind="$(echo "${resolved}" | tail -n 1)"
  path="$(echo "${resolved}" | head -n 1)"
  if [[ "${kind}" == "addon" ]]; then
    ADDON_NAMES+=("${name}")
    ADDON_PATHS+=("${path}")
  fi
done

# Skip vite when dist is newer than the module sources and shared/.
dist_fresh() {
  local dir="$1"
  local dist="${dir}/dist/index.html"
  [[ -f "${dist}" ]] || return 1
  local shared=""
  if [[ -d "${dir}/../../.." ]]; then
    shared="$(cd "${dir}/../../.." && pwd)/shared"
  fi
  if [[ ! -d "${shared}" ]]; then
    shared="${ROOT}/shared"
  fi
  local args=()
  [[ -d "${dir}/src" ]] && args+=("${dir}/src")
  local file
  for file in index.html vite.config.ts package.json tsconfig.json; do
    [[ -f "${dir}/${file}" ]] && args+=("${dir}/${file}")
  done
  [[ -d "${shared}" ]] && args+=("${shared}")
  [[ ${#args[@]} -eq 0 ]] && return 1
  local newer=""
  # -L follows modoor-pro/shared → ../modoor-dev/shared
  newer="$(find -L "${args[@]}" -type f -newer "${dist}" -print -quit 2>/dev/null || true)"
  [[ -z "${newer}" ]]
}

chmod +x "${ROOT}/scripts/run_build.sh"
PLATFORM_NEED=()
for name in "${PLATFORM_WEBUI[@]}"; do
  dir="${ROOT}/builtin/${name}/webui"
  if [[ ! -d "${dir}" ]]; then
    continue
  fi
  if dist_fresh "${dir}"; then
    echo ">> skip ${name}: dist is up to date"
  else
    PLATFORM_NEED+=("${name}")
  fi
done
if [[ ${#PLATFORM_NEED[@]} -gt 0 ]]; then
  echo ">> build platform webui: ${PLATFORM_NEED[*]}"
  "${ROOT}/scripts/run_build.sh" "${PLATFORM_NEED[@]}"
fi

for i in "${!ADDON_NAMES[@]}"; do
  name="${ADDON_NAMES[$i]}"
  path="${ADDON_PATHS[$i]}"
  if [[ ! -d "${path}/webui" ]]; then
    echo ">> skip ${name}: no webui/"
    continue
  fi
  if dist_fresh "${path}/webui"; then
    echo ">> skip ${name}: dist is up to date"
    continue
  fi
  addon_root="$(cd "$(dirname "${path}")" && pwd)"
  echo ">> build addon webui: ${name} (${addon_root})"
  MODOOR_ADDON_ROOT="${addon_root}" "${ROOT}/scripts/run_build.sh" "${name}"
done

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/modoor-image.XXXXXX")"
cleanup() { rm -rf "${STAGE}"; }
trap cleanup EXIT

copy_tree "${ROOT}/modoor" "${STAGE}/modoor"
copy_tree "${ROOT}/builtin" "${STAGE}/builtin"
mkdir -p "${STAGE}/addon"
printf '%s\n' '# Selected business addons for this image.' > "${STAGE}/addon/__init__.py"

STATIC=(base doc wiki skill flow)
for i in "${!ADDON_NAMES[@]}"; do
  name="${ADDON_NAMES[$i]}"
  path="${ADDON_PATHS[$i]}"
  copy_tree "${path}" "${STAGE}/addon/${name}"
  STATIC+=("${name}")
done

FINAL_STATIC=()
for name in "${STATIC[@]}"; do
  if [[ -f "${STAGE}/builtin/${name}/webui/dist/index.html" || -f "${STAGE}/addon/${name}/webui/dist/index.html" ]]; then
    FINAL_STATIC+=("${name}")
  fi
done
STATIC_CSV="$(IFS=,; echo "${FINAL_STATIC[*]}")"

mkdir -p "${STAGE}/scripts"
cp "${ROOT}/pyproject.toml" "${ROOT}/README.md" "${ROOT}/LICENSE" "${ROOT}/Dockerfile" "${ROOT}/logo.png" "${STAGE}/"
cp "${ROOT}/scripts/docker-entrypoint.sh" "${STAGE}/scripts/docker-entrypoint.sh"
# Image does not ship external/. Drop it from the staged package list so pip install succeeds.
python3 - "${STAGE}/pyproject.toml" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
path.write_text(path.read_text().replace(', "external"', ""))
PY

IMAGE="${REPO}:${TAG}"
echo ">> docker build -t ${IMAGE}"
echo "   addons: ${ADDON_NAMES[*]:-none}"
echo "   static: ${STATIC_CSV}"

docker build \
  --build-arg "MODOOR_WEBUI_STATIC_MODULES=${STATIC_CSV}" \
  -f "${STAGE}/Dockerfile" \
  -t "${IMAGE}" \
  "${STAGE}"

echo "image ok: ${IMAGE}"
