# Laptop Health

[![Latest Release](https://img.shields.io/github/v/release/Heis1/laptop-health?display_name=tag)](https://github.com/Heis1/laptop-health/releases)
[![Release Downloads](https://img.shields.io/github/downloads/Heis1/laptop-health/total)](https://github.com/Heis1/laptop-health/releases)
[![License](https://img.shields.io/github/license/Heis1/laptop-health)](https://github.com/Heis1/laptop-health/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

A modern Linux system health dashboard for laptops.

Laptop Health provides a clean, modular interface for monitoring system performance, thermals, storage, network activity, and power state — built with PySide6 and designed for Linux Mint / Ubuntu environments.

## Project Status

Stable release branch: main  
UI v2 development branch: feature/new-dashboard-ui  

UI v2 introduces a redesigned dashboard architecture with modular services, live sparklines, improved updates handling, enhanced system insight cards, and sidebar version/update checking.

To preview UI v2:

    git checkout feature/new-dashboard-ui
    python ui_preview_v2.py

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

## Installation (Debian / Ubuntu / Mint)

Download the latest `.deb` from the Releases page.

Or download it directly from the repo:

    python3 download_latest_deb.py

This saves the newest release asset in the current directory, preferring the `amd64` package by default.

Install using:

    pkexec apt install ./laptop-health_0.4.0-9_amd64.deb

Or manually:

    sudo dpkg -i laptop-health_0.4.0-9_amd64.deb
    sudo apt -f install

## Runtime Dependencies

Laptop Health relies on the following system tools:

- lm-sensors
- powertop
- nvme-cli
- power-profiles-daemon
- network-manager

Install them if needed:

    sudo apt install lm-sensors powertop nvme-cli power-profiles-daemon network-manager

Optional:

- nvidia-smi (for NVIDIA GPUs)
- speedtest or speedtest-cli

## Running

After installation:

    laptop-health

Or from source:

    python main.py

For UI v2 preview:

    python ui_preview_v2.py

## Development

Clone the repository:

    git clone https://github.com/Heis1/laptop-health.git
    cd laptop-health

Create a virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-build.txt

Run:

    python main.py

## Packaging

Build using PyInstaller:

    pip install -r requirements-build.txt
    pyinstaller --noconfirm --clean --name laptop-health main.py

Debian packaging is handled manually using dpkg-deb.

## Versioning

Releases follow semantic versioning:

    v1.x.y

Binary installers are attached to GitHub Releases.

## Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
