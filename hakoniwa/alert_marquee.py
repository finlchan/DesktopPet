"""警報公佈走馬燈 — horizontal scrolling alerts under the status strip.

Pure Qt (QPainter + QTimer). Theme matches in-map HUD (dark translucent,
cyan/teal border, light text).
"""

from __future__ import annotations

from typing import List, Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

# Sample disaster / event stubs for demos when no live alerts are queued.
SAMPLE_ALERTS: tuple[str, ...] = (
    "【警報】海域風浪偏高 — 港灣／防波堤注意防護",
    "【公佈】怪獸影蹤通報 — 請確認防衛設施與飛彈基地",
    "【警報】地震餘震觀測中 — 山區採掘場暫緩作業",
    "【公佈】觀光季開始 — 空港／酒店／遊樂園人流上升",
)

_BG = QColor(16, 36, 40, 200)
_BORDER = QColor(90, 200, 190, 200)
_FG = QColor(230, 248, 200, 245)
_ACCENT = QColor(220, 160, 70, 230)

MARQUEE_H = 22
_SCROLL_PX = 1
_TICK_MS = 30
_GAP = "　　◆　　"


class AlertMarquee(QWidget):
    """Single-line horizontal marquee for alert / announcement text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hakoniwaAlertMarquee")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(MARQUEE_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("警報公佈")

        self._alerts: List[str] = []
        self._offset = 0.0
        self._loop_w = 1.0

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    def alerts(self) -> List[str]:
        return list(self._alerts)

    def has_alerts(self) -> bool:
        return bool(self._alerts)

    def set_alerts(self, texts: Sequence[str]) -> None:
        cleaned = [t.strip() for t in texts if t and str(t).strip()]
        self._alerts = cleaned
        self._offset = 0.0
        self._recompute_loop()
        self._sync_timer()
        self.update()

    def clear_alerts(self) -> None:
        self.set_alerts([])

    def set_sample_alerts(self) -> None:
        """Load disaster／event stub lines for demos / screenshots."""
        self.set_alerts(SAMPLE_ALERTS)

    def _joined(self) -> str:
        if not self._alerts:
            return ""
        return _GAP.join(self._alerts) + _GAP

    def _recompute_loop(self) -> None:
        text = self._joined()
        if not text:
            self._loop_w = 1.0
            return
        fm = self.fontMetrics()
        self._loop_w = max(float(fm.horizontalAdvance(text)), 1.0)

    def _sync_timer(self) -> None:
        if self._alerts and not self.isHidden() and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        if not self._alerts:
            return
        self._offset = (self._offset + _SCROLL_PX) % self._loop_w
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._recompute_loop()
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute_loop()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(QPen(_BORDER, 1.2))
        p.setBrush(_BG)
        p.drawRoundedRect(r, 3.0, 3.0)

        text = self._joined()
        if not text:
            p.end()
            return

        font = QFont(self.font())
        font.setPointSize(max(9, font.pointSize()))
        font.setBold(True)
        p.setFont(font)
        p.setPen(_FG)

        # Accent tag at left edge
        tag = "警報"
        fm = p.fontMetrics()
        tag_w = fm.horizontalAdvance(tag) + 10
        p.fillRect(1, 1, tag_w, self.height() - 2, QColor(40, 28, 12, 210))
        p.setPen(_ACCENT)
        p.drawText(4, 0, tag_w - 4, self.height(), int(Qt.AlignmentFlag.AlignVCenter), tag)

        # Clip scrolling region to the right of the tag.
        p.setPen(_FG)
        p.setClipRect(tag_w + 2, 0, self.width() - tag_w - 3, self.height())
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        x0 = tag_w + 6 - int(self._offset)
        # Draw two copies for seamless loop.
        p.drawText(x0, y, text)
        p.drawText(x0 + int(self._loop_w), y, text)
        p.end()
