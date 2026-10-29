"""生成 assets/icon.ico：与程序内托盘/窗口图标同一套画法。

Windows 支持 PNG 压缩的 ICO 条目（Vista 起），所以这里直接把手绘的
PNG 塞进 ICO 容器，不依赖 Pillow。
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> bytes:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3b6ef6"))
    p.drawRoundedRect(1, 1, size - 2, size - 2, size * 0.26, size * 0.26)
    p.setPen(QPen(QColor("#ffffff"), max(2, size // 10)))
    p.drawLine(int(size * 0.5), int(size * 0.26), int(size * 0.5), int(size * 0.54))
    p.drawLine(int(size * 0.5), int(size * 0.54), int(size * 0.70), int(size * 0.66))
    p.end()

    # 存临时文件再读回：QPixmap.save 到 QBuffer 在 PySide6 下会直接 abort
    tmp = os.path.join(tempfile.gettempdir(), f"capturedock_{size}.png")
    if not pm.save(tmp, "PNG"):
        raise RuntimeError("生成 PNG 失败")
    data = Path(tmp).read_bytes()
    os.remove(tmp)
    return data


def main() -> None:
    _app = QApplication(sys.argv)          # QPixmap 需要 QGuiApplication
    images = [(s, render(s)) for s in SIZES]

    out_dir = Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "icon.ico"

    header = struct.pack("<HHH", 0, 1, len(images))   # reserved, type=icon, count
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII",
                               size if size < 256 else 0,
                               size if size < 256 else 0,
                               0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    out.write_bytes(header + entries + blobs)
    print("icon written:", out, out.stat().st_size, "bytes", flush=True)


if __name__ == "__main__":
    main()
