"""路径与常量。"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "CaptureDock"
APP_VERSION = "0.1.0"


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = data_dir()
DB_PATH = DATA_DIR / "tasks.db"
SETTINGS_PATH = DATA_DIR / "settings.json"


def db_path_for(data_dir: str | None = None) -> Path:
    """把设置里的自定义目录解析成具体 db 文件路径；空或不可用则回退默认目录。

    注意：settings.json 始终留在默认目录，避免"换目录后找不到设置"。
    """
    if data_dir:
        try:
            p = Path(str(data_dir)).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            if p.is_dir():
                return p / "tasks.db"
        except Exception:
            pass
    return DB_PATH

# 状态
STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_DONE = "done"
STATUS_LATER = "later"

STATUS_LABEL = {
    STATUS_TODO: "待办",
    STATUS_DOING: "进行中",
    STATUS_DONE: "完成",
    STATUS_LATER: "稍后",
}
STATUS_NEXT = {
    STATUS_TODO: STATUS_DONE,
    STATUS_DOING: STATUS_DONE,
    STATUS_LATER: STATUS_DONE,
    STATUS_DONE: STATUS_TODO,
}
STATUS_COLOR = {
    STATUS_TODO: "#e8b339",
    STATUS_DOING: "#3b82f6",
    STATUS_LATER: "#a78bfa",
    STATUS_DONE: "#4ade80",
}

DEFAULT_SOURCE = "企业微信"
