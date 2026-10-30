"""桌宠形态：极简几何小生物，是数据条的互斥视图。

同一份数据、两个视图：
- 单击它 → 切回数据条
- 拖到任意位置，右键更多
- 到点提醒 → 抖动 + 头顶气泡
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, QRect
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget, QMenu

PET_SIZE = 96          # 窗口边长
FRAME_MS = 33          # 30fps
BASE_CHECK_MS = 2000   # 基础状态巡检

C_BODY = "#3b6ef6"
C_ALERT = "#ef4444"
C_DONE = "#22c55e"


# ------------------------------------------------------------------ 气泡
class PetBubble(QWidget):
    """桌宠头顶的小气泡，显示到期任务摘要。"""

    MAX_W = 240

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._text = ""
        self.setFixedWidth(self.MAX_W)

    def show_text(self, text: str, anchor: QPoint) -> None:
        self._text = text
        self.setFixedHeight(self._measure_height(text))
        x = anchor.x() - self.MAX_W // 2
        y = anchor.y() - self.height()
        scr = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        x = max(g.left() + 4, min(x, g.right() - self.MAX_W - 4))
        if y < g.top() + 4:
            # 上方放不下就改到桌宠下方
            y = anchor.y() + PET_SIZE - 8
        self.move(int(x), int(y))
        self.show()
        self.raise_()

    def _measure_height(self, text: str) -> int:
        fm = self.fontMetrics()
        rect = fm.boundingRect(QRect(0, 0, self.MAX_W - 26, 400),
                               int(Qt.TextWordWrap), text)
        return max(36, rect.height() + 24)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setBrush(QColor(26, 28, 36, 242))
        p.setPen(QPen(QColor(96, 106, 136, 210), 1))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QColor("#e8eaf0"))
        p.drawText(QRectF(13, 12, self.width() - 26, self.height() - 24),
                   int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter),
                   self._text)


# ------------------------------------------------------------------ 桌宠
class PetWindow(QWidget):
    """极简几何桌宠。状态：idle / new_task / due_soon / all_done。"""

    def __init__(self, db, st, on_open_bar=None, on_open_settings=None) -> None:
        super().__init__(None)
        self.db = db
        self.st = st
        self.on_open_bar = on_open_bar or (lambda: None)
        self.on_open_settings = on_open_settings or (lambda: None)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(PET_SIZE, PET_SIZE)
        self.setToolTip("CaptureDock · 单击打开任务列表")

        self._t = 0.0
        self._state = "idle"
        self._start = 0.0
        self._total = 0.0

        self._last_open = -1
        self._seen_due: set[str] = set()
        self._locked = bool(st["petLocked"])

        self._drag_from: QPoint | None = None
        self._drag_moved = False

        self.bubble = PetBubble()

        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._base_timer = QTimer(self)
        self._base_timer.setInterval(BASE_CHECK_MS)
        self._base_timer.timeout.connect(self._check_base)
        self._base_timer.start()

        self._pos_timer = QTimer(self)
        self._pos_timer.setSingleShot(True)
        self._pos_timer.setInterval(600)
        self._pos_timer.timeout.connect(self.save_pos)

        self._restore_pos()

    # ---------- 位置 ----------
    def _default_pos(self) -> QPoint:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(screen.right() - PET_SIZE - 40,
                      screen.bottom() - PET_SIZE - 60)

    def _restore_pos(self) -> None:
        pos = self.st["petPos"]
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if isinstance(pos, list) and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
        else:
            p = self._default_pos()
            x, y = p.x(), p.y()
        x = max(screen.left(), min(x, screen.right() - PET_SIZE))
        y = max(screen.top(), min(y, screen.bottom() - PET_SIZE))
        self.move(x, y)

    def save_pos(self) -> None:
        self.st["petPos"] = [self.x(), self.y()]

    def moveEvent(self, e):
        self._pos_timer.start()
        if self.bubble.isVisible() and self._bubble_text:
            self.bubble.show_text(
                self._bubble_text,
                self.mapToGlobal(QPoint(PET_SIZE // 2, 10)))
        super().moveEvent(e)

    # ---------- 状态机 ----------
    def play(self, state: str, hold: float) -> None:
        """播放一次限时动作，到时自动回到 idle。"""
        self._state = state
        self._start = time.monotonic()
        self._total = max(0.05, hold)

    def _phase(self) -> float:
        if self._total <= 0:
            return 1.0
        return max(0.0, min(1.0, (time.monotonic() - self._start) / self._total))

    def _tick(self) -> None:
        self._t += FRAME_MS / 1000.0
        if self._state != "idle" and time.monotonic() >= self._start + self._total:
            self._state = "idle"
            self._bubble_text = ""
            self.bubble.hide()
        self.update()

    def _check_base(self) -> None:
        """巡检：未完成清零 → all_done；15 分钟内到期 → due_soon + 气泡。"""
        if self._state != "idle":
            self._last_open = self.db.open_count()
            return

        open_n = self.db.open_count()
        if self._last_open > 0 and open_n == 0:
            self.play("all_done", 1.1)
            self._last_open = open_n
            return
        self._last_open = open_n

        now = int(time.time() * 1000)
        fresh = [t for t in self.db.due_tasks(now + 15 * 60_000)
                 if t["id"] not in self._seen_due]
        # 只在桌宠可见时提醒；隐藏时不消费事件，切回来仍会提示
        if fresh and self.isVisible():
            task = fresh[0]
            self._seen_due.add(task["id"])
            text = (task.get("task_text") or task.get("raw_text") or "")[:120]
            self._bubble_text = text
            self.play("due_soon", 8.0)
            QTimer.singleShot(30, lambda: self.bubble.show_text(
                text, self.mapToGlobal(QPoint(PET_SIZE // 2, 10))))

    _bubble_text = ""

    # ---------- 绘制 ----------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        t = self._t
        state = self._state
        cx, cy = self.width() / 2.0, self.height() / 2.0
        R = 30.0

        dy = math.sin(t * 1.6) * 1.8
        scale = 1.0
        shake = 0.0
        rot = 0.0
        eye_k = 1.0
        color = QColor(C_BODY)
        mouth = "smile"

        if state == "new_task":
            k = math.sin(self._phase() * math.pi)
            dy -= k * 16
            scale = 1.0 + k * 0.07
            eye_k = 1.0 + k * 0.22
            mouth = "open"
        elif state == "all_done":
            k = abs(math.sin(self._phase() * math.pi * 2))
            dy -= k * 11
            color = QColor(C_DONE)
            mouth = "big"
        elif state == "due_soon":
            shake = math.sin(t * 42) * 2.0
            color = QColor(C_ALERT)
            eye_k = 1.15
            mouth = "o"
        else:
            if (t % 4.2) < 0.16:
                eye_k = 0.10

        bx, by = cx + shake, cy + 2 + dy

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 32))
        p.drawEllipse(QRectF(bx - R * 0.70, cy + R * 0.64, R * 1.40, R * 0.30))

        p.save()
        p.translate(bx, by)
        p.rotate(rot)
        p.scale(scale, scale)

        grad = QLinearGradient(0, -R, 0, R)
        grad.setColorAt(0.0, color.lighter(124))
        grad.setColorAt(1.0, color.darker(120))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(-R, -R, R * 2, R * 2))

        p.setBrush(QColor(255, 255, 255, 46))
        p.drawEllipse(QRectF(-R * 0.62, -R * 0.80, R * 0.80, R * 0.50))

        # 眼睛：白眼球 + 圆形瞳孔
        eye_rx, eye_ry = 5.6, 6.4
        for ex in (-10.5, 10.5):
            if state == "all_done":
                # 开心眯眼 ^
                pen = QPen(QColor("#ffffff"), 2.6)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(ex - 5.4, -4.6, 10.8, 9.0), 10 * 16, 160 * 16)
                continue
            h = eye_ry * eye_k
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(ex - eye_rx, -5.0 - h, eye_rx * 2, h * 2))
            if eye_k > 0.4:
                pr = 2.9
                p.setBrush(QColor(22, 24, 32))
                p.drawEllipse(QRectF(ex - pr, -4.2 - pr, pr * 2, pr * 2))

        pen = QPen(QColor(255, 255, 255, 205), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if mouth == "smile":
            p.drawArc(QRectF(-7, 4, 14, 10), 200 * 16, 140 * 16)
        elif mouth == "open":
            p.drawEllipse(QRectF(-4.5, 5, 9, 9))
        elif mouth == "o":
            p.drawEllipse(QRectF(-3.2, 6, 6.4, 7))
        else:
            p.drawArc(QRectF(-8, 3, 16, 12), 190 * 16, 160 * 16)

        p.restore()

        if state == "due_soon":
            p.setPen(QPen(QColor(C_ALERT), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPoint(int(cx), 5), QPoint(int(cx), 14))
            p.setBrush(QColor(C_ALERT))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(cx - 1.8, 17, 3.6, 3.6))

    # ---------- 交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._locked:
            self._drag_from = e.globalPosition().toPoint() - self.pos()
            self._drag_moved = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and (e.buttons() & Qt.LeftButton):
            target = e.globalPosition().toPoint() - self._drag_from
            if (target - self.pos()).manhattanLength() > 3:
                self._drag_moved = True
            self.move(target)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag_from is not None:
            moved = self._drag_moved
            self._drag_from = None
            if not moved:
                self.on_open_bar()
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("打开任务列表", self.on_open_bar)
        m.addSeparator()
        act_lock = m.addAction("锁定位置")
        act_lock.setCheckable(True)
        act_lock.setChecked(self._locked)
        act_lock.toggled.connect(self.set_locked)
        m.addAction("回到屏幕右下角", self._reset_pos)
        m.addSeparator()
        m.addAction("设置…", self.on_open_settings)
        m.exec(e.globalPos())

    def set_locked(self, on: bool) -> None:
        self._locked = bool(on)
        self.st["petLocked"] = self._locked

    def _reset_pos(self) -> None:
        self.move(self._default_pos())
        self.save_pos()

    # ---------- 显示 ----------
    def show_pet(self) -> None:
        self._restore_pos()
        open_n = self.db.open_count()
        # 隐藏期间新增过任务 → 跳一下
        if self._snapshot_open is not None and open_n > self._snapshot_open:
            self.play("new_task", 0.9)
        self._snapshot_open = open_n
        self._last_open = open_n
        self.show()
        self.raise_()
        self._check_base()

    def hideEvent(self, e):
        self.save_pos()
        self._bubble_text = ""
        self.bubble.hide()
        super().hideEvent(e)

    _snapshot_open: int | None = None
