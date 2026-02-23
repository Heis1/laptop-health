# Laptop Health

A lightweight Linux system health dashboard for laptops.

Laptop Health provides a clean, modern interface for monitoring system performance, thermals, and power state — built with PySide6 and designed for Linux Mint / Ubuntu environments.

## Project Status

Production releases live on: `main`

UI v2 development is happening on: `feature/new-dashboard-ui`

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

## Installation (Debian / Ubuntu / Mint)

Download the latest `.deb` from the Releases page.

Install using:

    sudo apt install ./laptop-health_0.4.0-9_amd64.deb

If installing manually:

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
- speedtest (Ookla CLI) or speedtest-cli

## Running

After installation:

    laptop-health

Or launch it from your desktop application menu.

## Development

Clone the repository:

    git clone https://github.com/Heis1/laptop-health.git
    cd laptop-health

Create a development virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install PySide6 psutil

Run:

    python main.py

## Packaging

The project uses PyInstaller to create a self-contained binary:

    pyinstaller --noconfirm --clean --name laptop-health main.py

Debian packaging is handled manually using `dpkg-deb`.

## Versioning

Releases are tagged using semantic versioning:

    v0.x.y

Binary installers are attached to GitHub Releases.

## Roadmap

- Improved hardware detection
- Enhanced GPU support
- Auto-update checks
- Additional telemetry modules
- CI-based automated builds

## Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
