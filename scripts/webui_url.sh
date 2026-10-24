#!/usr/bin/env bash
# Shared: parse MODOOR_MODULE_GATE → HOST / PORT / MODOOR_MODULE_GATE (normalized).
# A public gate is only the link origin. Listen stays on 127.0.0.1:8765.
# Usage: source scripts/webui_url.sh && modoor_load_webui_url

modoor_gate_is_public() {
  local host
  host="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  host="${host%.}"
  [[ -z "${host}" || "${host}" == "localhost" || "${host}" == "localhost.localdomain" ]] && return 1
  [[ "${host}" == *.local || "${host}" == *.localhost || "${host}" == *.internal ]] && return 1
  [[ "${host}" != *.* ]] && return 1
  case "${host}" in
    127.*|10.*|192.168.*|169.254.*|0.0.0.0) return 1 ;;
    172.1[6-9].*|172.2[0-9].*|172.3[0-1].*) return 1 ;;
  esac
  return 0
}

modoor_load_webui_url() {
  local url="${MODOOR_MODULE_GATE:-${MODOOR_WEBUI_URL:-http://127.0.0.1:8765}}"
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
  # Public URL is for links. The process still listens on the local console.
  if modoor_gate_is_public "${HOST}"; then
    if [[ "${scheme}" == "http" && "${PORT}" == "80" ]] || [[ "${scheme}" == "https" && "${PORT}" == "443" ]]; then
      MODOOR_MODULE_GATE="${scheme}://${HOST}"
    else
      MODOOR_MODULE_GATE="${scheme}://${HOST}:${PORT}"
    fi
    HOST="127.0.0.1"
    PORT="8765"
    export HOST PORT MODOOR_MODULE_GATE
    return
  fi
  # Default console URL when env omitted
  if [[ -z "${MODOOR_MODULE_GATE:-}${MODOOR_WEBUI_URL:-}" ]]; then
    MODOOR_MODULE_GATE="http://127.0.0.1:8765"
    HOST="127.0.0.1"
    PORT="8765"
  else
    MODOOR_MODULE_GATE="${scheme}://${HOST}:${PORT}"
  fi
  export HOST PORT MODOOR_MODULE_GATE
}
