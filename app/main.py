"""CaptureDock 入口。"""
from __future__ import annotations

import sys

from PySide6.QtCore import QSharedMemory, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import APP_NAME, APP_VERSION, db_path_for
from .db import DB
from .settings import Settings
from .bar_window import BarWindow
from .pet_window import PetWindow
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

    def to_bar(with_capture: bool = True) -> None:
        pet.hide()
        st["mode"] = "bar"
        if with_capture:
            win.show_capture()
        else:
            win.show()

    def to_pet() -> None:
        win.hide()
        st["mode"] = "pet"
        pet.show_pet()

    def toggle_mode() -> None:
        if pet.isVisible():
            to_bar()
        else:
            to_pet()

    pet = PetWindow(
        db, st,
        on_open_bar=lambda: to_bar(),
        on_open_settings=lambda: (to_bar(False),
                                  QTimer.singleShot(120, win.open_settings)),
    )

    tray = TrayController(win, app, toggle_mode=toggle_mode,
                          show_bar=lambda: to_bar())
    tray.show()
    win.reminder_due.connect(tray.on_reminder)

    # 启动形态
    if str(st["mode"]) == "pet":
        pet.show_pet()
    else:
        win.show()

    # 全局快捷键（Win32 RegisterHotKey，无需管理员权限）
    hk = HotkeyManager(int(win.winId()))
    app.installNativeEventFilter(hk)
    hk.triggered.connect(lambda name: {
        "capture": lambda: to_bar() if pet.isVisible() else win.show_capture(),
        "toggle_pen": win.toggle_ignore_mouse,
        "toggle_win": lambda: (to_bar() if pet.isVisible()
                               else (win.hide() if win.isVisible()
                                     else win.show_capture())),
        "toggle_mode": toggle_mode,
        "reset_win": lambda: (pet._reset_pos() if pet.isVisible()
                              else win.reset_geometry()),
    }.get(name, lambda: None)())

    failed = []
    if not hk.register("capture", MOD_CONTROL | MOD_SHIFT, VK["space"]):
        failed.append("Ctrl+Shift+Space")
    if not hk.register("toggle_mode", MOD_CONTROL | MOD_SHIFT, VK["m"]):
        failed.append("Ctrl+Shift+M")
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
        pet.save_pos()


if __name__ == "__main__":
    sys.exit(main())
