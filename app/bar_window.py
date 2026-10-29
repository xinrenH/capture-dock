"""数据条主窗口：透明、置顶、无边框悬浮表格。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QMenu,
    QMessageBox, QAbstractItemView, QDialog, QFormLayout, QCheckBox, QSlider,
    QTimeEdit, QDialogButtonBox, QFrame, QInputDialog, QSizePolicy, QFileDialog,
)
from PySide6.QtCore import QTime

from .config import (
    STATUS_LABEL, STATUS_COLOR, STATUS_NEXT, STATUS_DONE, DEFAULT_SOURCE,
)
from .style import build_qss

COL_STATUS, COL_TASK, COL_REMIND = range(3)
HEADERS = ["状态", "任务", "提醒"]

MIN_WIDTH, MIN_HEIGHT = 180, 90
DEFAULT_WIDTH, DEFAULT_HEIGHT = 780, 420
RESIZE_EDGE = 4      # 边缘热区厚度
RESIZE_CORNER = 12   # 角部热区边长

# ---- Win32 鼠标穿透 ----
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x0020
WS_EX_LAYERED = 0x00080000

_user32 = ctypes.windll.user32
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]


def set_click_through(hwnd: int, enabled: bool) -> bool:
    """直接改扩展窗口样式实现穿透。

    不用 setWindowFlag(Qt.WindowTransparentForInput)：那会重建原生窗口，
    导致用旧 hwnd 注册的全局热键失效、窗口位置跳变。
    """
    if not hwnd:
        return False
    try:
        ex = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex = (ex | WS_EX_LAYERED | WS_EX_TRANSPARENT) if enabled \
            else (ex & ~WS_EX_TRANSPARENT)
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 工具函数
def fmt_ms(ms: int | None) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M")


def fmt_remind(ms: int | None) -> str:
    if not ms:
        return "—"
    dt = datetime.fromtimestamp(ms / 1000)
    today = datetime.now().date()
    if dt.date() == today:
        return "今天 " + dt.strftime("%H:%M")
    if dt.date() == today + timedelta(days=1):
        return "明天 " + dt.strftime("%H:%M")
    return dt.strftime("%m-%d %H:%M")


def parse_remind(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    now = datetime.now()
    for fmt in ("%H:%M", "%H%M", "%m-%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt in ("%H:%M", "%H%M"):
            dt = dt.replace(year=now.year, month=now.month, day=now.day)
            if dt <= now:
                dt += timedelta(days=1)
        elif fmt == "%m-%d %H:%M":
            dt = dt.replace(year=now.year)
        return int(dt.timestamp() * 1000)
    return None


def make_icon(size: int = 32, color: str = "#3b6ef6") -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(3, 3, size - 6, size - 6, size * 0.26, size * 0.26)
    p.setPen(QPen(QColor("#ffffff"), max(2, size // 10)))
    p.drawLine(int(size * 0.5), int(size * 0.26), int(size * 0.5), int(size * 0.54))
    p.drawLine(int(size * 0.5), int(size * 0.54), int(size * 0.70), int(size * 0.66))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- 边缘缩放热区
class ResizeHandle(QWidget):
    """无边框窗口的边缘缩放热区，交给系统做 resize，拖动过程平滑。"""

    def __init__(self, host: "BarWindow", edges) -> None:
        super().__init__(host)
        self.host = host
        self.edges = edges
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            win = self.host.windowHandle()
            if win is not None and win.startSystemResize(self.edges):
                e.accept()
                return
        super().mousePressEvent(e)


# ---------------------------------------------------------------- 穿透恢复浮标
class PenBadge(QWidget):
    """穿透状态下仍然可点击的小浮标，点一下就恢复正常模式。"""

    def __init__(self, host: "BarWindow") -> None:
        super().__init__(None)
        self.host = host
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(104, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击取消穿透，恢复窗口交互")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("已穿透 · 点击恢复", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "background-color: rgba(59,110,246,240);"
            "color: #ffffff; border-radius: 13px;"
            'font-family: "Microsoft YaHei UI"; font-size: 12px;')
        lay.addWidget(self.label)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.host.set_ignore_mouse(False)
            e.accept()
            return
        super().mousePressEvent(e)

    def sync_position(self) -> None:
        g = self.host.geometry()
        self.move(g.x() + g.width() - self.width() - 16, g.y() + 7)


# ---------------------------------------------------------------- 任务气泡
class HoverBubble(QWidget):
    """鼠标悬停在被截断的任务上时弹出的气泡，显示完整内容。

    用独立顶层窗口实现，不走 Qt 自带 tooltip：样式统一、可控制延迟、
    穿透状态下收不到鼠标事件因此自然不弹。
    """

    MAX_CHARS = 600

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint |
                            Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.box = QFrame(self)
        self.box.setObjectName("bubbleBox")
        self.box.setStyleSheet(
            "QFrame#bubbleBox {"
            "  background-color: #22232b;"
            "  border: 1px solid rgba(255,255,255,60);"
            "  border-radius: 8px;"
            "}"
            "QLabel { color: #e9e9ef;"
            '  font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 12px;'
            "  background: transparent; }")
        bl = QVBoxLayout(self.box)
        bl.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel("", self.box)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(460)
        self.label.setTextFormat(Qt.PlainText)
        bl.addWidget(self.label)
        lay.addWidget(self.box)

    def show_text(self, text: str, global_pos) -> None:
        text = (text or "").strip()
        if not text:
            self.hide()
            return
        if len(text) > self.MAX_CHARS:
            text = text[:self.MAX_CHARS] + " …"
        self.label.setText(text)
        # 按最长一行定宽，超过上限才换行，短文本不会缩成细条
        fm = self.label.fontMetrics()
        widest = max((fm.horizontalAdvance(line) for line in text.splitlines()), default=0)
        self.label.setFixedWidth(max(120, min(460, widest + 6)))
        self.adjustSize()
        w, h = self.width(), self.height()
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = global_pos.x() + 14
        y = global_pos.y() + 18
        if x + w > area.right():
            x = max(area.left(), area.right() - w - 4)
        if y + h > area.bottom():
            y = max(area.top(), global_pos.y() - h - 10)
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_now(self) -> None:
        self.hide()


# ---------------------------------------------------------------- 顶栏（可拖动）
class TopBar(QWidget):
    def __init__(self, host: "BarWindow") -> None:
        super().__init__(host)
        self.host = host
        self.setObjectName("topbar")
        self.setFixedHeight(40)
        self._drag = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 4)
        lay.setSpacing(4)

        # 计数不再占版面，只用于托盘提示与提醒闪烁
        self.counter = QLabel("未完成 0", self)
        self.counter.setObjectName("counter")
        self.counter.hide()

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索任务…")
        self.search.setMinimumWidth(80)
        self.search.setFixedHeight(26)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self.search, 1)

        def small(text: str, tip: str, checkable: bool = False) -> QPushButton:
            b = QPushButton(text, self)
            b.setObjectName("ghost")
            b.setCheckable(checkable)
            b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.btn_watch = small("贴", "剪贴板监听：开启后复制文本仅提示，不自动入库", True)
        self.btn_pen = small("透", "鼠标穿透：开启后点击直达下层窗口（Ctrl+Alt+P 可切回）", True)
        self.btn_lock = small("锁", "锁定位置，禁止拖动", True)
        self.btn_set = small("设", "设置")
        self.btn_hide = small("✕", "收起到托盘（Esc）")
        for b in (self.btn_watch, self.btn_pen, self.btn_lock, self.btn_set, self.btn_hide):
            lay.addWidget(b)

    # 拖动
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.host.locked:
            self._drag = e.globalPosition().toPoint() - self.host.frameGeometry().topLeft()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and not self.host.locked:
            self.host.move(e.globalPosition().toPoint() - self._drag)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.host.save_geometry()
        super().mouseReleaseEvent(e)


# ---------------------------------------------------------------- 捕获输入框
class CaptureEdit(QPlainTextEdit):
    def __init__(self, host: "BarWindow") -> None:
        super().__init__()
        self.host = host

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.host.submit()
            return
        if e.key() == Qt.Key_Escape:
            self.host.hide()
            return
        super().keyPressEvent(e)


# ---------------------------------------------------------------- 设置对话框
class SettingsDialog(QDialog):
    def __init__(self, host: "BarWindow") -> None:
        super().__init__(host)
        self.host = host
        self.setWindowTitle("CaptureDock 设置")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(430)

        st = host.st
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 13)
        form.setSpacing(12)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 80)
        self.slider.setValue(int(float(st["opacity"]) * 100))
        self.lbl_opacity = QLabel(f"{self.slider.value()}%")
        row = QHBoxLayout()
        row.addWidget(self.slider, 1)
        row.addWidget(self.lbl_opacity)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("背景不透明度", wrap)
        self.slider.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"{v}%"))

        self.chk_autohide = QCheckBox("捕获后 3 秒自动收起（默认关闭）")
        self.chk_autohide.setChecked(bool(st["autoHideAfterCapture"]))
        form.addRow("", self.chk_autohide)

        self.chk_clip = QCheckBox("监听剪贴板（仅提示，不自动入库）")
        self.chk_clip.setChecked(bool(st["clipboardWatch"]))
        form.addRow("", self.chk_clip)

        self.time_review = QTimeEdit()
        self.time_review.setDisplayFormat("HH:mm")
        try:
            h, m = str(st["reviewTime"]).split(":")
            self.time_review.setTime(QTime(int(h), int(m)))
        except Exception:
            self.time_review.setTime(QTime(18, 0))
        form.addRow("下班前回顾时间", self.time_review)

        note = QLabel("数据保存在本机 SQLite，不上传云端。")
        note.setObjectName("hint")
        form.addRow(note)

        # ---- 数据目录 ----
        self._dir = str(host.data_dir_now())
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.lbl_dir = QLineEdit(self._dir)
        self.lbl_dir.setReadOnly(True)
        self.lbl_dir.setToolTip("tasks.db 所在目录。点「浏览…」可换到别处（如 D 盘或网盘同步目录）。")
        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedWidth(58)
        btn_browse.clicked.connect(self._pick_dir)
        btn_open = QPushButton("打开")
        btn_open.setFixedWidth(46)
        btn_open.clicked.connect(host.open_data_dir)
        dir_row.addWidget(self.lbl_dir, 1)
        dir_row.addWidget(btn_browse)
        dir_row.addWidget(btn_open)
        dir_wrap = QWidget()
        dir_wrap.setLayout(dir_row)
        form.addRow("数据目录", dir_wrap)

        self.lbl_dir_hint = QLabel("换目录时会把现有任务复制过去，原文件保留作备份。")
        self.lbl_dir_hint.setObjectName("hint")
        form.addRow(self.lbl_dir_hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "选择数据存放目录", self._dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if d:
            self._dir = d
            self.lbl_dir.setText(d)

    def _save(self) -> None:
        st = self.host.st
        st["opacity"] = round(self.slider.value() / 100, 2)
        st["autoHideAfterCapture"] = self.chk_autohide.isChecked()
        st["clipboardWatch"] = self.chk_clip.isChecked()
        st["reviewTime"] = self.time_review.time().toString("HH:mm")
        self.host.apply_theme()
        self.host.topbar.btn_watch.setChecked(bool(st["clipboardWatch"]))
        self.host.set_clipboard_watch(bool(st["clipboardWatch"]))
        if self._dir and self._dir != str(self.host.data_dir_now()):
            if not self.host.change_data_dir(self._dir):
                return   # 目录切换未完成，保持弹窗不关闭，方便重选
        self.accept()


# ---------------------------------------------------------------- 主窗口
class BarWindow(QWidget):
    reminder_due = Signal(dict)
    count_changed = Signal(int)

    def __init__(self, db, st) -> None:
        super().__init__()
        self.db = db
        self.st = st
        self.locked = bool(st["locked"])
        self.ignore_mouse = False
        self._loading = False
        self._fired: set[str] = set()
        self._review_fired_on = None
        self._geo_timer = QTimer(self)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.setInterval(600)
        self._geo_timer.timeout.connect(self.save_geometry)

        self.setWindowTitle("CaptureDock")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowIcon(make_icon())
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        self._build_ui()
        self._create_resize_handles()
        self.pen_badge = PenBadge(self)
        self._restore_geometry()
        self.apply_theme()
        self._apply_columns()

        self.refresh()
        self._restore_flags()
        self._start_timers()
        self._init_clipboard()

    # ---------- UI 构建 ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.root = QFrame(self)
        self.root.setObjectName("root")
        outer.addWidget(self.root)

        v = QVBoxLayout(self.root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 顶栏
        self.topbar = TopBar(self)
        self.topbar.search.textChanged.connect(lambda _: self.refresh())
        self.topbar.btn_lock.clicked.connect(lambda: self.set_locked(self.topbar.btn_lock.isChecked()))
        self.topbar.btn_pen.clicked.connect(lambda: self.set_ignore_mouse(self.topbar.btn_pen.isChecked()))
        self.topbar.btn_watch.clicked.connect(
            lambda: self.set_clipboard_watch(self.topbar.btn_watch.isChecked()))
        self.topbar.btn_set.clicked.connect(self.open_settings)
        self.topbar.btn_hide.clicked.connect(self.hide)
        v.addWidget(self.topbar)

        # 捕获输入
        cap_wrap = QWidget()
        cap_wrap.setObjectName("capwrap")
        ch = QHBoxLayout(cap_wrap)
        ch.setContentsMargins(12, 4, 12, 8)
        ch.setSpacing(8)
        self.edit = CaptureEdit(self)
        self.edit.setPlaceholderText("粘贴消息内容，回车加入（Shift+Enter 换行，支持多行）")
        self.edit.setFixedHeight(58)
        self.btn_add = QPushButton("加入")
        self.btn_add.setObjectName("primary")
        self.btn_add.setFixedSize(62, 34)
        self.btn_add.clicked.connect(self.submit)
        ch.addWidget(self.edit, 1)
        ch.addWidget(self.btn_add)
        v.addWidget(cap_wrap)

        # 剪贴板提示条
        self.clip_bar = QWidget()
        self.clip_bar.setObjectName("clipbar")
        self.clip_bar.setVisible(False)
        cl = QHBoxLayout(self.clip_bar)
        cl.setContentsMargins(12, 0, 12, 6)
        cl.setSpacing(8)
        self.clip_label = QLabel("")
        self.clip_label.setObjectName("hint")
        self.btn_clip_add = QPushButton("加入待办")
        self.btn_clip_add.setFixedHeight(24)
        self.btn_clip_add.clicked.connect(self._use_clipboard_text)
        btn_clip_close = QPushButton("✕")
        btn_clip_close.setObjectName("ghost")
        btn_clip_close.setFixedWidth(22)
        btn_clip_close.clicked.connect(lambda: self.clip_bar.setVisible(False))
        cl.addWidget(self.clip_label, 1)
        cl.addWidget(self.btn_clip_add)
        cl.addWidget(btn_clip_close)
        v.addWidget(self.clip_bar)

        # 表格
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.viewport().setAutoFillBackground(False)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setFixedHeight(28)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        # 选中态 4 秒后自动取消，避免一直挂着蓝色高亮
        self._sel_timer = QTimer(self)
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(4000)
        self._sel_timer.timeout.connect(self.table.clearSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.viewport().installEventFilter(self)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)
        # hover 气泡：任务列文字被截断时，悬停 350ms 弹出完整内容
        self.bubble = HoverBubble()
        self._bubble_text = ""
        self._bubble_pos = None
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.setInterval(350)
        self._bubble_timer.timeout.connect(self._show_bubble)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        v.addWidget(self.table, 1)

        # 底部操作条：默认隐藏，选中某一行才出现（选中态 4 秒后自动取消，它也跟着收起）
        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("bottombar")
        bl = QHBoxLayout(self.bottom_bar)
        bl.setContentsMargins(12, 6, 12, 8)
        bl.setSpacing(6)
        self.btn_done = QPushButton("完成")
        self.btn_snooze = QPushButton("稍后 10 分钟")
        self.btn_archive = QPushButton("归档")
        self.btn_copy = QPushButton("复制原文")
        self.btn_delete = QPushButton("删除")
        self.btn_delete.setObjectName("danger")
        for b in (self.btn_done, self.btn_snooze, self.btn_archive,
                  self.btn_copy, self.btn_delete):
            b.setFixedHeight(26)
            b.setCursor(Qt.PointingHandCursor)
            bl.addWidget(b)
        bl.addStretch(1)
        self.bottom_bar.setVisible(False)
        v.addWidget(self.bottom_bar)

        # 「显示已完成」不占版面：状态由隐藏复选框持有，入口放在右键菜单与托盘菜单
        self.chk_show_done = QCheckBox("显示已完成", self)
        self.chk_show_done.setChecked(True)
        self.chk_show_done.hide()

        self.btn_done.clicked.connect(lambda: self._act("done"))
        self.btn_snooze.clicked.connect(lambda: self._act("snooze"))
        self.btn_archive.clicked.connect(lambda: self._act("archive"))
        self.btn_copy.clicked.connect(lambda: self._act("copy"))
        self.btn_delete.clicked.connect(lambda: self._act("delete"))
        self.chk_show_done.toggled.connect(lambda _: self.refresh())

    # ---------- 主题 / 标志 ----------
    def apply_theme(self) -> None:
        self.setStyleSheet(build_qss(float(self.st["opacity"])))
        self.table.viewport().setStyleSheet("background: transparent;")

    def _apply_columns(self) -> None:
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_TASK, QHeaderView.Stretch)
        for col, width in ((COL_STATUS, 76), (COL_REMIND, 132)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_columns()
        self._layout_handles()
        if self.ignore_mouse:
            self.pen_badge.sync_position()
            self.pen_badge.show()
            self.pen_badge.raise_()

    def hideEvent(self, e):
        self.pen_badge.hide()
        try:
            self._hide_bubble()
        except Exception:
            pass
        super().hideEvent(e)

    def _restore_flags(self) -> None:
        self.topbar.btn_lock.setChecked(self.locked)

        # 鼠标穿透不跨会话恢复：否则重启后窗口点不到。
        # 需要穿透时用 Ctrl+Alt+P 或托盘菜单开启。
        self.ignore_mouse = False
        self.topbar.btn_pen.setChecked(False)

        self.topbar.btn_watch.setChecked(bool(self.st["clipboardWatch"]))

    # ---------- 边缘缩放 ----------
    def _create_resize_handles(self) -> None:
        specs = {
            "l": (Qt.LeftEdge, Qt.SizeHorCursor),
            "r": (Qt.RightEdge, Qt.SizeHorCursor),
            "t": (Qt.TopEdge, Qt.SizeVerCursor),
            "b": (Qt.BottomEdge, Qt.SizeVerCursor),
            "tl": (Qt.LeftEdge | Qt.TopEdge, Qt.SizeFDiagCursor),
            "tr": (Qt.RightEdge | Qt.TopEdge, Qt.SizeBDiagCursor),
            "bl": (Qt.LeftEdge | Qt.BottomEdge, Qt.SizeBDiagCursor),
            "br": (Qt.RightEdge | Qt.BottomEdge, Qt.SizeFDiagCursor),
        }
        self._handles: dict[str, ResizeHandle] = {}
        for key, (edges, cursor) in specs.items():
            hnd = ResizeHandle(self, edges)
            hnd.setCursor(cursor)
            hnd.setToolTip("拖动调整窗口大小")
            self._handles[key] = hnd
        self._layout_handles()

    def _layout_handles(self) -> None:
        handles = getattr(self, "_handles", None)
        if not handles:
            return
        w, h = self.width(), self.height()
        e, c = RESIZE_EDGE, RESIZE_CORNER
        handles["tl"].setGeometry(0, 0, c, c)
        handles["tr"].setGeometry(w - c, 0, c, c)
        handles["bl"].setGeometry(0, h - c, c, c)
        handles["br"].setGeometry(w - c, h - c, c, c)
        handles["l"].setGeometry(0, c, e, max(0, h - 2 * c))
        handles["r"].setGeometry(w - e, c, e, max(0, h - 2 * c))
        handles["t"].setGeometry(c, 0, max(0, w - 2 * c), e)
        handles["b"].setGeometry(c, h - e, max(0, w - 2 * c), e)
        for hnd in handles.values():
            hnd.raise_()

    def _restore_geometry(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        geo = self.st["window"]
        if isinstance(geo, list) and len(geo) == 4:
            x, y, w, h = (int(v) for v in geo)
            w = max(MIN_WIDTH, min(w, screen.width()))
            h = max(MIN_HEIGHT, min(h, screen.height()))
            # 整窗保持在屏幕内，避免拖出后找不回来
            x = max(screen.left(), min(x, screen.right() - w))
            y = max(screen.top(), min(y, screen.bottom() - h))
            self.setGeometry(x, y, w, h)
            return
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.move(screen.right() - self.width() - 40, screen.top() + 90)

    def moveEvent(self, e):
        self._geo_timer.start()
        if getattr(self, "ignore_mouse", False) and getattr(self, "pen_badge", None):
            self.pen_badge.sync_position()
        super().moveEvent(e)

    def resizeEvent(self, e):
        self._geo_timer.start()
        self._layout_handles()
        if getattr(self, "ignore_mouse", False) and getattr(self, "pen_badge", None):
            self.pen_badge.sync_position()
        super().resizeEvent(e)

    def save_geometry(self) -> None:
        g = self.geometry()
        self.st["window"] = [g.x(), g.y(), g.width(), g.height()]
        self.st.save()

    # ---------- 解锁/穿透 ----------
    def set_locked(self, on: bool) -> None:
        self.locked = bool(on)
        self.st["locked"] = self.locked
        self.st.save()
        self.topbar.btn_lock.setChecked(self.locked)


    def set_ignore_mouse(self, on: bool) -> None:
        self.ignore_mouse = bool(on)
        self.st["ignoreMouse"] = self.ignore_mouse
        self.st.save()
        self._apply_ignore_mouse(self.ignore_mouse)
        self.topbar.btn_pen.setChecked(self.ignore_mouse)

        # 穿透后整个窗口点不到，留一个可点的浮标用于恢复
        if self.ignore_mouse:
            self.pen_badge.sync_position()
            self.pen_badge.show()
            self.pen_badge.raise_()
        else:
            self.pen_badge.hide()
    def _apply_ignore_mouse(self, on: bool) -> None:
        if sys.platform == "win32":
            if set_click_through(int(self.winId()), on):
                return
        # 兜底：非 Windows 或调用失败时走 Qt 原生开关
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        self.show()
        if not on:
            self.raise_()
            self.activateWindow()

    def toggle_ignore_mouse(self) -> None:
        self.set_ignore_mouse(not self.ignore_mouse)

    # ---------- 剪贴板 ----------
    def _init_clipboard(self) -> None:
        self._clip = QGuiApplication.clipboard()
        self._clip.dataChanged.connect(self._on_clipboard_changed)
        self._clip_last = ""
        self._clip_enabled = bool(self.st["clipboardWatch"])

    def set_clipboard_watch(self, on: bool) -> None:
        self._clip_enabled = bool(on)
        self.st["clipboardWatch"] = self._clip_enabled
        self.st.save()
        self.topbar.btn_watch.setChecked(self._clip_enabled)

        if not self._clip_enabled:
            self.clip_bar.setVisible(False)

    def _on_clipboard_changed(self) -> None:
        if not self._clip_enabled:
            return
        text = (self._clip.text() or "").strip()
        if not text or text == self._clip_last:
            return
        self._clip_last = text
        preview = text.splitlines()[0][:40]
        self.clip_label.setText(f"检测到新复制内容：{preview}")
        self.btn_clip_add.setToolTip(text[:800])
        self.clip_bar.setVisible(True)

    def _use_clipboard_text(self) -> None:
        """一键入库：不经过输入框，减少点击次数。"""
        text = (self._clip.text() or "").strip()
        if text:
            self.db.create(text)
            self._clip_last = text
            self.clip_bar.setVisible(False)
            self.refresh()
            self.table.selectRow(0)
        self.clip_bar.setVisible(False)

    # ---------- 表格渲染 ----------
    def refresh(self) -> None:
        # 记录当前选中行，刷新后按 task id 复原，避免连续操作丢失选中
        keep = None
        cur = self.table.currentRow()
        if cur >= 0:
            it = self.table.item(cur, COL_STATUS)
            if it:
                keep = it.data(Qt.UserRole)

        self._loading = True
        try:
            search = self.topbar.search.text().strip()
            tasks = self.db.list_tasks(search, include_done=self.chk_show_done.isChecked())
            self.table.setRowCount(len(tasks))
            for row, t in enumerate(tasks):
                self._fill_row(row, t)
                self.table.setRowHeight(row, 38)
        finally:
            self._loading = False

        if keep:
            for row in range(self.table.rowCount()):
                it = self.table.item(row, COL_STATUS)
                if it and it.data(Qt.UserRole) == keep:
                    self.table.selectRow(row)
                    break
        self._update_counter()

    def _fill_row(self, row: int, t: dict) -> None:
        done = t["status"] == STATUS_DONE

        it_status = QTableWidgetItem(STATUS_LABEL.get(t["status"], t["status"]))
        it_status.setForeground(QColor(STATUS_COLOR.get(t["status"], "#e9e9ef")))
        it_status.setTextAlignment(Qt.AlignCenter)
        it_status.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it_status.setData(Qt.UserRole, t["id"])
        self.table.setItem(row, COL_STATUS, it_status)

        it_task = QTableWidgetItem(t["task_text"])
        it_task.setData(Qt.UserRole + 1, t["raw_text"])
        it_task.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        if done:
            f = QFont()
            f.setStrikeOut(True)
            it_task.setFont(f)
            it_task.setForeground(QColor("#8b90a0"))
        self.table.setItem(row, COL_TASK, it_task)

        it_rem = QTableWidgetItem(fmt_remind(t["remind_at"]))
        it_rem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if t["remind_at"] and not done:
            overdue = t["remind_at"] <= int(time.time() * 1000)
            it_rem.setForeground(QColor("#ef4444" if overdue else "#9aa0ad"))
        else:
            it_rem.setForeground(QColor("#9aa0ad"))
        self.table.setItem(row, COL_REMIND, it_rem)


    def _update_counter(self) -> None:
        n = self.db.open_count()
        self.topbar.counter.setText(f"未完成 {n}")
        self.count_changed.emit(n)

    def current_task(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, COL_STATUS)
        if not it:
            return None
        tid = it.data(Qt.UserRole)
        return self.db.get(tid) if tid else None

    # ---------- 编辑 ----------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        head = self.table.item(row, COL_STATUS)
        if not head:
            return
        tid = head.data(Qt.UserRole)
        if not tid:
            return
        if item.column() == COL_TASK:
            text = item.text().strip()
            if text:
                self.db.update(tid, task_text=text)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        head = self.table.item(row, COL_STATUS)
        if not head:
            return
        tid = head.data(Qt.UserRole)
        if not tid:
            return
        if col == COL_STATUS:
            task = self.db.get(tid)
            if task:
                # 双击只做「完成 / 未完成」两态切换：一次双击就能收掉一条
                self._set_status(tid, STATUS_NEXT.get(task["status"], "done"))
        elif col == COL_REMIND:
            self._edit_remind(tid)

    def _edit_remind(self, tid: str) -> None:
        task = self.db.get(tid)
        if not task:
            return
        default = ""
        if task["remind_at"]:
            default = datetime.fromtimestamp(task["remind_at"] / 1000).strftime("%H:%M")
        text, ok = QInputDialog.getText(
            self, "设置提醒",
            "输入时间：HH:MM（今天，已过则顺延到明天）\n或 MM-DD HH:MM（清空即取消提醒）",
            QLineEdit.Normal, default)
        if not ok:
            return
        text = text.strip()
        if not text:
            self.db.update(tid, remind_at=None)
            self._fired.discard(tid)
        else:
            ms = parse_remind(text)
            if ms is None:
                QMessageBox.warning(self, "格式不对", "请按 HH:MM 或 MM-DD HH:MM 输入。")
                return
            self.db.update(tid, remind_at=ms)
            self._fired.discard(tid)
        self.refresh()

    # ---------- 捕获 ----------
    def submit(self) -> None:
        text = self.edit.toPlainText().strip()
        if not text:
            return
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) > 1:
            box = QMessageBox(self)
            box.setWindowTitle("检测到多行内容")
            box.setText(f"共 {len(lines)} 行，如何保存？")
            b_merge = box.addButton("合并一条", QMessageBox.AcceptRole)
            b_split = box.addButton("拆成多条", QMessageBox.ActionRole)
            box.setDefaultButton(b_merge)
            box.exec()
            clicked = box.clickedButton()
            if clicked is None:
                return
            if clicked is b_split:
                for line in lines:
                    self.db.create(line)
                self.edit.clear()
                self._after_capture(len(lines))
                return
        self.db.create(text)
        self.edit.clear()
        self._after_capture(1)

    def _after_capture(self, count: int) -> None:
        self.refresh()
        if count == 1:
            row = 0
            if self.table.rowCount() > 0:
                self.table.selectRow(row)
        if self.st["autoHideAfterCapture"]:
            QTimer.singleShot(3000, self.hide)

    # ---------- 行操作 ----------
    def _act(self, action: str) -> None:
        task = self.current_task()
        if not task:
            return
        tid = task["id"]
        if action == "done":
            if task["status"] == STATUS_DONE:
                self.db.update(tid, status="todo", completed_at=None)
            else:
                self.db.complete(tid)
            self._fired.discard(tid)
        elif action == "snooze":
            self.db.snooze(tid, 10)
            self._fired.discard(tid)
        elif action == "archive":
            self.db.archive(tid)
        elif action == "delete":
            if QMessageBox.question(self, "删除", "确定删除这条记录？",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.db.delete(tid)
        elif action == "copy":
            QGuiApplication.clipboard().setText(task["raw_text"])
            self._clip_last = task["raw_text"]
        self.refresh()

    def _show_row_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        task = self.current_task()
        if not task:
            return
        m = QMenu(self)
        m.addAction("设为待办", lambda: self._set_status(task["id"], "todo"))
        m.addAction("设为进行中", lambda: self._set_status(task["id"], "doing"))
        m.addAction("设为稍后", lambda: self._set_status(task["id"], "later"))
        m.addAction("设为完成", lambda: self._set_status(task["id"], "done"))
        m.addSeparator()
        m.addAction("设置提醒…", lambda: self._edit_remind(task["id"]))
        m.addAction("稍后 10 分钟提醒", lambda: self._snooze(task["id"]))
        m.addSeparator()
        m.addAction("查看原始消息", lambda: self._show_raw(task))
        m.addAction("复制原文", lambda: QGuiApplication.clipboard().setText(task["raw_text"]))
        m.addSeparator()
        m.addAction("归档", lambda: self._archive(task["id"]))
        m.addAction("删除", lambda: self._delete(task["id"]))
        m.addSeparator()
        act_done = m.addAction("显示已完成任务")
        act_done.setCheckable(True)
        act_done.setChecked(self.chk_show_done.isChecked())
        act_done.toggled.connect(self.set_show_done)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def set_show_done(self, on: bool) -> None:
        self.chk_show_done.setChecked(bool(on))
        self.refresh()

    def _set_status(self, tid: str, status: str) -> None:
        self.db.update(tid, status=status,
                       completed_at=int(time.time() * 1000) if status == STATUS_DONE else None)
        self.refresh()

    def _snooze(self, tid: str) -> None:
        self.db.snooze(tid, 10)
        self._fired.discard(tid)
        self.refresh()

    def _archive(self, tid: str) -> None:
        self.db.archive(tid)
        self.refresh()

    def _delete(self, tid: str) -> None:
        self.db.delete(tid)
        self.refresh()

    def _show_raw(self, task: dict) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("原始消息")
        box.setText(task["raw_text"][:2000])
        box.exec()

    # ---------- 定时任务 ----------
    def _start_timers(self) -> None:
        self._remind_timer = QTimer(self)
        self._remind_timer.setInterval(15000)
        self._remind_timer.timeout.connect(self.check_reminders)
        self._remind_timer.start()

        self._review_timer = QTimer(self)
        self._review_timer.setInterval(60_000)
        self._review_timer.timeout.connect(self.check_review)
        self._review_timer.start()

        QTimer.singleShot(1200, self.check_reminders)

    def check_reminders(self) -> None:
        now = int(time.time() * 1000)
        for t in self.db.due_tasks(now):
            if t["id"] in self._fired:
                continue
            self._fired.add(t["id"])
            self.reminder_due.emit(t)
        self._update_counter()

    def check_review(self) -> None:
        try:
            h, m = str(self.st["reviewTime"]).split(":")
            target = datetime.now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        except Exception:
            return
        now = datetime.now()
        today = now.date()
        if now >= target and self._review_fired_on != today:
            self._review_fired_on = today
            n = self.db.open_count()
            if n > 0:
                self.reminder_due.emit({
                    "id": "__review__",
                    "task_text": f"今天就到这儿了，还有 {n} 项未完成",
                    "raw_text": "",
                    "remind_at": None,
                    "status": "todo",
                })

    # ---------- 快捷键动作 ----------
    def show_capture(self) -> None:
        if self.ignore_mouse:
            self.set_ignore_mouse(False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()

    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    # ---------- 数据目录 ----------
    def data_dir_now(self) -> Path:
        return Path(self.db.path).parent

    def change_data_dir(self, target: str) -> bool:
        """切换数据目录。新目录没有库时把现有数据复制过去（原文件保留作备份）。"""
        if not target:
            return False
        try:
            new_dir = Path(target).expanduser()
            new_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "目录不可用", f"无法使用该目录：\n{target}\n\n{e}")
            return False
        if not new_dir.is_dir():
            QMessageBox.warning(self, "目录不可用", f"不是有效目录：\n{target}")
            return False

        new_db = new_dir / "tasks.db"
        cur_db = Path(self.db.path)
        try:
            same = new_db.resolve() == cur_db.resolve()
        except Exception:
            same = False
        if same:
            return True

        if new_db.exists():
            ok = QMessageBox.question(
                self, "目录中已有数据",
                f"目标目录已存在 tasks.db：\n{new_db}\n\n"
                "是否直接使用其中的数据？\n（选「否」则保持当前目录不变，不覆盖任何文件）",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
            if not ok:
                return False
        else:
            try:
                self.db.backup_to(new_db)   # 复制现有任务到新目录
            except Exception as e:
                QMessageBox.warning(self, "复制失败", f"复制数据失败，未做切换：\n{e}")
                return False

        try:
            self.db.reopen(new_db)
        except Exception as e:
            QMessageBox.critical(self, "切换失败", f"打开新数据库失败，已回退：\n{e}")
            self.db.reopen(cur_db)
            return False

        self.st["dataDir"] = str(new_dir)
        self.st.save()
        self.refresh()
        return True

    def open_data_dir(self) -> None:
        d = self.data_dir_now()
        try:
            if sys.platform.startswith("win"):
                import os
                os.startfile(str(d))  # noqa: S606
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(d)])
        except Exception:
            pass

    def reset_geometry(self) -> None:
        """还原默认大小与位置：窗口缩得太小或跑到屏幕外时用来兜底。"""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.move(screen.right() - self.width() - 40, screen.top() + 90)
        self.save_geometry()

    def _on_selection_changed(self) -> None:
        model = self.table.selectionModel()
        has = model is not None and model.hasSelection()
        if has:
            self._sel_timer.start()
        else:
            self._sel_timer.stop()
        # 底部操作条只在选中行时出现，不占常驻空间
        if self.bottom_bar.isVisible() != has:
            self.bottom_bar.setVisible(has)
            self._layout_handles()

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport():
            et = ev.type()
            # 点表格空白处立即取消选中
            if et == QEvent.MouseButtonPress:
                if not self.table.indexAt(ev.pos()).isValid():
                    self.table.clearSelection()
                self._hide_bubble()
            elif et == QEvent.MouseMove:
                self._hover_move(ev.pos())
            elif et in (QEvent.Leave, QEvent.Wheel):
                self._hide_bubble()
        return super().eventFilter(obj, ev)

    # ---------- hover 气泡 ----------
    def _task_elided(self, row: int) -> bool:
        it = self.table.item(row, COL_TASK)
        if not it or not it.text():
            return False
        avail = self.table.columnWidth(COL_TASK) - 16
        return self.table.fontMetrics().horizontalAdvance(it.text()) > avail

    def _hover_move(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if (not idx.isValid() or idx.column() != COL_TASK
                or not self._task_elided(idx.row())):
            self._hide_bubble()
            return
        it = self.table.item(idx.row(), COL_TASK)
        text = it.data(Qt.UserRole + 1) or it.text()
        self._bubble_text = text
        self._bubble_pos = self.table.viewport().mapToGlobal(pos)
        if self.bubble.isVisible():
            self.bubble.show_text(self._bubble_text, self._bubble_pos)
        else:
            self._bubble_timer.start()

    def _show_bubble(self) -> None:
        if self._bubble_pos is None or self.ignore_mouse:
            return
        self.bubble.show_text(self._bubble_text, self._bubble_pos)

    def _hide_bubble(self) -> None:
        self._bubble_timer.stop()
        self._bubble_pos = None
        self.bubble.hide_now()

    def pulse(self) -> None:
        """到点提醒时让可见窗口边框闪一下，不弹窗。"""
        if not self.isVisible():
            return
        state = {"n": 0}

        def step() -> None:
            state["n"] += 1
            self.root.setProperty("alert", state["n"] % 2 == 1)
            self.root.style().unpolish(self.root)
            self.root.style().polish(self.root)
            if state["n"] < 7:
                QTimer.singleShot(320, step)

        step()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(e)
