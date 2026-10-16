#!/bin/sh
# Base image stays small. Optional packages install into MODOOR_PY_CACHE.
set -eu

PY_CACHE="${MODOOR_PY_CACHE:-/var/cache/modoor/py}"
mkdir -p "${PY_CACHE}"
export MODOOR_PY_CACHE="${PY_CACHE}"
export PYTHONPATH="${PY_CACHE}${PYTHONPATH:+:$PYTHONPATH}"

ocr_on() {
  case "$(printf '%s' "${MODOOR_DOC_OCR:-0}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

backend() {
  printf '%s' "${MODOOR_OCR_BACKEND:-tesseract}" | tr '[:upper:]' '[:lower:]'
}

if ocr_on; then
  if ! python -c "import pypdfium2, PIL" >/dev/null 2>&1; then
    echo ">> install pypdfium2 and pillow into ${PY_CACHE}"
    pip install --no-cache-dir --target "${PY_CACHE}" "pypdfium2>=4.30" "pillow>=10.0"
  fi
  case "$(backend)" in
    external|http|remote) ;;
    *)
      if ! command -v tesseract >/dev/null 2>&1; then
        echo ">> install tesseract"
        apk add --no-cache tesseract-ocr tesseract-ocr-data-chi_sim tesseract-ocr-data-eng
      fi
      ;;
  esac
fi

exec "$@"
