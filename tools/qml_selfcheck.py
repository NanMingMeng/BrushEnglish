"""离屏加载 QML，检查界面有没有语法错误或警告。"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

from appcore import paths
from appcore.controller import AppController


def main():
    real_out = sys.stdout
    app = QGuiApplication(sys.argv)
    qml_dir = paths.qml_dir()
    qmlRegisterSingletonType(QUrl.fromLocalFile(str(qml_dir / "Theme.qml")), "BrushUI", 1, 0, "Theme")
    ctl = AppController()
    sys.stdout = real_out
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir))
    engine.rootContext().setContextProperty("backend", ctl)
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.load(QUrl.fromLocalFile(str(qml_dir / "Main.qml")))

    result = {"root_count": len(engine.rootObjects()), "warnings": warnings[:10]}
    QTimer.singleShot(1500, app.quit)
    app.exec()
    real_out.write(json.dumps(result, ensure_ascii=False))
    real_out.write("\n")
    real_out.flush()
    # 用 os._exit 跳过 Qt/后台线程的析构，避免自检脚本被收尾阶段的异常带成非 0
    os._exit(0 if result["root_count"] == 1 and not result["warnings"] else 1)


if __name__ == "__main__":
    main()
