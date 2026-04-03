#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-}"
TARGET_USER="${PI_PROBE_USER:-}"
INSTALL_DIR="${PI_PROBE_INSTALL_DIR:-/opt/pi-probe}"
SERVICE_NAME="pi-probe"
ENV_FILE_PATH="${PI_PROBE_ENV_FILE:-/etc/pi-probe.env}"
TOKEN_FILE_PATH="${PI_PROBE_TOKEN_FILE:-/etc/pi-probe.token}"
LOCAL_CERT_OUT="${PI_PROBE_LOCAL_CERT_OUT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/probe/probe.crt}"

if [[ -z "${TARGET_HOST}" ]]; then
  read -r -p "Pi hostname or IP: " TARGET_HOST
fi

if [[ -z "${TARGET_USER}" ]]; then
  read -r -p "Pi SSH user: " TARGET_USER
fi

if [[ -z "${TARGET_HOST}" || -z "${TARGET_USER}" ]]; then
  echo "Pi hostname/IP and SSH user are required."
  exit 1
fi

SSH_TARGET="${TARGET_USER}@${TARGET_HOST}"
CONTROL_PATH="/tmp/pi-probe-remove-${TARGET_USER}@${TARGET_HOST}"
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

trap cleanup EXIT

echo "Removing probe from ${SSH_TARGET}"
remote_ssh "true"
remote_ssh "sudo systemctl disable --now '${SERVICE_NAME}' >/dev/null 2>&1 || true
sudo rm -f '/etc/systemd/system/${SERVICE_NAME}.service'
sudo rm -f '/etc/systemd/system/${SERVICE_NAME}.service.d/override.conf'
sudo rmdir '/etc/systemd/system/${SERVICE_NAME}.service.d' >/dev/null 2>&1 || true
sudo rm -f '${ENV_FILE_PATH}' '${TOKEN_FILE_PATH}'
sudo rm -rf '${INSTALL_DIR}'
sudo systemctl daemon-reload"

rm -f "${LOCAL_CERT_OUT}"

echo
echo "Probe removed from ${SSH_TARGET}"
echo "Local certificate removed: ${LOCAL_CERT_OUT}"
