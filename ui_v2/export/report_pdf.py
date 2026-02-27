from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QDateTime, Qt, QRectF, QPoint, QMarginsF
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QPainter,
    QPdfWriter,
    QPixmap,
    QPageSize,
    QPageLayout,
    QImage,
    QPalette,
    QRegion,
)
from PySide6.QtWidgets import QApplication, QWidget

from ui_v2.services.updates import (
    get_update_count,
    reboot_required,
    list_kept_back,
    list_holds,
    list_upgradable,
)


@dataclass
class Section:
    title: str
    rows: list[tuple[str, str]]


def export_current_view_pdf(widget: QWidget, path: str, scale: float = 2.0) -> None:
    QApplication.processEvents()
    pixmap = _capture_widget(widget, scale=scale, prefer_screen=True)

    writer, painter, page = _start_pdf(path)
    try:
        y = _draw_header(
            painter,
            page,
            "Current View Export",
            timestamp=_now_ts(),
            app_version=_app_version_hint(),
        )
        y = _draw_pixmap_full_width(painter, page, pixmap, y)
        _draw_footer(painter, page, timestamp=_now_ts(), page_number=1)
    finally:
        painter.end()


def export_system_report_pdf(
    path: str,
    screenshots: dict[str, QPixmap],
    sections: dict[str, bool],
    scale: float = 2.0,
) -> None:
    QApplication.processEvents()
    dashboard_pixmap = screenshots.get("dashboard")

    writer, painter, page = _start_pdf(path)
    try:
        timestamp = _now_ts()
        app_version = _app_version_hint()

        page_number = 1
        y = _draw_header(
            painter,
            page,
            "System Report",
            timestamp=timestamp,
            app_version=app_version,
        )

        if dashboard_pixmap is not None:
            y = _draw_dashboard_block(
                painter,
                page,
                dashboard_pixmap,
                y,
                _updates_summary_rows(),
            )

        _draw_footer(painter, page, timestamp=timestamp, page_number=page_number)

        sections_to_render = _build_sections(sections)
        if sections_to_render:
            page_number += 1
            page.new_page()
            y = page.content.top()

            for section in sections_to_render:
                pix = screenshots.get(_section_key(section.title))
                y, page_number = _draw_section_block(
                    painter,
                    page,
                    section,
                    y,
                    timestamp,
                    page_number,
                    pix,
                )

            _draw_footer(painter, page, timestamp=timestamp, page_number=page_number)
    finally:
        painter.end()


def _build_sections(selections: dict[str, bool]) -> list[Section]:
    out: list[Section] = []

    if selections.get("updates"):
        out.append(Section(title="Updates Summary", rows=_updates_summary_rows()))

    if selections.get("power"):
        out.append(_placeholder_section("Power Summary"))

    if selections.get("storage"):
        out.append(_placeholder_section("Storage Summary"))

    if selections.get("network"):
        out.append(_placeholder_section("Network Summary"))

    if selections.get("devtools"):
        out.append(_placeholder_section("Dev/Tools Logs"))

    return out


def _placeholder_section(title: str) -> Section:
    return Section(title=title, rows=[("Status", "Not implemented yet")])


def _start_pdf(path: str) -> tuple[QPdfWriter, QPainter, _PageSpec]:
    writer = QPdfWriter(path)
    layout = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Landscape,
        QMarginsF(15, 15, 15, 15),
        QPageLayout.Millimeter,
    )
    writer.setPageLayout(layout)
    writer.setResolution(300)

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)

    page = _PageSpec(writer)
    return writer, painter, page


class _PageSpec:
    def __init__(self, writer: QPdfWriter) -> None:
        self.writer = writer
        self.margin = 0
        self.update_rects()

    def update_rects(self) -> None:
        rect = self.writer.pageLayout().paintRectPixels(self.writer.resolution())
        self.rect = QRectF(rect)
        self.content = QRectF(
            self.rect.left() + self.margin,
            self.rect.top() + self.margin,
            self.rect.width() - self.margin * 2,
            self.rect.height() - self.margin * 2,
        )

    def new_page(self) -> None:
        self.writer.newPage()
        self.update_rects()


def _draw_header(
    painter: QPainter,
    page: _PageSpec,
    title: str,
    timestamp: str,
    app_version: str | None,
) -> float:
    y = page.content.top()

    title_font = QFont("Segoe UI", 22, QFont.Bold)
    painter.setFont(title_font)
    y += _draw_text_line(painter, page, title, y)

    meta_font = QFont("Segoe UI", 10)
    painter.setFont(meta_font)
    meta_parts = [f"Generated: {timestamp}"]
    if app_version:
        meta_parts.append(f"Version: {app_version}")
    y += _draw_text_line(painter, page, " | ".join(meta_parts), y)

    y += 12
    return y


def _draw_footer(painter: QPainter, page: _PageSpec, timestamp: str, page_number: int) -> None:
    footer_font = QFont("Segoe UI", 8)
    painter.setFont(footer_font)
    text = f"Laptop Health  |  {timestamp}  |  Page {page_number}"
    metrics = QFontMetrics(footer_font)
    h = metrics.height()
    x = page.content.left()
    y = page.rect.bottom() - 8
    painter.setPen(Qt.gray)
    painter.drawText(x, y, text)
    painter.setPen(Qt.black)


def _draw_section_block(
    painter: QPainter,
    page: _PageSpec,
    section: Section,
    y: float,
    timestamp: str,
    page_number: int,
    screenshot: QPixmap | None,
) -> tuple[float, int]:
    heading_font = QFont("Segoe UI", 12, QFont.Bold)
    body_font = QFont("Segoe UI", 10)
    value_font = QFont("JetBrains Mono", 10)
    heading_metrics = QFontMetrics(heading_font)
    body_metrics = QFontMetrics(body_font)

    section_gap = 30
    header_h = heading_metrics.height()
    block_needed = section_gap + header_h + 10
    if screenshot is not None and not screenshot.isNull():
        block_needed += page.content.height() * 0.40 + 14
    row_h = body_metrics.height() + 8
    block_needed += row_h * max(1, len(section.rows)) + 12

    y, page_number = _ensure_space(page, painter, y, block_needed, timestamp, page_number)

    y += section_gap
    painter.setFont(heading_font)
    painter.setPen(Qt.white)
    painter.drawText(page.content.left(), y + heading_metrics.ascent(), section.title)
    y += header_h + 6

    painter.setPen(Qt.gray)
    painter.drawLine(page.content.left(), y, page.content.right(), y)
    y += 12

    if screenshot is not None and not screenshot.isNull():
        logical_w, logical_h = _pixmap_logical_size(screenshot)
        max_width = page.content.width()
        max_height = page.content.height() * 0.40
        scale = min(max_width / logical_w, max_height / logical_h)
        target_width = logical_w * scale
        target_height = logical_h * scale
        target = QRectF(page.content.left(), y, target_width, target_height)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(target, screenshot, QRectF(0, 0, screenshot.width(), screenshot.height()))
        y = target.bottom() + 16

    indent = 40
    y_cursor = y
    key_col_w = page.content.width() * 0.55

    for key, value in section.rows:
        painter.setFont(body_font)
        painter.setPen(Qt.white)
        painter.drawText(page.content.left() + indent, y_cursor + body_metrics.ascent(), key)
        painter.setFont(value_font)
        painter.setPen(Qt.lightGray)
        painter.drawText(page.content.left() + indent + key_col_w, y_cursor + body_metrics.ascent(), value)
        y_cursor += row_h

    return y_cursor + 20, page_number


def _draw_dashboard_block(
    painter: QPainter,
    page: _PageSpec,
    pixmap: QPixmap,
    y: float,
    summary_rows: list[tuple[str, str]],
) -> float:
    if pixmap.isNull():
        return y
    logical_w, logical_h = _pixmap_logical_size(pixmap)
    max_width = page.content.width()
    max_height = page.content.height() * 0.60
    scale = min(max_width / logical_w, max_height / logical_h)
    target_width = logical_w * scale
    target_height = logical_h * scale

    target = QRectF(page.content.left(), y, target_width, target_height)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(target, pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))
    y += target_height + 14

    y = _draw_summary_card(painter, page, y, summary_rows)
    return y


def _draw_pixmap_full_width(
    painter: QPainter,
    page: _PageSpec,
    pixmap: QPixmap,
    y: float,
) -> float:
    if pixmap.isNull():
        return y
    logical_w, logical_h = _pixmap_logical_size(pixmap)
    max_width = page.content.width()
    max_height = page.content.height()
    scale = min(max_width / logical_w, max_height / logical_h)
    target_width = logical_w * scale
    target_height = logical_h * scale
    target = QRectF(page.content.left(), y, target_width, target_height)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(target, pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))
    return y + target_height + 10


def _ensure_space(
    page: _PageSpec,
    painter: QPainter,
    y: float,
    needed: float,
    timestamp: str,
    page_number: int,
) -> tuple[float, int]:
    if y + needed <= page.content.bottom() - 16:
        return y, page_number
    _draw_footer(painter, page, timestamp=timestamp, page_number=page_number)
    page_number += 1
    page.new_page()
    return page.content.top(), page_number


def _draw_text_line(painter: QPainter, page: _PageSpec, text: str, y: float) -> float:
    metrics = painter.fontMetrics()
    painter.drawText(page.content.left(), y + metrics.ascent(), text)
    return metrics.height()

def _draw_card_bg(painter: QPainter, rect: QRectF) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.transparent)
    painter.setPen(Qt.gray)
    painter.setBrush(Qt.transparent)
    painter.drawRoundedRect(rect, 10, 10)


def _draw_summary_card(
    painter: QPainter,
    page: _PageSpec,
    y: float,
    rows: list[tuple[str, str]],
) -> float:
    heading_font = QFont("Segoe UI", 12, QFont.Bold)
    body_font = QFont("Segoe UI", 10)
    value_font = QFont("JetBrains Mono", 10)
    heading_metrics = QFontMetrics(heading_font)
    body_metrics = QFontMetrics(body_font)

    row_h = 20
    painter.setFont(heading_font)
    painter.setPen(Qt.white)
    painter.drawText(page.content.left(), y + heading_metrics.ascent(), "Key Summary")
    y += heading_metrics.height() + 2

    painter.setPen(Qt.gray)
    painter.drawLine(page.content.left(), y, page.content.right(), y)
    y += 8

    y_cursor = y
    indent = 40
    key_col_w = page.content.width() * 0.55

    for key, value in rows:
        painter.setFont(body_font)
        painter.setPen(Qt.white)
        painter.drawText(page.content.left() + indent, y_cursor + body_metrics.ascent(), key)
        painter.setFont(value_font)
        painter.setPen(Qt.lightGray)
        painter.drawText(page.content.left() + indent + key_col_w, y_cursor + body_metrics.ascent(), value)
        y_cursor += row_h

    return y_cursor + 20

def _capture_widget(widget: QWidget, scale: float = 2.0, prefer_screen: bool = False) -> QPixmap:
    widget.ensurePolished()
    widget.update()
    widget.repaint()
    QApplication.processEvents()
    QApplication.processEvents()

    bg = widget.palette().color(QPalette.Window)
    scale = max(1.0, float(scale))

    if prefer_screen and _session_type() == "x11":
        screen_pix = _capture_widget_screen(widget)
        if screen_pix is not None and not screen_pix.isNull():
            return _rescale_pixmap(screen_pix, scale)

    # 1) Prefer QWidget.grab (often best for styled widgets)
    pixmap = widget.grab()
    if not pixmap.isNull() and not _looks_blank(pixmap, bg):
        return _rescale_pixmap(pixmap, scale)

    # 2) Render to high-res image
    size = widget.size()
    if size.isEmpty():
        size = widget.sizeHint()
    if not size.isEmpty():
        image = QImage(
            int(size.width() * scale),
            int(size.height() * scale),
            QImage.Format_ARGB32,
        )
        image.setDevicePixelRatio(scale)
        image.fill(bg)
        p = QPainter(image)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            widget.render(
                p,
                QPoint(0, 0),
                QRegion(widget.rect()),
                QWidget.RenderFlag.DrawWindowBackground | QWidget.RenderFlag.DrawChildren,
            )
        finally:
            p.end()
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull() and not _looks_blank(pixmap, bg):
            return pixmap

    if prefer_screen:
        screen_pix = _capture_widget_screen(widget)
        if screen_pix is not None and not screen_pix.isNull():
            return _rescale_pixmap(screen_pix, scale)

    return pixmap


def capture_widget_pixmap(widget: QWidget, scale: float = 2.0) -> QPixmap:
    return _capture_widget(widget, scale=scale, prefer_screen=True)


def _capture_widget_screen(widget: QWidget) -> QPixmap | None:
    win = widget.window()
    screen = QApplication.primaryScreen()
    if screen is None or win is None:
        return None
    full = screen.grabWindow(int(win.winId()))
    if full.isNull():
        return None
    top_left = widget.mapTo(win, QPoint(0, 0))
    rect = QRectF(top_left.x(), top_left.y(), widget.width(), widget.height()).toRect()
    return full.copy(rect)


def _looks_blank(pixmap: QPixmap, bg_color) -> bool:
    if pixmap.isNull():
        return True
    img = pixmap.toImage()
    w = img.width()
    h = img.height()
    if w == 0 or h == 0:
        return True
    samples = [
        (w // 4, h // 4),
        (w // 2, h // 4),
        (3 * w // 4, h // 4),
        (w // 4, h // 2),
        (w // 2, h // 2),
        (3 * w // 4, h // 2),
        (w // 4, 3 * h // 4),
        (w // 2, 3 * h // 4),
        (3 * w // 4, 3 * h // 4),
    ]
    bg = bg_color
    for x, y in samples:
        c = img.pixelColor(x, y)
        if c.alpha() > 20:
            if (
                abs(c.red() - bg.red()) > 6
                or abs(c.green() - bg.green()) > 6
                or abs(c.blue() - bg.blue()) > 6
            ):
                return False
    return True


def _pixmap_logical_size(pixmap: QPixmap) -> tuple[float, float]:
    dpr = max(1.0, float(pixmap.devicePixelRatioF()))
    return pixmap.width() / dpr, pixmap.height() / dpr


def _rescale_pixmap(pixmap: QPixmap, scale: float) -> QPixmap:
    if scale <= 1.01:
        return pixmap
    w, h = _pixmap_logical_size(pixmap)
    target = pixmap.scaled(
        int(w * scale),
        int(h * scale),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    return target


def _session_type() -> str:
    from os import environ
    return (environ.get("XDG_SESSION_TYPE") or "").lower()


def _now_ts() -> str:
    return QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")


def _fmt_count(value: int | None) -> str:
    if value is None:
        return "Unknown"
    return str(int(value))


def _app_version_hint() -> str | None:
    return None


def _updates_summary_rows() -> list[tuple[str, str]]:
    total, security = get_update_count()
    kept = len(list_kept_back())
    held = len(list_holds())
    reboot = reboot_required()
    upgradable = list_upgradable()
    return [
        ("Total updates", _fmt_count(total)),
        ("Security updates", _fmt_count(security)),
        ("Reboot required", "Yes" if reboot else "No"),
        ("Upgradable packages", str(len(upgradable))),
        ("Kept back", str(kept)),
        ("Held packages", str(held)),
    ]


def _section_key(title: str) -> str:
    mapping = {
        "Updates Summary": "updates",
        "Power Summary": "power",
        "Storage Summary": "storage",
        "Network Summary": "network",
        "Dev/Tools Logs": "devtools",
    }
    return mapping.get(title, "")
