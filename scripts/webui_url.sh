#!/usr/bin/env bash
# Shared: parse MODOOR_WEBUI_URL → HOST / PORT / MODOOR_WEBUI_URL (normalized).
# Usage: source scripts/webui_url.sh && modoor_load_webui_url

modoor_load_webui_url() {
  local url="${MODOOR_WEBUI_URL:-http://127.0.0.1:8765}"
  url="${url%"${url##*[![:space:]]}"}"
  url="${url#"${url%%[![:space:]]*}"}"
  url="${url%/}"
  [[ -z "${url}" ]] && url="http://127.0.0.1:8765"

  local scheme="http" rest host port
  case "${url}" in
    https://*) scheme="https"; rest="${url#https://}" ;;
    http://*) scheme="http"; rest="${url#http://}" ;;
    *) rest="${url}" ;;
  esac

  host="${rest%%[:/]*}"
  local after="${rest#"${host}"}"
  if [[ "${after}" == :* ]]; then
    port="${after#:}"
    port="${port%%/*}"
  elif [[ "${scheme}" == "https" ]]; then
    port="443"
  elif [[ "${scheme}" == "http" ]]; then
    # bare http://host with no port → 80; default console uses 8765 when unset entirely
    port="80"
  else
    port="8765"
  fi

  HOST="${host:-127.0.0.1}"
  PORT="${port:-8765}"
  # Default console URL when env omitted
  if [[ -z "${MODOOR_WEBUI_URL:-}" ]]; then
    MODOOR_WEBUI_URL="http://127.0.0.1:8765"
    HOST="127.0.0.1"
    PORT="8765"
  else
    MODOOR_WEBUI_URL="${scheme}://${HOST}:${PORT}"
  fi
  export HOST PORT MODOOR_WEBUI_URL
}
