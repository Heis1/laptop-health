Laptop Health

A modern Linux system health dashboard for laptops.

Laptop Health provides a clean, modular interface for monitoring system performance, thermals, storage, network activity, and power state — built with PySide6 and designed for Linux Mint / Ubuntu environments.

🚀 Project Status

Current stable release: main branch
Next-generation UI (v2) in development: feature/new-dashboard-ui

UI v2 introduces a redesigned dashboard architecture with modular services, live sparklines, improved updates handling, and enhanced system insight cards.

You can preview UI v2 by switching to the development branch:

git checkout feature/new-dashboard-ui
python ui_preview_v2.py

✨ Features (Stable)

CPU temperature and load monitoring

GPU and SSD temperature visibility

Wake-up / power state awareness

Power profile detection

Network diagnostics module

Optional speed testing support

Dark mode support

Clean, card-based UI layout

📦 Installation (Debian / Ubuntu / Mint)

Download the latest .deb from the Releases page.

Install:

sudo apt install ./laptop-health_0.4.0-9_amd64.deb

Or manually:

sudo dpkg -i laptop-health_0.4.0-9_amd64.deb
sudo apt -f install
🔧 Runtime Dependencies

Laptop Health relies on:

lm-sensors

powertop

nvme-cli

power-profiles-daemon

network-manager

Install if needed:

sudo apt install lm-sensors powertop nvme-cli power-profiles-daemon network-manager

Optional:

nvidia-smi (NVIDIA GPUs)

speedtest (Ookla CLI) or speedtest-cli

▶ Running

After installation:

laptop-health

Or from source:

python main.py
🧪 Development
git clone https://github.com/Heis1/laptop-health.git
cd laptop-health

python3 -m venv .venv
source .venv/bin/activate
pip install PySide6 psutil

python main.py
📦 Packaging

The project uses PyInstaller:

pyinstaller --noconfirm --clean --name laptop-health main.py

Debian packaging is handled manually using dpkg-deb.

🔢 Versioning

Releases follow semantic versioning:

v0.x.y

Binary installers are attached to GitHub Releases.

🛣 Roadmap

Finalize UI v2 dashboard architecture

Expanded updates handling

Additional telemetry modules

CI-based automated builds

Performance tuning & optimization

⚠ Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
