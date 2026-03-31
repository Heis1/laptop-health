# Laptop Health

[![Latest Release](https://img.shields.io/github/v/release/Heis1/laptop-health?display_name=tag)](https://github.com/Heis1/laptop-health/releases)
[![Release Downloads](https://img.shields.io/github/downloads/Heis1/laptop-health/total)](https://github.com/Heis1/laptop-health/releases)
[![License](https://img.shields.io/github/license/Heis1/laptop-health)](https://github.com/Heis1/laptop-health/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

A modern Linux system health dashboard for laptops.

Laptop Health provides a clean, modular interface for monitoring system performance, thermals, storage, network activity, and power state — built with PySide6 and designed for Linux Mint / Ubuntu environments.

## Project Status

Stable release branch: main  

The current version includes:
- redesigned dashboard (UI v2)
- modular service architecture
- live sparklines and enhanced system metrics
- integrated update checking and download support
- configurable network discovery and improved live network monitoring
- Raspberry Pi probe support for remote monitoring inside the desktop app

---

## Features

- CPU temperature and load monitoring
- GPU and SSD temperature visibility
- Wake-up / power state awareness
- Power profile detection
- Remote Raspberry Pi probe card in the desktop dashboard
- Network diagnostics module
- Configurable device discovery with quiet/noisy scans
- Optional speed testing support
- Dark mode support
- Clean, card-based UI layout
- Sidebar version display
- GitHub update checking
- In-app update download support (.deb)

---

## Installation (Debian / Ubuntu / Mint)

Download the latest `.deb` from the Releases page.

Or download directly:

```bash
python3 download_latest_deb.py
```

This will fetch the latest release asset (preferring `amd64`).

Install using:

```bash
pkexec apt install ./laptop-health_1.1.0-1_amd64.deb
```

Or manually:

```bash
sudo dpkg -i laptop-health_1.1.0-1_amd64.deb
sudo apt -f install
```

---

## Runtime Dependencies

Laptop Health relies on the following system tools:

- lm-sensors
- powertop
- nvme-cli
- power-profiles-daemon
- network-manager
- nmap

Install them if needed:

```bash
sudo apt install lm-sensors powertop nvme-cli power-profiles-daemon network-manager nmap
```

Optional:

- nvidia-smi (for NVIDIA GPUs)
- speedtest or speedtest-cli

---

## Running

After installation:

```bash
laptop-health
```

Or from source:

```bash
python main.py
```

To run the new UI preview from source:

```bash
./run-v2.sh
```

Or:

```bash
source .venv/bin/activate
python ui_v2/app.py
```

---

## Development

Clone the repository:

```bash
git clone https://github.com/Heis1/laptop-health.git
cd laptop-health
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt
```

Run:

```bash
python main.py
```

For the new UI preview:

```bash
./run-v2.sh
```

## Raspberry Pi Probe

The repository includes a headless probe at `probe/pi_probe.py`.

This feature is currently under active development on `feature/pi-probe-integration`.

Current in-progress scope:

- guided in-app install and uninstall flow for Raspberry Pi probes
- multi-probe support in the desktop app
- customizable probe names
- rotating probe card on the overview dashboard
- hardened token handling and TLS verification

Quick deploy from your laptop:

```bash
./probe/setup_probe.sh
```

That interactive script prompts for:

- the Pi hostname or IP
- the Pi SSH user
- TLS mode
- the HTTPS hostname to put into the certificate
- the probe token, or it can generate one for you

At the end it prints the exact app settings to enter.

### How To Test The Probe Flow

From source:

```bash
./run-v2.sh
```

Then in the app:

1. Open `Probe/s`
2. Click `Add Probe`
3. Enter the Pi IP or hostname, SSH user, TLS mode, and token choice
4. Wait for the in-app installer to finish
5. Confirm the new probe appears on `Probe/s`
6. Confirm the overview dashboard shows the probe card when at least one probe is enabled
7. Add a second probe entry or rename the current one to test multi-probe switching
8. Use `Remove Current` to confirm the local entry disappears and the remote uninstall runs

Recommended verification:

- confirm `./probe/test_probe.sh` returns JSON for the configured probe
- confirm the app accepts the CA certificate at `probe/probe.crt` when using self-signed TLS
- confirm the overview card hides completely when no probes are enabled
- confirm manual prev/next switching and automatic rotation both work when multiple probes are enabled

If you want the non-interactive version, use:

```bash
export PI_PROBE_USER=pi
export PI_PROBE_TOKEN=choose-a-long-random-secret
bash ./probe/deploy_probe.sh raspberrypi.local
```

Remove the probe from a Pi:

```bash
./probe/remove_probe.sh
```

That script:

- copies the probe and service files to the Pi
- runs the service as the SSH user you selected with `PI_PROBE_USER`
- generates a self-signed TLS certificate by default
- enables and restarts the `pi-probe` systemd service
- copies the Pi certificate back to `probe/probe.crt` on your laptop
- reuses one SSH connection, so you should only need to authenticate once per deploy

Run it on the Raspberry Pi:

```bash
export PI_PROBE_TOKEN=choose-a-long-random-secret
python3 probe/pi_probe.py
```

Then in Laptop Health, use `Probe settings` and enter:

- URL: `http://raspberrypi.local:9821/metrics`
- Token: the same `PI_PROBE_TOKEN`

### HTTPS / TLS

The probe can serve HTTPS directly.

Set these on the Raspberry Pi before starting the probe:

```bash
export PI_PROBE_TOKEN=choose-a-long-random-secret
export PI_PROBE_TLS_CERT=/opt/pi-probe/certs/probe.crt
export PI_PROBE_TLS_KEY=/opt/pi-probe/certs/probe.key
python3 probe/pi_probe.py
```

Then point Laptop Health at:

- URL: `https://raspberrypi.local:9821/metrics`
- Token: the same `PI_PROBE_TOKEN`
- CA certificate: leave blank if the cert chains to a normal trusted CA, or set it to the local path of the Pi certificate if you are using a self-signed cert, for example `probe/probe.crt`

This means the dashboard verifies the probe certificate instead of blindly trusting the connection.

The deployment script supports:

```bash
PI_PROBE_USER=pi PI_PROBE_TOKEN=choose-a-long-random-secret PI_PROBE_TLS_MODE=self-signed bash ./probe/deploy_probe.sh raspberrypi.local
PI_PROBE_USER=pi PI_PROBE_TOKEN=choose-a-long-random-secret PI_PROBE_TLS_MODE=off bash ./probe/deploy_probe.sh raspberrypi.local
PI_PROBE_USER=pi PI_PROBE_TOKEN=choose-a-long-random-secret PI_PROBE_TLS_MODE=provided PI_PROBE_TLS_CERT_SOURCE=/path/to/probe.crt PI_PROBE_TLS_KEY_SOURCE=/path/to/probe.key bash ./probe/deploy_probe.sh raspberrypi.local
```

The desktop app stores non-secret probe settings in `~/.config/laptop-health/probes.json`.
Probe tokens are stored separately and written with restrictive permissions. On Linux desktops with `secret-tool` available, the app will also use the local secret store.

---

## Packaging

Build a release `.deb` with:

```bash
VERSION=1.1.0 ./release.sh
```

This produces:

```text
pkg/laptop-health_1.1.0-1_amd64.deb
```

The release script builds the PyInstaller bundle and then stages the Debian package with the required runtime dependencies.

---

## Versioning

Releases follow semantic versioning, for example `v1.1.0`.

Binary installers are attached to GitHub Releases.

---

## Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
