from __future__ import annotations

from collections import deque

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QSizePolicy

from ui_v2.widgets.cards import MetricCard, UpdatesCard, WakeupsCard, apply_responsive_card_fonts
from ui_v2.widgets.disk_usage_card import DiskUsageCard
from ui_v2.widgets.network_card import NetworkCard
from ui_v2.widgets.inspector import Inspector
from ui_v2.workers import Worker
from ui_v2.services.overview_metrics import gather_overview, OverviewMetrics, gather_fast, gather_slow
from ui_v2.services.gpu_metrics import get_gpu, GpuInfo
from ui_v2.services.refresh_controller import RefreshController, RefreshState


def _fix_top_row_heights(*widgets, h: int = 165) -> None:
    # Keep a readable minimum height but still allow resize.
    for w in widgets:
        try:
            w.setMinimumHeight(h)
            w.setMaximumHeight(16777215)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            w.setMinimumWidth(0)
        except Exception:
            pass


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _fmt_cpu(temp_c: float | None, ghz: float | None) -> tuple[str, str, str]:
    if temp_c is None:
        big = "—"
        accent = "blue"
    else:
        big = f"{temp_c:.0f}°C"
        accent = "green" if temp_c < 55 else ("orange" if temp_c < 75 else "red")
    sub = "—" if ghz is None else f"{ghz:.1f} GHz"
    return big, sub, accent


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self._workers: list[object] = []
        self._top_cards: list[QWidget] = []
        self._mid_cards: list[QWidget] = []

        # Sparkline histories (store 0..1 floats)
        self._cpu_hist = deque([0.0] * 30, maxlen=30)
        self._gpu_hist = deque([0.0] * 30, maxlen=30)

        # GPU last-known values (avoid flicker / avoid overwriting with None)
        self._gpu_last_temp: float | None = None
        self._gpu_last_util: float | None = None
        self._gpu_last_name: str | None = None


        # Cache fast-owned bottom-row metrics so slow refresh can't reset them
        self._last_wakeups = ("—", "—", "green")  # (big, sub, accent)
        self._last_net = (None, None)  # (down_mbps, latency_ms)

        # Cache fast metrics so slow refresh (None fields) can't zero the UI
        self._fast_cache: dict[str, object] = {}

        self._updates_last = None  # cache slow updates

        # cache slow metrics so fast refresh can't wipe them
        self._disk_home_used = None
        self._disk_home_free = None
        self._disk_root_free = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        # Keep the 1-column cards visibly wider while preserving the 2-column spans.
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 4)
        grid.setColumnStretch(3, 4)

        # Top row
        self.cpu = MetricCard("CPU", "—", "—", "green", spark_points=[0.0]*24)
        self.gpu = MetricCard("GPU", "—", "—", "blue", spark_points=[0.0]*24)
        self.cpu.big_lbl.setObjectName("CardHuge")
        self.gpu.big_lbl.setObjectName("CardHuge")
        self.cpu.sub_lbl.setWordWrap(True)
        self.gpu.sub_lbl.setWordWrap(True)
        apply_responsive_card_fonts(self.cpu)
        apply_responsive_card_fonts(self.gpu)

        self.disk = DiskUsageCard(0, "—")
        try:
            self.disk.title.setText("Disk Usage (Home)")
        except Exception:
            pass

        _fix_top_row_heights(self.cpu, self.gpu, self.disk, h=165)
        for w in (self.cpu, self.gpu):
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            w.setMinimumWidth(0)
        self._top_cards = [self.cpu, self.gpu, self.disk]

        grid.addWidget(self.cpu, 0, 0)
        grid.addWidget(self.gpu, 0, 1)
        grid.addWidget(self.disk, 0, 2, 1, 2)

        # Second row
        self.wakeups = WakeupsCard("green")
        self.updates = UpdatesCard("red")
        self.updates.details_requested.connect(self._go_updates)
        self.net = NetworkCard()

        for w in (self.wakeups, self.updates):
            w.setMinimumHeight(165)
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            w.setMinimumWidth(0)
        self.net.setMinimumHeight(165)
        self.net.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.net.setMinimumWidth(0)
        self._mid_cards = [self.wakeups, self.updates, self.net]

        grid.addWidget(self.wakeups, 1, 0)
        grid.addWidget(self.updates, 1, 1)
        grid.addWidget(self.net, 1, 2, 1, 2)

        # Let cards compress with the window instead of pinning desktop widths.
        for card in (self.cpu, self.gpu, self.disk, self.wakeups, self.updates, self.net):
            try:
                card.setMinimumWidth(0)
            except Exception:
                pass

        outer.addLayout(grid)
        self.inspector = Inspector()
        outer.addWidget(self.inspector)

        # Refresh controller (debounce + busy state)
        self._refresh_ctl = RefreshController(min_interval_ms=700)
        self._refresh_ctl.stateChanged.connect(self._on_refresh_state)
        self._refresh_ctl.refreshRequested.connect(self._do_refresh_now)


        self._refresh_ctl.request_refresh("Refreshing…")
        # Kick once for initial paint
        self._refresh_fast()
        self._refresh_slow()

        # Fast: CPU/Wake/Net + Inspector feel
        self.timer_fast = QTimer(self)
        self.timer_fast.setInterval(2000)
        self.timer_fast.timeout.connect(self._refresh_fast)
        self.timer_fast.start()

        # Slow: disk + updates
        self.timer_slow = QTimer(self)
        self.timer_slow.setInterval(60000)
        self.timer_slow.timeout.connect(self._refresh_slow)
        self.timer_slow.start()

        # GPU cadence gate (~5s)
        self._gpu_last_ts = 0.0
        self._apply_responsive_card_sizes()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_card_sizes()

    def _apply_responsive_card_sizes(self) -> None:
        width = max(900, self.width())
        if width >= 1400:
            row_h = 175
            spark_h = 54
        elif width >= 1180:
            row_h = 165
            spark_h = 48
        elif width >= 1020:
            row_h = 156
            spark_h = 42
        else:
            row_h = 148
            spark_h = 38

        for card in self._top_cards + self._mid_cards:
            try:
                card.setMinimumHeight(row_h)
                card.setMaximumHeight(16777215)
            except Exception:
                pass

        for spark_owner in (self.cpu, self.gpu):
            try:
                if getattr(spark_owner, "spark", None) is not None:
                    spark_owner.spark.setMinimumHeight(spark_h)
                    spark_owner.spark.setMaximumHeight(spark_h)
            except Exception:
                pass

    def _refresh_fast(self):
        # Fast metrics (non-blocking)
        w = Worker(lambda: gather_fast())
        self._workers.append(w)

        def _done(res):
            try:
                self._apply(res)
            finally:
                try:
                    self._workers.remove(w)
                except ValueError:
                    pass

        w.signals.finished.connect(_done)
        self.pool.start(w)

        # GPU gated to ~5s
        try:
            import time as _time
            now = _time.time()
            if now - getattr(self, "_gpu_last_ts", 0.0) >= 5.0:
                self._gpu_last_ts = now
                wg = Worker(get_gpu)
                self._workers.append(wg)

                def _done_g(res):
                    try:
                        self._apply_gpu(res)
                    finally:
                        try:
                            self._workers.remove(wg)
                        except ValueError:
                            pass

                wg.signals.finished.connect(_done_g)
                self.pool.start(wg)
        except Exception:
            pass

    def _refresh_slow(self):
        # Slow metrics (disk + updates)
        w = Worker(lambda: gather_slow())
        self._workers.append(w)

        def _done(res):
            try:
                self._apply(res)
            finally:
                try:
                    self._workers.remove(w)
                except ValueError:
                    pass

        w.signals.finished.connect(_done)
        self.pool.start(w)


    def _refresh(self):
        # Wrapper kept for compatibility: route refresh through controller
        try:
            self._refresh_ctl.request_refresh("Refreshing…")
        except Exception:
            # Fallback: if controller isn't ready for some reason, run directly
            self._do_refresh_now()

    def _do_refresh_now(self) -> None:
        """Actual refresh pipeline (previously _refresh())."""
        # Overview (CPU/disk/network/updates)
        w = Worker(lambda: gather_overview(interval_s=1.0))
        self._workers.append(w)
        def _done_overview(res):
            try:
                self._apply(res)
            finally:
                try:
                    self._workers.remove(w)
                except ValueError:
                    pass
        w.signals.finished.connect(_done_overview)
        self.pool.start(w)

        # GPU (separate worker so Overview doesn’t block)
        w_gpu = Worker(get_gpu)
        self._workers.append(w_gpu)
        def _done_gpu(res):
            try:
                self._apply_gpu(res)
            finally:
                try:
                    self._workers.remove(w_gpu)
                except ValueError:
                    pass
        w_gpu.signals.finished.connect(_done_gpu)
        self.pool.start(w_gpu)
    def _apply_gpu(self, r):
        # Ignore garbage / failures (don’t overwrite UI with — every tick)
        if not isinstance(r, GpuInfo):
            return

        if r.name:
            self._gpu_last_name = r.name
        if r.temp_c is not None:
            self._gpu_last_temp = r.temp_c
        if r.busy_pct is not None:
            self._gpu_last_util = r.busy_pct

        # If still nothing useful, show once but don’t flicker
        if self._gpu_last_temp is None and self._gpu_last_util is None:
            self.gpu.set_values("—", "GPU metrics unavailable", "blue")
            return

        # Spark: prefer util, else temp
        try:
            if self._gpu_last_util is not None:
                self._gpu_hist.append(_norm01(self._gpu_last_util, 0.0, 100.0))
            elif self._gpu_last_temp is not None:
                self._gpu_hist.append(_norm01(self._gpu_last_temp, 30.0, 95.0))
            self.gpu.set_spark(list(self._gpu_hist))
        except Exception:
            pass

        # Display
        if self._gpu_last_temp is None:
            big = "—"
            accent = "blue"
        else:
            big = f"{self._gpu_last_temp:.0f}°C"
            accent = "green" if self._gpu_last_temp < 60 else ("orange" if self._gpu_last_temp < 80 else "red")

        util = "—" if self._gpu_last_util is None else f"{self._gpu_last_util:.0f}% load"
        name = self._gpu_last_name or "GPU"
        self.gpu.set_values(big, f"{name} • {util}", accent)


    def _apply(self, result):
        def _cache(k: str, v):
            if v is not None:
                self._fast_cache[k] = v
            return self._fast_cache.get(k)

        if not isinstance(result, OverviewMetrics):
            return

        # CPU numbers + spark (temp mapped 30..95°C)
        big, sub, accent = _fmt_cpu(_cache("cpu_temp_c", result.cpu_temp_c), _cache("cpu_freq_ghz", result.cpu_freq_ghz))
        self.cpu.set_values(big, sub, accent)
        if _cache("cpu_temp_c", result.cpu_temp_c) is not None:
            self._cpu_hist.append(_norm01(_cache("cpu_temp_c", result.cpu_temp_c), 30.0, 95.0))
            try:
                self.cpu.set_spark(list(self._cpu_hist))
            except Exception:
                pass

        # Disk (Home + Root in subtitle)

        # Only update disk values when slow refresh provides them
        if result.home_used_pct is not None:
            self._disk_home_used = result.home_used_pct
        if result.home_free_gb is not None:
            self._disk_home_free = result.home_free_gb
        if result.root_free_gb is not None:
            self._disk_root_free = result.root_free_gb

        home_used = self._disk_home_used
        home_free = self._disk_home_free
        root_free = self._disk_root_free

        disk_accent = "orange"
        if root_free is not None:
            if root_free < 5:
                disk_accent = "red"
            elif root_free < 8:
                disk_accent = "orange"

        try:
            self.disk.setProperty("accent", disk_accent)
            self.disk.style().unpolish(self.disk)
            self.disk.style().polish(self.disk)
            self.disk.update()
        except Exception:
            pass

        if home_used is None:
            self.disk.big.setText("—")
            self.disk.bar.setValue(0)
        else:
            self.disk.big.setText(f"{int(home_used)}% Used")
            self.disk.bar.setValue(max(0, min(100, int(home_used))))

        if home_free is None and root_free is None:
            self.disk.sub.setText("—")
        else:
            hf = "—" if home_free is None else f"{home_free:.0f} GB Free"
            rf = "—" if root_free is None else f"{root_free:.0f} GB Free"
            self.disk.sub.setText(f"Home: {hf}   •   Root: {rf}")
        # Wakeups + Network + Updates
        # Fast loop owns wakeups/net; slow loop owns updates. Cache fast values so slow tick can't wipe them.
        try:
            wb = getattr(result, 'wakeups_big', None)
            ws = getattr(result, 'wakeups_sub', None)
            wa = getattr(result, 'wakeups_accent', None)
            if wb is not None or ws is not None or wa is not None:
                self._last_wakeups = (
                    wb if wb is not None else self._last_wakeups[0],
                    ws if ws is not None else self._last_wakeups[1],
                    wa if wa is not None else self._last_wakeups[2],
                )
            self.wakeups.set_values(*self._last_wakeups)
        except Exception:
            pass

        try:
            dm = getattr(result, 'down_mbps', None)
            lm = getattr(result, 'latency_ms', None)
            if dm is not None or lm is not None:
                self._last_net = (
                    dm if dm is not None else self._last_net[0],
                    lm if lm is not None else self._last_net[1],
                )
            self.net.set_network(self._last_net[0], self._last_net[1])
        except Exception:
            pass

        # Updates: FAST results often omit these fields; don't overwrite with Unknown
        try:
            u_total = getattr(result, 'updates_available', None)
            u_sec = getattr(result, 'security_updates', None)
            u_reb = getattr(result, 'reboot_required', None)
            u_kb = getattr(result, 'kept_back_updates', 0)
            u_held = getattr(result, 'held_updates', 0)
            u_badge = getattr(result, 'updates_badge', None)
            u_acc = getattr(result, 'updates_accent', None)
            has_any = any(v is not None for v in (u_total, u_sec, u_reb, u_badge, u_acc))
            if has_any:
                self._updates_last = (u_total, u_sec, u_reb, u_kb, u_held, u_badge, u_acc)
                self.updates.set_updates(*self._updates_last)
            elif self._updates_last is not None:
                # keep last-known slow values on fast ticks
                pass
        except Exception:
            pass
        # Back-compat: expose numeric wakeup fields for widgets that expect numbers
        # We currently only have strings like "0 ctx/s" and "0 intr/s".
        try:
            def _num(x):
                if x is None:
                    return None
                if isinstance(x, (int, float)):
                    return float(x)
                if isinstance(x, str):
                    mm = re.search(r"([-+]?[0-9]*\.?[0-9]+)", x)
                    return float(mm.group(1)) if mm else None
                return None

            # Common numeric names Wakeup Analysis widgets tend to use
            if getattr(result, "ctx_per_s", None) is None:
                v = _num(getattr(result, "wakeups_big", None))
                if v is not None:
                    setattr(result, "ctx_per_s", v)

            if getattr(result, "intr_per_s", None) is None:
                v = _num(getattr(result, "wakeups_sub", None))
                if v is not None:
                    setattr(result, "intr_per_s", v)

            # Also offer some alias names, just in case
            if getattr(result, "wakeups_per_s", None) is None and getattr(result, "intr_per_s", None) is not None:
                setattr(result, "wakeups_per_s", getattr(result, "intr_per_s"))

        except Exception:
            pass

        # Inspector owns the CPU Details + Wakeup Analysis cards
        try:
            self.inspector.update_overview(result)
        except Exception:
            pass

    def _on_refresh_state(self, st: RefreshState) -> None:
        # Safe: works even if you haven't added _overlay/_status/buttons yet
        try:
            status = getattr(self, "_status", None)
            overlay = getattr(self, "_overlay", None)

            if st.busy:
                if status is not None:
                    status.setText(st.message or "Refreshing…")
                if overlay is not None:
                    try:
                        overlay.setText(st.message or "Refreshing…")
                    except Exception:
                        pass
                    try:
                        overlay.start()
                    except Exception:
                        pass

                # Optional: disable common buttons if present
                for name in ("refresh_btn", "run_speedtest_btn"):
                    b = getattr(self, name, None)
                    if b is not None:
                        try:
                            b.setEnabled(False)
                        except Exception:
                            pass
                return

            # Not busy
            if overlay is not None:
                try:
                    overlay.stop()
                except Exception:
                    pass

            if status is not None:
                if st.last_ok_epoch_ms is not None:
                    from PySide6.QtCore import QDateTime
                    t = QDateTime.fromMSecsSinceEpoch(st.last_ok_epoch_ms).toString("HH:mm:ss")
                    status.setText(f"{st.message} {t}" if st.message else f"Updated {t}")
                else:
                    status.setText(st.message or "Ready")

            for name in ("refresh_btn", "run_speedtest_btn"):
                b = getattr(self, name, None)
                if b is not None:
                    try:
                        b.setEnabled(True)
                    except Exception:
                        pass
        except Exception:
            # Never let UI state updates crash refresh
            pass


    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
        super().closeEvent(event)


    def _go_updates(self):
        # MainWindow owns the QStackedWidget + _go("updates")
        w = self.window()
        if hasattr(w, "_go"):
            w._go("updates")
