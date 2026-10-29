"""打包入口。

`python -m app.main` 用的是包内相对导入，PyInstaller 直接分析会失败，
所以这里做一层绝对导入的壳，PyInstaller 用 -F/-D 指向本文件即可。
"""
import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
