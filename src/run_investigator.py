"""启动“排查助手”本地图形界面。

用法（在项目根目录）：

    .\\.venv\\Scripts\\python.exe -X utf8 src\\run_investigator.py

只使用 Python 标准库与 Tkinter；不联网、不启动摄像头、不修改任何源材料。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from investigator.ui import main  # noqa: E402  (路径先就位再导入)


if __name__ == "__main__":
    raise SystemExit(main())
