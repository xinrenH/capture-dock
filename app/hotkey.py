"""全局快捷键：直接调用 Win32 RegisterHotKey，零第三方依赖、无需管理员权限。"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

user32 = ctypes.windll.user32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

VK = {
    "space": 0x20, "m": 0x4D, "p": 0x50, "c": 0x43, "r": 0x52, "d": 0x44,
    "esc": 0x1B,
}


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


def _msg_addr(message) -> int:
    """兼容不同 PySide6 版本对 nativeEventFilter message 参数的包装。"""
    try:
        return int(message)
    except Exception:
        pass
    try:
        from shiboken6 import VoidPtr  # type: ignore
        return int(VoidPtr(message))
    except Exception:
        return 0


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """注册表: {hotkey_id: name}，按下时发出 triggered(name)。"""

    triggered = Signal(str)

    def __init__(self, hwnd: int, parent=None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.hwnd = hwnd
        self._registry: dict[int, str] = {}
        self._next_id = 0xA001
        self._registered: list[int] = []
        self._last_fired: dict[str, float] = {}

    def register(self, name: str, modifiers: int, vk: int) -> bool:
        hid = self._next_id
        self._next_id += 1
        # MOD_NOREPEAT: 按住不放时只在按下瞬间触发一次，避免反复切换
        ok = bool(user32.RegisterHotKey(self.hwnd, hid, modifiers | MOD_NOREPEAT, vk))
        if ok:
            self._registry[hid] = name
            self._registered.append(hid)
        return ok

    def unregister_all(self) -> None:
        for hid in self._registered:
            try:
                user32.UnregisterHotKey(self.hwnd, hid)
            except Exception:
                pass
        self._registered.clear()
        self._registry.clear()

    def _fire(self, name: str) -> None:
        """去抖：250ms 内同一快捷键只触发一次，防止抖动导致状态反复切换。"""
        now = time.monotonic()
        if now - self._last_fired.get(name, 0.0) < 0.25:
            return
        self._last_fired[name] = now
        self.triggered.emit(name)

    def nativeEventFilter(self, event_type, message):
        try:
            if "windows" in str(event_type).lower():
                addr = _msg_addr(message)
                if addr:
                    msg = MSG.from_address(addr)
                    if msg.message == WM_HOTKEY:
                        name = self._registry.get(int(msg.wParam))
                        if name:
                            self._fire(name)
        except Exception:
            pass
        return False, 0
