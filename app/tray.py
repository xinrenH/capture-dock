"""系统托盘：常驻图标、菜单、轻提醒通知。"""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from .bar_window import make_icon, fmt_remind


class TrayController:
    def __init__(self, window, app: QApplication) -> None:
        self.window = window
        self.app = app
        self.tray = QSystemTrayIcon(make_icon(), window)
        self.tray.setToolTip("CaptureDock")
        self._build_menu()
        self.tray.activated.connect(self._on_activated)
        self.tray.messageClicked.connect(self.window.show_capture)
        window.count_changed.connect(self._on_count)

    def _build_menu(self) -> None:
        m = QMenu()
        m.addAction(QAction("呼出捕获  Ctrl+Shift+Space", m,
                            triggered=self.window.show_capture))
        m.addSeparator()

        self.act_show = QAction("显示 / 隐藏窗口", m, triggered=self._toggle_show)
        m.addAction(self.act_show)

        self.act_lock = QAction("锁定位置", m, checkable=True,
                                triggered=lambda v: self.window.set_locked(v))
        self.act_lock.setChecked(self.window.locked)
        m.addAction(self.act_lock)

        self.act_pen = QAction("鼠标穿透  Ctrl+Alt+P", m, checkable=True,
                               triggered=lambda v: self.window.set_ignore_mouse(v))
        self.act_pen.setChecked(self.window.ignore_mouse)
        m.addAction(self.act_pen)

        self.act_clip = QAction("监听剪贴板", m, checkable=True,
                                triggered=lambda v: self.window.set_clipboard_watch(v))
        self.act_clip.setChecked(bool(self.window.st["clipboardWatch"]))
        m.addAction(self.act_clip)

        m.addSeparator()
        self.act_done = QAction("显示已完成任务", m, checkable=True,
                                triggered=self.window.set_show_done)
        self.act_done.setChecked(self.window.chk_show_done.isChecked())
        m.addAction(self.act_done)
        m.addAction(QAction("还原默认大小与位置  Ctrl+Alt+R", m,
                            triggered=self.window.reset_geometry))
        m.addAction(QAction("设置…", m, triggered=self.window.open_settings))
        m.addSeparator()
        m.addAction(QAction("退出 CaptureDock", m, triggered=self.quit))

        self.menu = m
        self.tray.setContextMenu(m)

    def show(self) -> None:
        self.tray.show()

    def _toggle_show(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show_capture()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.window.show_capture()

    def _on_count(self, n: int) -> None:
        self.tray.setToolTip(f"CaptureDock · 未完成 {n}")
        self.act_lock.setChecked(self.window.locked)
        self.act_pen.setChecked(self.window.ignore_mouse)
        self.act_clip.setChecked(bool(self.window.st["clipboardWatch"]))

    # 到点提醒：只做轻提醒，不弹大窗
    def on_reminder(self, task: dict) -> None:
        title = "任务到点提醒" if task.get("id") != "__review__" else "下班前回顾"
        body = task.get("task_text", "")
        if task.get("remind_at"):
            body = f"{body}\n提醒时间 {fmt_remind(task['remind_at'])}"
        self.tray.showMessage(title, body, make_icon(), 8000)
        # 顺带让窗口闪一下提示条，避免只存不提醒
        if hasattr(self.window, "pulse"):
            self.window.pulse()

    def quit(self) -> None:
        try:
            self.window.save_geometry()
        except Exception:
            pass
        self.tray.hide()
        self.app.quit()
