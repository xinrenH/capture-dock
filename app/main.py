"""CaptureDock 入口。"""
from __future__ import annotations

import sys

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import APP_NAME, APP_VERSION, db_path_for
from .db import DB
from .settings import Settings
from .bar_window import BarWindow
from .tray import TrayController
from .hotkey import HotkeyManager, MOD_CONTROL, MOD_SHIFT, MOD_ALT, VK


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)

    # 单实例
    guard = QSharedMemory("CaptureDock.singleton.v1")
    if not guard.create(1):
        QMessageBox.information(
            None, APP_NAME,
            "CaptureDock 已在运行。\n按 Ctrl+Shift+Space 呼出捕获窗口。")
        return 0

    st = Settings()
    db = DB(db_path_for(st["dataDir"]))
    win = BarWindow(db, st)
    win.show()

    tray = TrayController(win, app)
    tray.show()

    win.reminder_due.connect(tray.on_reminder)

    # 全局快捷键（Win32 RegisterHotKey，无需管理员权限）
    hk = HotkeyManager(int(win.winId()))
    app.installNativeEventFilter(hk)
    hk.triggered.connect(lambda name: {
        "capture": win.show_capture,
        "toggle_pen": win.toggle_ignore_mouse,
        "toggle_win": lambda: win.hide() if win.isVisible() else win.show_capture(),
        "reset_win": win.reset_geometry,
    }.get(name, lambda: None)())

    failed = []
    if not hk.register("capture", MOD_CONTROL | MOD_SHIFT, VK["space"]):
        failed.append("Ctrl+Shift+Space")
    if not hk.register("toggle_pen", MOD_CONTROL | MOD_ALT, VK["p"]):
        failed.append("Ctrl+Alt+P")
    if not hk.register("reset_win", MOD_CONTROL | MOD_ALT, VK["r"]):
        failed.append("Ctrl+Alt+R")
    if failed:
        tray.tray.showMessage(
            "快捷键注册失败",
            "以下快捷键被其他程序占用：" + "、".join(failed) +
            "\n仍可通过托盘菜单使用。", 8000)

    try:
        return app.exec()
    finally:
        hk.unregister_all()
        win.save_geometry()


if __name__ == "__main__":
    sys.exit(main())
