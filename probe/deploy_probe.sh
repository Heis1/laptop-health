#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGET_HOST="${1:-}"
PROBE_TOKEN="${PI_PROBE_TOKEN:-}"
TARGET_USER="${PI_PROBE_USER:-pi}"
TARGET_BIND_HOST="${PI_PROBE_HOST:-0.0.0.0}"
TARGET_PORT="${PI_PROBE_PORT:-9821}"
INSTALL_DIR="${PI_PROBE_INSTALL_DIR:-/opt/pi-probe}"
SERVICE_NAME="pi-probe"
ENV_FILE_PATH="${PI_PROBE_ENV_FILE:-/etc/pi-probe.env}"
TOKEN_FILE_PATH="${PI_PROBE_TOKEN_FILE:-/etc/pi-probe.token}"
REMOTE_CERT_DIR="${PI_PROBE_CERT_DIR:-${INSTALL_DIR}/certs}"
REMOTE_CERT_PATH="${REMOTE_CERT_DIR}/probe.crt"
REMOTE_KEY_PATH="${REMOTE_CERT_DIR}/probe.key"
LOCAL_CERT_OUT="${PI_PROBE_LOCAL_CERT_OUT:-${ROOT_DIR}/probe/probe.crt}"
TLS_MODE="${PI_PROBE_TLS_MODE:-self-signed}"
TLS_CERT_SOURCE="${PI_PROBE_TLS_CERT_SOURCE:-}"
TLS_KEY_SOURCE="${PI_PROBE_TLS_KEY_SOURCE:-}"
TLS_CN="${PI_PROBE_TLS_CN:-raspberrypi.local}"

is_ipv4() {
  [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

if [[ -z "${TARGET_HOST}" ]]; then
  read -r -p "Pi hostname or IP: " TARGET_HOST
fi

if [[ -z "${PROBE_TOKEN}" ]]; then
  read -r -s -p "Probe token: " PROBE_TOKEN
  echo
fi

if [[ -z "${TARGET_HOST}" ]]; then
  echo "Usage: PI_PROBE_TOKEN=... $0 <pi-hostname-or-ip>"
  exit 1
fi

if [[ -z "${PROBE_TOKEN}" ]]; then
  echo "PI_PROBE_TOKEN is required"
  exit 1
fi

if [[ "${TLS_MODE}" != "self-signed" && "${TLS_MODE}" != "provided" && "${TLS_MODE}" != "off" ]]; then
  echo "PI_PROBE_TLS_MODE must be one of: self-signed, provided, off"
  exit 1
fi

if [[ "${TLS_MODE}" == "provided" ]]; then
  if [[ ! -f "${TLS_CERT_SOURCE}" || ! -f "${TLS_KEY_SOURCE}" ]]; then
    echo "For PI_PROBE_TLS_MODE=provided, set PI_PROBE_TLS_CERT_SOURCE and PI_PROBE_TLS_KEY_SOURCE to existing files"
    exit 1
  fi
fi

SSH_TARGET="${TARGET_USER}@${TARGET_HOST}"
CONTROL_PATH="/tmp/pi-probe-${TARGET_USER}@${TARGET_HOST}"
SSH_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=10m
  -o "ControlPath=${CONTROL_PATH}"
)

cleanup() {
  ssh "${SSH_OPTS[@]}" -O exit "${SSH_TARGET}" >/dev/null 2>&1 || true
}

remote_ssh() {
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "$@"
}

remote_scp_to() {
  scp "${SSH_OPTS[@]}" "$1" "${SSH_TARGET}:$2"
}

remote_scp_from() {
  scp "${SSH_OPTS[@]}" "${SSH_TARGET}:$1" "$2"
}

trap cleanup EXIT

echo "Installing probe on ${SSH_TARGET}"

remote_ssh "true"
remote_ssh "sudo mkdir -p '${INSTALL_DIR}' '${REMOTE_CERT_DIR}' /etc/systemd/system/${SERVICE_NAME}.service.d"
remote_scp_to "${SCRIPT_DIR}/pi_probe.py" "/tmp/pi_probe.py"
remote_scp_to "${SCRIPT_DIR}/pi-probe.service" "/tmp/pi-probe.service"

remote_ssh "sudo cp /tmp/pi_probe.py '${INSTALL_DIR}/pi_probe.py' && sudo cp /tmp/pi-probe.service /etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${TLS_MODE}" == "provided" ]]; then
  echo "Uploading provided TLS certificate and key"
  remote_scp_to "${TLS_CERT_SOURCE}" "/tmp/probe.crt"
  remote_scp_to "${TLS_KEY_SOURCE}" "/tmp/probe.key"
  remote_ssh "sudo cp /tmp/probe.crt '${REMOTE_CERT_PATH}' && sudo cp /tmp/probe.key '${REMOTE_KEY_PATH}' && sudo chown '${TARGET_USER}:${TARGET_USER}' '${REMOTE_CERT_PATH}' '${REMOTE_KEY_PATH}' && sudo chmod 644 '${REMOTE_CERT_PATH}' && sudo chmod 600 '${REMOTE_KEY_PATH}'"
elif [[ "${TLS_MODE}" == "self-signed" ]]; then
  echo "Generating self-signed certificate on the Pi"
  if is_ipv4 "${TLS_CN}"; then
    TLS_SAN="IP:${TLS_CN}"
  else
    TLS_SAN="DNS:${TLS_CN}"
  fi
  remote_ssh "sudo openssl req -x509 -newkey rsa:4096 -keyout '${REMOTE_KEY_PATH}' -out '${REMOTE_CERT_PATH}' -sha256 -days 365 -nodes -subj '/CN=${TLS_CN}' -addext 'subjectAltName=${TLS_SAN}' >/dev/null 2>&1 && sudo chown '${TARGET_USER}:${TARGET_USER}' '${REMOTE_CERT_PATH}' '${REMOTE_KEY_PATH}' && sudo chmod 644 '${REMOTE_CERT_PATH}' && sudo chmod 600 '${REMOTE_KEY_PATH}'"
  mkdir -p "$(dirname "${LOCAL_CERT_OUT}")"
  remote_scp_from "${REMOTE_CERT_PATH}" "${LOCAL_CERT_OUT}"
  echo "Copied certificate to ${LOCAL_CERT_OUT}"
fi

if [[ "${TLS_MODE}" == "off" ]]; then
  TLS_CERT_ENV=""
  TLS_KEY_ENV=""
else
  TLS_CERT_ENV="PI_PROBE_TLS_CERT=${REMOTE_CERT_PATH}"
  TLS_KEY_ENV="PI_PROBE_TLS_KEY=${REMOTE_KEY_PATH}"
fi

remote_ssh "cat <<EOF | sudo tee '${TOKEN_FILE_PATH}' >/dev/null
${PROBE_TOKEN}
EOF
sudo chown '${TARGET_USER}:${TARGET_USER}' '${TOKEN_FILE_PATH}'
sudo chmod 600 '${TOKEN_FILE_PATH}'
cat <<EOF | sudo tee '${ENV_FILE_PATH}' >/dev/null
PI_PROBE_PORT=${TARGET_PORT}
PI_PROBE_HOST=${TARGET_BIND_HOST}
${TLS_CERT_ENV}
${TLS_KEY_ENV}
EOF
sudo chown root:root '${ENV_FILE_PATH}'
sudo chmod 600 '${ENV_FILE_PATH}'"

remote_ssh "cat <<EOF | sudo tee /etc/systemd/system/${SERVICE_NAME}.service.d/override.conf >/dev/null
[Service]
User=${TARGET_USER}
EnvironmentFile=${ENV_FILE_PATH}
Environment=PI_PROBE_TOKEN_FILE=${TOKEN_FILE_PATH}
EOF"

remote_ssh "sudo systemctl daemon-reload && sudo systemctl enable --now ${SERVICE_NAME} && sudo systemctl restart ${SERVICE_NAME}"

if [[ "${TLS_MODE}" == "off" ]]; then
  VERIFY_CMD="curl -fsS -H 'Authorization: Bearer ${PROBE_TOKEN}' 'http://localhost:${TARGET_PORT}/metrics' >/dev/null 2>/dev/null"
  DASHBOARD_URL="http://${TARGET_HOST}:${TARGET_PORT}/metrics"
else
  if is_ipv4 "${TLS_CN}"; then
    VERIFY_CMD="curl -fsS --cacert '${REMOTE_CERT_PATH}' -H 'Authorization: Bearer ${PROBE_TOKEN}' 'https://${TLS_CN}:${TARGET_PORT}/metrics' >/dev/null 2>/dev/null"
  else
    VERIFY_CMD="curl -fsS --cacert '${REMOTE_CERT_PATH}' --resolve '${TLS_CN}:${TARGET_PORT}:127.0.0.1' -H 'Authorization: Bearer ${PROBE_TOKEN}' 'https://${TLS_CN}:${TARGET_PORT}/metrics' >/dev/null 2>/dev/null"
  fi
  DASHBOARD_URL="https://${TLS_CN}:${TARGET_PORT}/metrics"
fi

if ! remote_ssh "for attempt in 1 2 3 4 5 6 7 8 9 10; do ${VERIFY_CMD} && exit 0; sleep 1; done; exit 1"; then
  echo
  echo "Probe verification failed. Recent service status:"
  remote_ssh "sudo systemctl --no-pager --full status ${SERVICE_NAME} | sed -n '1,20p'"
  echo
  echo "Recent probe logs:"
  remote_ssh "sudo journalctl -u ${SERVICE_NAME} --no-pager -n 20"
  exit 1
fi

echo
echo "Deployment complete"
echo "Dashboard URL: ${DASHBOARD_URL}"
if [[ "${TLS_MODE}" == "self-signed" ]]; then
  echo "Laptop CA cert path: ${LOCAL_CERT_OUT}"
fi
echo "Systemd status:"
remote_ssh "systemctl --no-pager --full status ${SERVICE_NAME} | sed -n '1,12p'"
