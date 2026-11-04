"""Odometer-style digit roll widgets for the hakoniwa status HUD.

Each digit sits in its own small dark cell (「累計 12,527 人」 vibe); labels
and commas stay outside cells. The status strip itself is frameless over the
map. Digits scroll upward with a short OutBack bounce. Persistence helpers
remember the last-seen turn snapshot so login/open only rolls when the turn
advances.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    Property,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

PathLike = Union[str, Path]

# Labels / commas: bold white over the map. Digit cells: small dark tiles.
STATUS_FG = QColor("#ffffff")
DIGIT_FG = QColor("#ffffff")
DIGIT_CELL_BG = QColor(12, 18, 16, 230)  # dark cell fill (not a bar frame)
DIGIT_MS = 520
DIGIT_RADIUS = 2.0


def format_grouped(n: int) -> str:
    """Integer with thousands commas (e.g. 12480 → '12,480')."""
    return f"{int(n):,}"


class DigitReel(QWidget):
    """One digit in a small dark cell; reel scrolls upward with overshoot."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._digit = 0
        self._offset = 0.0  # fractional reel position (digit units)
        self._anim: Optional[QPropertyAnimation] = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        font = QFont(self.font())
        font.setBold(True)
        self.setFont(font)
        fm = QFontMetrics(self.font())
        # Compact cell like counter tiles — tight around the glyph.
        self._cell_w = max(fm.horizontalAdvance("0") + 6, 14)
        self._cell_h = max(fm.height() + 4, 18)
        self.setFixedSize(self._cell_w, self._cell_h)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, get_offset, set_offset)

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize

        return QSize(self._cell_w, self._cell_h)

    def current_digit(self) -> int:
        return int(self._digit) % 10

    def set_digit(self, digit: int, *, animate: bool = False) -> None:
        digit = int(digit) % 10
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        if not animate or digit == self.current_digit():
            self._digit = digit
            self._offset = float(digit)
            self.update()
            return
        start = self._offset
        # Always roll upward (increasing offset); wrap past 9 → 10+…
        end = float(digit)
        if end <= start:
            end += 10.0
        # Slight overshoot past the target, then settle (OutBack handles bounce).
        self._digit = digit
        anim = QPropertyAnimation(self, b"offset", self)
        anim.setDuration(DIGIT_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.finished.connect(self._on_anim_finished)
        self._anim = anim
        anim.start()

    def _on_anim_finished(self) -> None:
        self._offset = float(self._digit % 10)
        self._anim = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        h = float(self.height())
        w = float(self.width())
        # Dark cell tile (individual digit box — not a bar frame).
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), DIGIT_RADIUS, DIGIT_RADIUS)
        p.fillPath(path, DIGIT_CELL_BG)
        p.setClipPath(path)
        p.setFont(self.font())
        p.setPen(DIGIT_FG)
        base = self._offset
        for k in range(int(base) - 1, int(base) + 3):
            d = k % 10
            y = (k - base) * h
            if y + h < -h or y > h * 2:
                continue
            p.drawText(
                0,
                int(round(y)),
                int(w),
                int(h),
                int(Qt.AlignmentFlag.AlignCenter),
                str(d),
            )
        p.end()


class OdometerNumber(QWidget):
    """Comma-grouped digit reels; commas sit *outside* digit cells."""

    def __init__(self, parent: Optional[QWidget] = None, *, min_digits: int = 1):
        super().__init__(parent)
        self._min_digits = max(1, int(min_digits))
        self._value = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        # Tight gap between digit cells; commas get their own spacing.
        self._layout.setSpacing(2)
        self._reels: list[DigitReel] = []
        self._seps: list[QLabel] = []
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._rebuild(0, animate=False)

    def value(self) -> int:
        return self._value

    def set_value(self, value: int, *, animate: bool = False) -> None:
        value = max(0, int(value))
        self._value = value
        grouped = format_grouped(value)
        digits = grouped.replace(",", "")
        if len(digits) == len(self._reels) and grouped.count(",") == len(self._seps):
            # Same digit count / grouping — roll each reel in place.
            for reel, ch in zip(self._reels, digits):
                reel.set_digit(int(ch), animate=animate)
            return
        self._rebuild(value, animate=animate)

    def _rebuild(self, value: int, *, animate: bool) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._reels.clear()
        self._seps.clear()
        text = format_grouped(value)
        raw = text.replace(",", "")
        if len(raw) < self._min_digits:
            raw = raw.zfill(self._min_digits)
            text = format_grouped(int(raw))
        # Build from grouped text so commas land between digit cells.
        for ch in text:
            if ch == ",":
                # Comma lives outside digit cells (no dark tile).
                sep = QLabel(",", self)
                sep.setObjectName("hakoniwaOdoSep")
                font = QFont(sep.font())
                font.setBold(True)
                sep.setFont(font)
                sep.setStyleSheet(
                    "color: #ffffff; background: transparent; border: none;"
                    "padding: 0 1px; font-weight: bold;"
                )
                self._layout.addWidget(sep)
                self._seps.append(sep)
            else:
                reel = DigitReel(self)
                reel.set_digit(int(ch), animate=False)
                self._layout.addWidget(reel)
                self._reels.append(reel)
        if animate and self._reels:
            # Nudge top reel so open-roll still feels like motion when width changed.
            top = self._reels[-1]
            start_digit = (top.current_digit() - 1) % 10
            top.set_digit(start_digit, animate=False)
            top.set_digit(int(text.replace(",", "")[-1]), animate=True)

    def sizeHint(self):  # noqa: N802
        return self._layout.sizeHint()


def status_seen_path(save_path: PathLike) -> Path:
    """JSON beside the island save remembering last-seen status snapshot."""
    return Path(save_path).parent / "hakoniwa_status_seen.json"


def load_status_seen(path: PathLike) -> Optional[Dict[str, int]]:
    target = Path(path)
    if not target.exists():
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    out: Dict[str, int] = {}
    for key in ("turn", "funds", "food", "population", "land_count", "score"):
        if key not in data:
            return None
        try:
            out[key] = int(data[key])
        except (TypeError, ValueError):
            return None
    if "bank_deposit" in data:
        try:
            out["bank_deposit"] = int(data["bank_deposit"])
        except (TypeError, ValueError):
            out["bank_deposit"] = 0
    else:
        out["bank_deposit"] = 0
    return out


def save_status_seen(path: PathLike, snap: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "turn": int(snap["turn"]),
        "funds": int(snap["funds"]),
        "food": int(snap["food"]),
        "population": int(snap["population"]),
        "land_count": int(snap["land_count"]),
        "score": int(snap["score"]),
        "bank_deposit": int(snap.get("bank_deposit", 0) or 0),
    }
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return target


def snapshot_from_state(state: Any) -> Dict[str, int]:
    """Pull status fields from an IslandState (duck-typed)."""
    return {
        "turn": int(state.turn),
        "funds": int(state.funds),
        "food": int(state.food),
        "population": int(state.population),
        "land_count": int(state.land_count()),
        "score": int(state.island_score()),
        "bank_deposit": int(getattr(state, "bank_deposit", 0) or 0),
    }


class HakoniwaStatusBar(QWidget):
    """Frameless top strip: 狀態 | 資金[cells] | … (labels outside; bold white).

    ``text()`` returns a flat string for smoke tests / layout width.
    ``setText`` switches to plain tourism/legacy mode.
    """

    FIELD_ORDER = (
        ("funds", "資金"),
        ("food", "糧食"),
        ("population", "人口"),
        ("turn", "回合"),
        ("land_count", "格數"),
        ("score", "分數"),
    )

    _LABEL_STYLE = (
        "color: #ffffff; background: transparent; border: none; font-weight: bold;"
    )

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("hakoniwaHudStatus")
        # Fully transparent strip — only digit cells paint a dark fill.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        font = QFont(self.font())
        font.setBold(True)
        self.setFont(font)

        self._plain = False
        self._plain_text = ""
        self._suffix = ""  # e.g. monster bit
        self._values: Dict[str, int] = {
            "funds": 0,
            "food": 0,
            "population": 0,
            "turn": 0,
            "land_count": 0,
            "score": 0,
            "bank_deposit": 0,
        }

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(4, 2, 4, 2)
        self._row.setSpacing(6)

        self._plain_label = QLabel(self)
        self._plain_label.setObjectName("hakoniwaHudStatusPlain")
        self._plain_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._plain_label.setWordWrap(False)
        self._plain_label.hide()

        self._structured = QWidget(self)
        self._structured.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._structured.setAutoFillBackground(False)
        self._struct_lay = QHBoxLayout(self._structured)
        self._struct_lay.setContentsMargins(0, 0, 0, 0)
        self._struct_lay.setSpacing(6)

        self._status_label = self._make_caption("狀態")
        self._struct_lay.addWidget(self._status_label)
        self._odometers: Dict[str, OdometerNumber] = {}
        self._bank_label = QLabel("", self._structured)
        self._bank_label.setStyleSheet(self._LABEL_STYLE)
        self._suffix_label = QLabel("", self._structured)
        self._suffix_label.setStyleSheet(self._LABEL_STYLE)

        for key, title in self.FIELD_ORDER:
            # Always "| label odo" after 狀態 (and between fields).
            self._struct_lay.addWidget(self._make_sep())
            self._struct_lay.addWidget(self._make_caption(title))
            odo = OdometerNumber(self._structured, min_digits=1)
            self._odometers[key] = odo
            self._struct_lay.addWidget(odo)
            if key == "funds":
                self._struct_lay.addWidget(self._bank_label)
        self._struct_lay.addWidget(self._suffix_label)

        self._row.addWidget(self._structured)
        self._row.addWidget(self._plain_label)

        self.setWordWrap = self._set_word_wrap_noop  # type: ignore[method-assign]
        self._word_wrap = False

    def _set_word_wrap_noop(self, wrap: bool) -> None:
        self._word_wrap = bool(wrap)
        self._plain_label.setWordWrap(self._word_wrap)

    def wordWrap(self) -> bool:  # noqa: N802
        return self._word_wrap

    def _make_caption(self, text: str) -> QLabel:
        lab = QLabel(text, self._structured)
        lab.setStyleSheet(self._LABEL_STYLE)
        return lab

    def _make_sep(self) -> QLabel:
        lab = QLabel("|", self._structured)
        lab.setStyleSheet(self._LABEL_STYLE)
        return lab

    def setAlignment(self, alignment) -> None:  # noqa: N802
        self._plain_label.setAlignment(alignment)

    def setTextFormat(self, fmt) -> None:  # noqa: N802
        self._plain_label.setTextFormat(fmt)

    def setText(self, text: str) -> None:  # noqa: N802
        """Legacy / tourism plain string mode."""
        self._plain = True
        self._plain_text = text or ""
        self._structured.hide()
        self._plain_label.setText(self._plain_text)
        self._plain_label.show()
        self.updateGeometry()

    def text(self) -> str:
        if self._plain:
            return self._plain_text
        return self._compose_text(self._values, self._suffix)

    @staticmethod
    def _compose_text(vals: Mapping[str, int], suffix: str = "") -> str:
        funds_bit = f"資金 {vals.get('funds', 0)}"
        bank = int(vals.get("bank_deposit", 0) or 0)
        if bank > 0:
            funds_bit += f"（存{bank}）"
        body = (
            f"狀態 | {funds_bit} | 糧食 {vals.get('food', 0)} | "
            f"人口 {vals.get('population', 0)} | 回合 {vals.get('turn', 0)} | "
            f"格數 {vals.get('land_count', 0)} | 分數 {vals.get('score', 0)}"
        )
        return body + (suffix or "")

    def set_values(
        self,
        values: Mapping[str, Any],
        *,
        animate: bool = False,
        suffix: str = "",
    ) -> None:
        """Structured odometer mode (main island play)."""
        self._plain = False
        self._plain_label.hide()
        self._structured.show()
        snap = {
            "funds": int(values.get("funds", 0)),
            "food": int(values.get("food", 0)),
            "population": int(values.get("population", 0)),
            "turn": int(values.get("turn", 0)),
            "land_count": int(values.get("land_count", 0)),
            "score": int(values.get("score", 0)),
            "bank_deposit": int(values.get("bank_deposit", 0) or 0),
        }
        self._values = snap
        self._suffix = suffix or ""
        for key, _title in self.FIELD_ORDER:
            self._odometers[key].set_value(snap[key], animate=animate)
        bank = snap["bank_deposit"]
        self._bank_label.setText(f"（存{bank}）" if bank > 0 else "")
        self._bank_label.setVisible(bank > 0)
        self._suffix_label.setText(self._suffix)
        self._suffix_label.setVisible(bool(self._suffix))
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        if self._plain:
            return self._plain_label.sizeHint()
        return self._structured.sizeHint()
