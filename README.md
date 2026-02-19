# Laptop Health

A lightweight Linux system health dashboard for laptops.

Laptop Health provides a clean, modern interface for monitoring system performance, thermals, and power state — built with PySide6 and designed for Linux Mint / Ubuntu environments.

---

## ✨ Features

- CPU temperature and load monitoring  
- GPU and SSD temperature visibility  
- Wake-up / power state awareness  
- Power profile detection  
- Network diagnostics module  
- Optional speed testing support  
- Dark mode support  
- Clean, card-based UI layout  

---

## 📦 Installation (Debian / Ubuntu / Mint)

Download the latest `.deb` from the **Releases** page.

Install using:

```bash
sudo apt install ./laptop-health_0.4.0-9_amd64.deb
```

If installing manually:

```bash
sudo dpkg -i laptop-health_0.4.0-9_amd64.deb

sudo apt -f install
```

---

## 🔧 Runtime Dependencies

Laptop Health relies on the following system tools:

- `lm-sensors`
- `powertop`
- `nvme-cli`
- `power-profiles-daemon`
- `network-manager`

Install them if needed:

```bash
sudo apt install lm-sensors powertop nvme-cli power-profiles-daemon network-manager
```

### Optional

- `nvidia-smi` (for NVIDIA GPUs)
- `speedtest` (Ookla CLI) or `speedtest-cli`

---

## ▶ Running

After installation:

```bash
laptop-health
```

Or launch it from your desktop application menu.

---

## 🧪 Development

Clone the repository:

```bash
git clone https://github.com/Heis1/laptop-health.git
cd laptop-health
```

Create a development virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install PySide6 psutil
```

Run:

```bash
python main.py
```

---

## 📦 Packaging

The project uses PyInstaller to create a self-contained binary:

```bash
pyinstaller --noconfirm --clean --name laptop-health main.py
```

Debian packaging is handled manually using `dpkg-deb`.

---

## 🔢 Versioning

Releases are tagged using semantic versioning:

```
v0.x.y
```

Binary installers are attached to GitHub Releases.

---

## 📜 License

N/A

---

## 🛣 Roadmap

- Improved hardware detection  
- Enhanced GPU support  
- Auto-update checks  
- Additional telemetry modules  
- CI-based automated builds  

---

## ⚠ Disclaimer

Laptop Health relies on underlying system tools for hardware metrics. Accuracy depends on your system configuration and installed utilities.
