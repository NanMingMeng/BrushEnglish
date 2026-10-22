# -*- coding: utf-8 -*-
"""刷单词助手（新版）：PySide6 + QML 界面。

启动方式：
    python 刷单词助手新版.py

和老版的区别：
- 老版是 PyQt6 + 传统控件（授权协议比较苛刻，打包分发有麻烦）。
- 新版是 PySide6 + QML（授权宽松，界面用描述式语言写，改样式不用动 Python）。
- 刷单词的核心脚本（完整脚本_学习测试循环.py）一行都没动，行为完全一样。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 让 Python 找得到 appcore 这个包
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# 打包成窗口程序时没有控制台，这里要兜住
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

from appcore import paths
from appcore.controller import AppController


def configure_environment() -> None:
    """开机设置：高 DPI、渲染后端等。

    高 DPI 这句的意思是：让窗口在 150% 缩放的屏幕上也清清楚楚，
    不会糊成一片或者控件对不上位置。
    """
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 关键：Qt 默认的「原生样式」(Windows 11 风格) 不允许改按钮背景，
    # 换成 Basic 之后，我们在 QML 里自己画的圆角、颜色才生效。
    # 这一句必须在 QGuiApplication 创建之前设置。
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    # 软件渲染兜底：有些机器上显卡驱动挑食，用软件渲染能正常显示
    if os.environ.get("BRUSH_SW_RENDER") == "1":
        os.environ["QSG_RENDER_LOOP"] = "basic"
    # 软件渲染兜底：有些机器上显卡驱动挑食，用软件渲染能正常显示
    if os.environ.get("BRUSH_SW_RENDER") == "1":
        os.environ["QSG_RENDER_LOOP"] = "basic"


def main() -> int:
    configure_environment()

    app = QGuiApplication(sys.argv)
    app.setApplicationName(paths.APP_NAME)
    app.setApplicationDisplayName(paths.APP_NAME)
    app.setOrganizationName("OneClass")

    qml_dir = paths.qml_dir()

    # 把 Theme 注册成 QML 单例：界面里 import BrushUI 1.0 后直接用 Theme.col("bg")
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(str(qml_dir / "Theme.qml")),
        "BrushUI",
        1,
        0,
        "Theme",
    )

    controller = AppController()

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir))
    engine.rootContext().setContextProperty("backend", controller)

    main_qml = qml_dir / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        print("界面加载失败：%s" % main_qml, file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())