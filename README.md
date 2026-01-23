# Laptop Health Dashboard (Linux)

Linux system health monitor with tray integration.

## Requirements

- Python 3
- Virtual environment (recommended)
- venv deps:
  - PySide6
  - psutil
- optional tools:
  - lm-sensors (`sensors`)
  - nvme-cli (`nvme`)
  - powerprofilesctl (power-profiles-daemon)
  - nvidia-smi (NVIDIA)
  - nmcli (NetworkManager) for Wi-Fi SSID/signal
  - speedtest (Ookla CLI) OR speedtest-cli for speed testing

## Run

```bash
source .venv/bin/activate
python main.py
.
├── main.py        # App entrypoint / orchestration
├── ui.py          # Qt UI widgets & layout
├── system.py      # OS, power, network helpers
├── sensors.py     # Hardware temperature sensors
├── .venv/         # Python virtual environment
├── .git/          # Git repository

### 3️⃣ Save and exit nano
- **Ctrl + O**
- **Enter**
- **Ctrl + X**

---

### 4️⃣ Commit it
```bash
git add README.md
git commit -m "docs: add README with project structure"
