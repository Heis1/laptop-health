#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CERT="${ROOT_DIR}/probe/probe.crt"

prompt_default() {
  local label="$1"
  local default_value="$2"
  local reply
  if [[ -n "${default_value}" ]]; then
    read -r -p "${label} [${default_value}]: " reply
    printf '%s' "${reply:-$default_value}"
  else
    read -r -p "${label}: " reply
    printf '%s' "${reply}"
  fi
}

URL="$(prompt_default "Probe URL" "https://192.0.2.51:9821/metrics")"
CERT_PATH="$(prompt_default "CA certificate path" "${DEFAULT_CERT}")"
read -r -s -p "Probe token: " TOKEN
echo

echo
echo "Requesting probe metrics..."
curl --cacert "${CERT_PATH}" -H "Authorization: Bearer ${TOKEN}" "${URL}"
echo
