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

---

## Features

- CPU temperature and load monitoring
- GPU and SSD temperature visibility
- Wake-up / power state awareness
- Power profile detection
- Network diagnostics module
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
pkexec apt install ./laptop-health_1.0.2-1_amd64.deb
```

Or manually:

```bash
sudo dpkg -i laptop-health_1.0.2-1_amd64.deb
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

Install them if needed:

```bash
sudo apt install lm-sensors powertop nvme-cli power-profiles-daemon network-manager
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

---

## Packaging

Build using PyInstaller:

```bash
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean --name laptop-health main.py
```

Debian packaging is handled manually using dpkg-deb.

---

## Versioning

Releases follow semantic versioning:

v1.x.y

Binary installers are attached to GitHub Releases.

---

## Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
