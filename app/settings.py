"""设置持久化（JSON）。"""
from __future__ import annotations

import json
from pathlib import Path

from .config import SETTINGS_PATH

DEFAULTS = {
    "opacity": 0.45,          # 背景不透明度 0.10 ~ 0.80
    "locked": False,
    "ignoreMouse": False,
    "mode": "bar",            # bar | pet
    "clipboardWatch": False,
    "autoHideAfterCapture": False,   # 默认不自动收起，避免刚加完就消失
    "reviewTime": "18:00",
    "window": None,           # [x, y, w, h]
    "dataDir": "",            # 自定义数据目录，空 = %APPDATA%\CaptureDock
}


class Settings:
    def __init__(self, path: str | Path = SETTINGS_PATH) -> None:
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
            except Exception:
                pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
