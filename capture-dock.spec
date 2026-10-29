# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：目标「体积尽量小、启动快」。

构建：.venv\\Scripts\\pyinstaller.exe capture-dock.spec --noconfirm --clean
产物：dist\\CaptureDock\\CaptureDock.exe（目录版，双击即用）

说明：用目录版（onefile 会把 Qt 解压到临时目录，每次启动慢 2-4 秒，
对一个常驻的快捷键小工具不划算）。分发时把整个 dist\\CaptureDock 打成一个 zip。
"""

# 程序只用到 QtCore / QtGui / QtWidgets，其余 Qt 模块全部剔除
EXCLUDED = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtNetwork", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDBus", "PySide6.QtPrintSupport",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtUiTools",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtMultimedia",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    # 标准库里用不到的大件
    "tkinter", "unittest", "doctest", "pydoc", "pdb", "pytest",
    "setuptools", "pip", "wheel", "sqlite3.test",
]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDED,
    noarchive=False,
    optimize=2,
)

# ---------------------------------------------------------------- 体积裁剪
import os

# 用不到的原生库/插件：OpenGL 软件渲染 20MB、OpenSSL（QtNetwork 已剔除）、
# 多余的平台/输入/图片格式插件
DROP_BIN = {
    "opengl32sw.dll",
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
    "qdirect2d.dll",
    "qoffscreen.dll",
    "qminimal.dll",
    "qtuiotouchplugin.dll",
    "qsvgicon.dll",
}
# 只保留 ico 图片格式（PNG 是 Qt 内置的）
KEEP_IMAGEFORMATS = {"qico.dll"}
# 界面全中文，翻译只留简体
KEEP_TRANSLATIONS = {"qt_zh_cn.qm", "qt_zh_tw.qm"}


def _keep_binary(dest: str) -> bool:
    low = dest.replace("\\", "/").lower()
    name = os.path.basename(low)
    if name in DROP_BIN:
        return False
    if "/imageformats/" in low and name not in KEEP_IMAGEFORMATS:
        return False
    return True


def _keep_data(dest: str) -> bool:
    low = dest.replace("\\", "/").lower()
    if "/translations/" in low and os.path.basename(low) not in KEEP_TRANSLATIONS:
        return False
    return True


a.binaries = [e for e in a.binaries if _keep_binary(e[0])]
a.datas = [e for e in a.datas if _keep_data(e[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CaptureDock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 容易被杀软误报，不用
    console=False,          # 无控制台窗口
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CaptureDock",
)
