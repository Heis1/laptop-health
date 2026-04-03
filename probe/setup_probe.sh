#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

save_local_probe_config() {
  local enabled="$1"
  local name="$2"
  local url="$3"
  local token="$4"
  local cert_path="$5"
  local config_dir="${HOME}/.config/laptop-health"
  local config_path="${config_dir}/probes.json"
  local probe_id
  probe_id="probe-$(openssl rand -hex 6 2>/dev/null || od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"

  mkdir -p "${config_dir}"
  chmod 700 "${config_dir}" || true

  cat > "${config_path}" <<EOF
{
  "probes": [
    {
      "id": "${probe_id}",
      "enabled": ${enabled},
      "name": "${name}",
      "url": "${url}",
      "ca_cert_path": "${cert_path}"
    }
  ]
}
EOF
  chmod 600 "${config_path}" || true

  if ! command -v secret-tool >/dev/null 2>&1; then
    echo
    echo "Desktop secret storage is required to save the probe token securely."
    echo "Install libsecret-tools and rerun this helper, or configure the token manually in the app."
    echo "No local plaintext token file was written."
    return 1
  fi

  if ! printf '%s' "${token}" | secret-tool store \
    --label "Laptop Health pi-probe (${probe_id})" \
    service laptop-health \
    account "pi-probe:${probe_id}" >/dev/null 2>&1; then
    echo
    echo "Failed to save the probe token into the desktop secret store."
    echo "No local plaintext token file was written."
    return 1
  fi

  return 0
}

default_tls_host() {
  local host="$1"
  printf '%s' "${host}"
}

echo "Laptop Health Pi Probe Setup"
echo "Target devices must be Linux systems with SSH, sudo, and systemd."
echo "Recommended targets: Raspberry Pi OS and other Debian-family Linux systems."
echo

TARGET_HOST="$(prompt_default "Pi hostname or IP" "")"
if [[ -z "${TARGET_HOST}" ]]; then
  echo "Pi hostname or IP is required."
  exit 1
fi

TARGET_USER="$(prompt_default "Pi SSH user" "pi")"
PROBE_NAME="$(prompt_default "Probe name" "Raspberry Pi")"
PROBE_BIND_HOST="$(prompt_default "Probe bind address" "0.0.0.0")"
PROBE_PORT="$(prompt_default "Probe port" "9821")"
TLS_MODE_CHOICE="$(prompt_default "TLS mode (self-signed/off)" "self-signed")"

if ! [[ "${PROBE_PORT}" =~ ^[0-9]+$ ]] || (( PROBE_PORT < 1 || PROBE_PORT > 65535 )); then
  echo "Probe port must be a number between 1 and 65535."
  exit 1
fi

case "${TLS_MODE_CHOICE}" in
  self-signed|off)
    ;;
  *)
    echo "TLS mode must be 'self-signed' or 'off'."
    exit 1
    ;;
esac

TLS_CN=""
APP_HOST="${TARGET_HOST}"
if [[ "${TLS_MODE_CHOICE}" == "self-signed" ]]; then
  TLS_CN="$(prompt_default "Hostname or IP your laptop will use for HTTPS" "$(default_tls_host "${TARGET_HOST}")")"
  if [[ -z "${TLS_CN}" ]]; then
    echo "HTTPS hostname or IP is required for self-signed TLS."
    exit 1
  fi
  APP_HOST="${TLS_CN}"
fi

echo
read -r -s -p "Probe token (leave blank to generate one): " PROBE_TOKEN
echo
if [[ -z "${PROBE_TOKEN}" ]]; then
  PROBE_TOKEN="$(generate_token)"
fi

echo
echo "Starting deploy..."
echo "You may be prompted once for your Pi SSH password and once for sudo."
echo

export PI_PROBE_USER="${TARGET_USER}"
export PI_PROBE_TOKEN="${PROBE_TOKEN}"
export PI_PROBE_HOST="${PROBE_BIND_HOST}"
export PI_PROBE_PORT="${PROBE_PORT}"
export PI_PROBE_TLS_MODE="${TLS_MODE_CHOICE}"
if [[ -n "${TLS_CN}" ]]; then
  export PI_PROBE_TLS_CN="${TLS_CN}"
fi

"${SCRIPT_DIR}/deploy_probe.sh" "${TARGET_HOST}"

if [[ "${TLS_MODE_CHOICE}" == "self-signed" ]]; then
  APP_URL="https://${APP_HOST}:${PROBE_PORT}/metrics"
  APP_CA_CERT="${ROOT_DIR}/probe/probe.crt"
else
  APP_URL="http://${APP_HOST}:${PROBE_PORT}/metrics"
  APP_CA_CERT=""
fi

SAVE_LOCAL_OK=0
if save_local_probe_config true "${PROBE_NAME}" "${APP_URL}" "${PROBE_TOKEN}" "${APP_CA_CERT}"; then
  SAVE_LOCAL_OK=1
fi

echo
if [[ "${SAVE_LOCAL_OK}" == "1" ]]; then
  echo "Saved probe settings locally for the app."
  echo "Open Probe settings to review if needed."
else
  echo "Probe deployed on the device, but local token save was skipped."
  echo "Open Probe settings in the app and paste the probe token manually."
fi
if [[ "${TLS_MODE_CHOICE}" == "self-signed" ]]; then
  echo "URL: ${APP_URL}"
  echo "CA certificate: ${APP_CA_CERT}"
  echo
  echo "Quick test from this laptop:"
  echo "./probe/test_probe.sh"
else
  echo "URL: ${APP_URL}"
  echo "CA certificate: leave blank"
  echo
  echo "Quick test from this laptop:"
  echo "./probe/test_probe.sh"
fi
