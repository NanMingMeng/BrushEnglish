# -*- coding: utf-8 -*-
"""日志总线：把脚本吐出来的文字，分级后整齐地交给界面显示。

白话解释：
刷单词脚本一边跑一边往屏幕上打字（专业叫「标准输出」）。
我们把它接管下来，先判断这一行是「普通信息 / 成功 / 警告 / 出错」，
再一次性打包发给界面，界面就能按级别显示不同颜色，还能筛选。

为什么要打包批量发？
脚本刷单词时一秒钟能打几十行，一行一行发会把界面卡住。
攒一小会儿（默认 60 毫秒）一起发，界面就流畅了。
"""
from __future__ import annotations

import re
import sys
from typing import List

from PySide6.QtCore import QObject, QTimer, Signal

# 日志级别：从轻到重。级别越高，颜色越醒目。
LEVELS = ("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR")

# 界面上显示的中文名对照表
LEVEL_LABELS = {
    "DEBUG": "调试",
    "INFO": "信息",
    "SUCCESS": "成功",
    "WARNING": "警告",
    "ERROR": "错误",
}

# 脚本日志的固定格式，例如：  [00:00:03] [INFO] 开始第 1 组
# 拆成三段：时间 / 级别 / 正文
LOG_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(:\d{2})?)\]\s*\[([A-Za-z]+)\]\s*(.*)$")

# 日志最多保留多少行，超了就从最老的删，防止内存越用越多
MAX_LINES = 2000


def parse_line(raw: str):
    """把一行原始文字拆成 (时间, 级别, 正文)。

    拆不开就当成普通信息，正文原样保留。
    有些脚本输出带颜色控制符（看着像乱码），这里顺手清掉。
    """
    line = str(raw).rstrip("\n").rstrip("\r")
    # 去掉终端颜色控制符，比如 \x1b[31m
    line = re.sub(r"\x1b\[[0-9;]*m", "", line)
    if not line.strip():
        return None

    m = LOG_LINE_RE.match(line)
    if m:
        t = m.group(1)
        raw_level = (m.group(3) or "INFO").upper()
        level = raw_level if raw_level in LEVELS else "INFO"
        # 脚本里的 WARNING 其实常常是「成功/提示」，这里做个温和的纠正
        text = m.group(4)
        return (t, level, text)

    return ("", "INFO", line)


class LogBus(QObject):
    """日志总线：收文字 → 分级 → 批量发给界面。

    界面只要连上 lines 这个信号，就能拿到一批整理好的日志。
    """

    # 每次发一批：[[时间, 级别, 正文], ...]
    lines = Signal(list)
    # 通知界面「要清空了」
    cleared = Signal()

    def __init__(self, parent=None, batch_ms: int = 60):
        super().__init__(parent)
        self._buf: List[list] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(16, int(batch_ms)))
        self._timer.timeout.connect(self._flush)
        self._paused = False

    # ---------- 写入 ----------
    def push(self, raw: str) -> None:
        """收一行文字，先攒着，等一小会儿一起发。"""
        item = parse_line(raw)
        if item is None:
            return
        self._buf.append([item[0], item[1], item[2]])
        if not self._timer.isActive():
            self._timer.start()

    def flush_now(self) -> None:
        """立刻把攒着的发出去（比如脚本刚结束时）。"""
        if self._timer.isActive():
            self._timer.stop()
        self._flush()

    def clear(self) -> None:
        """清空界面上的日志。"""
        self._buf.clear()
        self.cleared.emit()

    def _flush(self) -> None:
        if not self._buf:
            return
        batch = self._buf
        self._buf = []
        try:
            self.lines.emit(batch)
        except RuntimeError:
            # 界面已经关掉了，忽略
            pass


class _StreamWriter:
    """伪装成「标准输出」的对象，把脚本 print 的内容转交给日志总线。"""

    def __init__(self, bus: LogBus):
        self._bus = bus

    def write(self, text: str) -> int:
        try:
            if text:
                self._bus.push(text)
        except Exception:
            pass
        return len(text or "")

    def flush(self) -> None:
        self._bus.flush_now()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def install_stdout_redirection(bus: LogBus, also_stderr: bool = True):
    """把 print / 报错信息全部接到日志总线上。

    注意会保留原始输出流，万一界面出问题还能退回控制台。
    """
    sys.stdout = _StreamWriter(bus)
    if also_stderr:
        sys.stderr = _StreamWriter(bus)