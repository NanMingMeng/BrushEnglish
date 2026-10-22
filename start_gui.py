import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "启动错误.log")

try:
    target = os.path.join(HERE, "刷单词助手.py")
    subprocess.Popen([sys.executable, target], cwd=HERE)
except Exception as exc:
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("启动失败：%r\n" % (exc,))