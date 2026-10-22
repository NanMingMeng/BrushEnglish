# -*- coding: utf-8 -*-
"""控制层（Controller）：界面（QML）和刷单词脚本（引擎）之间唯一的中间人。

白话解释：
界面只管好看和收操作，脚本只管干活，两者不直接对话，全靠这一层传话。
好处是以后想换界面、或者改脚本，都不会互相拖累。

状态机：脚本在某一刻只能处于一种状态，只能按下面这些箭头走：
    未启动 → 启动中 → 运行中 ⇄ 已暂停
                        ↓ 点停止
                     停止中 → 正常结束 / 出错结束 → 回到未启动
"""
from __future__ import annotations

import builtins
import importlib
import importlib.util
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot, Property
from PySide6.QtGui import QGuiApplication

from . import paths, settings
from .logbus import LogBus, _StreamWriter
from .models import CoordListModel, BankListModel


class S:
    """状态常量（界面靠这些判断按钮该不该能点）"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


# 允许的状态跳转：key 是当前状态，value 是可以跳到哪些状态
ALLOWED = {
    S.IDLE:       {S.STARTING},
    S.STARTING:   {S.RUNNING, S.FAILED, S.CANCELLING},
    S.RUNNING:    {S.PAUSED, S.CANCELLING, S.SUCCEEDED, S.FAILED},
    S.PAUSED:     {S.RUNNING, S.CANCELLING, S.FAILED},
    S.CANCELLING: {S.SUCCEEDED, S.FAILED, S.STOPPED},
    S.SUCCEEDED:  {S.IDLE},
    S.FAILED:     {S.IDLE},
    S.STOPPED:    {S.IDLE},
}

STATE_LABELS = {
    S.IDLE: "未启动",
    S.STARTING: "启动中",
    S.RUNNING: "运行中",
    S.PAUSED: "已暂停",
    S.CANCELLING: "正在停止",
    S.SUCCEEDED: "正常结束",
    S.FAILED: "出错结束",
    S.STOPPED: "已停止",
}

# 认字引擎：代号 → (显示名, 默认端口)
ENGINES = {
    "rapid":  ("内置 RapidOCR", 1225),
    "paddle": ("内置 PaddleOCR", 1224),
    "umi":    ("外置 Umi-OCR", 1224),
}
class AppController(QObject):
    """界面和引擎之间的桥梁。

    QML 里通过 backend.xxx() 调用这里标了 @Slot 的方法，
    通过 onXxx 接收这里发出的信号。
    """

    stateChanged = Signal(str)            # 状态变了
    statsChanged = Signal("QVariantMap")  # 统计数字变了
    logLines = Signal(list)               # 来了一批日志
    logCleared = Signal()                 # 日志要清空
    inputRequested = Signal(str)          # 脚本在等人回答
    inputFinished = Signal()              # 回答完了，输入框收起来
    toast = Signal(str)                   # 弹一条提示
    grabPreviewRequested = Signal(str)    # 请求界面生成一张预览图
    ocrStatusChanged = Signal(bool, str)  # 认字引擎状态（通不通, 说明文字）
    asrTestResult = Signal(str)           # 试录识别结果

    def __init__(self, parent=None):
        super().__init__(parent)

        # 打包后先把数据复制到 exe 同级，保证脚本和界面读同一份配置
        paths.ensure_user_files()

        self.bus = LogBus(self)
        self.bus.lines.connect(self._on_log_lines)
        self.bus.cleared.connect(self.logCleared)

        self.engine = None
        self.thread: Optional[threading.Thread] = None
        self.run_started_at = None

        self.input_event = threading.Event()
        self.input_result = [""]
        self.waiting_input = False

        self._recent: list = []
        self._bank_all_rows: list = []

        self._state = S.IDLE
        self._ui = settings.load_ui_settings()

        self.coord_model = CoordListModel(self)
        self.bank_model = BankListModel(self)

        # 把脚本的 print 和 input 接过来
        sys.stdout = _StreamWriter(self.bus)
        sys.stderr = _StreamWriter(self.bus)
        self._real_input = builtins.input
        builtins.input = self.gui_input

        # 每秒刷新一次统计
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_status)
        self._timer.start(1000)

        # 启动后先把坐标和题库读一遍
        QTimer.singleShot(50, self.reload_coordinates)
        QTimer.singleShot(80, self.reload_bank)

        # ---- 认字引擎（OCR）----
        self._ocr_url = "http://127.0.0.1:1224/api/ocr"
        self._ocr_source = ""
        self._ocr_original_url = None
        self._bridge_proc = None
        self._ocr_engine = str(self._ui.get("ocr_engine", "rapid") or "rapid")
        self._ocr_ok = False
        self._ocr_fail_count = 0
        self._ocr_error = ""

        # 上次没正常退出时，config 里可能还指着内置端口，先清回 1224
        self._cleanup_stale_ocr_config()
        # 每 5 秒探测一次认字服务通不通
        self._start_ocr_watch()
        # 自动拉起内置认字引擎（Rapid / Paddle）
        QTimer.singleShot(300, self._launch_ocr_bridge_async)
    # ================= 状态机 =================
    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, new_state: str) -> bool:
        """换状态，只走允许的箭头。要走不允许的就拒绝并返回 False。"""
        if new_state == self._state:
            return True
        if new_state not in ALLOWED.get(self._state, set()):
            return False
        self._state = new_state
        self.stateChanged.emit(new_state)
        return True

    @Slot(result=str)
    def stateName(self) -> str:
        return STATE_LABELS.get(self._state, self._state)

    @Slot(result=bool)
    def canStart(self) -> bool:
        return self._state in (S.IDLE, S.SUCCEEDED, S.FAILED, S.STOPPED)

    @Slot(result=bool)
    def isRunning(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    @Slot(result=bool)
    def isPaused(self) -> bool:
        return self._state == S.PAUSED

    # ================= 运行控制 =================
    @Slot(result=str)
    def start(self) -> str:
        """开始刷单词。返回空字符串表示成功，否则返回出错原因。"""
        if self.thread and self.thread.is_alive():
            return "脚本正在运行"
        if not self.canStart():
            return "当前状态不能启动"

        eng = paths.engine_file()
        if not eng.exists():
            return "没找到脚本文件：%s" % eng

        # 从「跑完了」那类状态先回到未启动，再走启动中
        if self._state in (S.SUCCEEDED, S.FAILED, S.STOPPED):
            self._state = S.IDLE
        if not self._set_state(S.STARTING):
            return "状态不允许启动"

        self.bus.clear()
        self.bus.push("=" * 60)
        self.bus.push("[界面] 正在启动刷单词脚本……")
        self.run_started_at = time.time()
        self.thread = threading.Thread(target=self._run_engine, daemon=True)
        self.thread.start()
        return ""

    @Slot()
    def stop(self) -> None:
        """停止脚本（会先让它把进度存下来）。"""
        if self._state not in (S.RUNNING, S.PAUSED, S.STARTING):
            return
        self._set_state(S.CANCELLING)
        if self.engine is not None:
            try:
                self.engine.stop_flag = True
            except Exception:
                pass
        self.bus.push("[界面] 已发出停止指令，等脚本自己收尾（会保存进度）……")
        if self.waiting_input:
            self.answerInput("q")

    @Slot()
    def pause(self) -> None:
        """暂停 / 继续"""
        if self.engine is None:
            return
        try:
            self.engine.pause_flag = not self.engine.pause_flag
            paused = bool(self.engine.pause_flag)
        except Exception:
            return
        if paused:
            self._set_state(S.PAUSED)
            self.bus.push("[界面] 已暂停（点“继续”恢复）")
        else:
            self._set_state(S.RUNNING)
            self.bus.push("[界面] 已继续")
    # ================= 引擎线程 =================
    def _run_engine(self):
        """在后台线程里跑刷单词脚本（原样保留已跑通的逻辑）。"""
        try:
            # 同一个进程里重跑时，先摘掉上一轮的日志处理器，免得日志翻倍
            try:
                lg = logging.getLogger("brush")
                for h in list(lg.handlers):
                    lg.removeHandler(h)
            except Exception:
                pass

            # 跳过启动时的自动更新检查，避免每次开软件白等网络
            try:
                au = importlib.import_module("auto_updater")
                au.check_and_ask_update = lambda force_check=False: "skip"
            except Exception as e:
                self.bus.push("[界面] 更新开关没挂上（不影响使用）：%s" % e)

            self._set_state(S.RUNNING)

            engine = self._load_engine()
            self.engine = engine
            try:
                engine.DRY_RUN = self.dryRunEnabled()
            except Exception:
                pass
            try:
                engine.save_monitor_state()
            except Exception:
                pass
            engine.main()

            # 跑完要看是自己停的还是被停止的
            if getattr(engine, "stop_flag", False):
                self._set_state(S.STOPPED)
            else:
                self._set_state(S.SUCCEEDED)
        except SystemExit:
            self.bus.push("[界面] 脚本主动退出（多半是触发了自动更新）")
            self._set_state(S.STOPPED)
        except Exception:
            self.bus.push("[界面] 脚本异常退出，详情如下：")
            self.bus.push(traceback.format_exc())
            self._set_state(S.FAILED)
        finally:
            self.bus.flush_now()

    def _load_engine(self):
        """按文件路径把引擎脚本当模块加载（文件名是中文，不能直接 import）。

        模块只加载一次。重复执行 exec_module 会把模块里的语音模型缓存清空，
        导致每次点“开始运行”都要重新加载一次模型（约 20 秒）。
        重跑时只清掉上一轮留下的运行状态，保留已加载的模型。
        """
        module = sys.modules.get("brush_engine")
        if module is None or not hasattr(module, "main"):
            eng = paths.engine_file()
            spec = importlib.util.spec_from_file_location("brush_engine", str(eng))
            if spec is None or spec.loader is None:
                raise RuntimeError("加载不了引擎文件：%s" % eng)
            module = importlib.util.module_from_spec(spec)
            sys.modules["brush_engine"] = module
            spec.loader.exec_module(module)
        else:
            # 复用已加载模块：只重置运行状态，不动模型缓存
            try:
                module.stop_flag = False
                module.pause_flag = False
                module._ocr_consecutive_fail[0] = 0
                module._ocr_in_recovery[0] = False
                module._page_mismatch[0] = False
                module._ocr_recovered_page[0] = None
            except Exception:
                pass
        return module

    # ================= 脚本问答 =================
    def gui_input(self, prompt=""):
        """替代内置 input()：后台线程里等着，界面上弹提示收字。"""
        self.input_event.clear()
        self.input_result[0] = ""
        self.waiting_input = True
        self.inputRequested.emit(str(prompt))
        self.input_event.wait()
        return self.input_result[0]

    @Slot(str)
    def answerInput(self, text: str) -> None:
        """界面把答案送回来，唤醒正在等待的脚本。"""
        self.waiting_input = False
        self.input_result[0] = str(text or "")
        self.inputFinished.emit()
        self.input_event.set()

    # ================= 日志 =================
    def _on_log_lines(self, batch):
        self._recent.extend(batch)
        if len(self._recent) > 2000:
            del self._recent[: len(self._recent) - 2000]
        self.logLines.emit(batch)

    @Slot()
    def clearLog(self) -> None:
        self._recent = []
        self.bus.clear()

    @Slot(result=str)
    def logAsText(self) -> str:
        """把当前日志导出成一段纯文本，方便复制或者存文件。"""
        return "\n".join(
            ("[%s] [%s] %s" % (t, lv, tx)).strip() for (t, lv, tx) in self._recent
        )
    # ================= 统计 =================
    @Slot()
    def refresh_status(self) -> None:
        """每秒读一次脚本写的进度和统计文件，刷新界面上的数字。"""
        prog = settings.read_json(paths.progress_file(), {}) or {}
        stats = settings.read_json(paths.stats_file(), {}) or {}

        running = self.isRunning()
        paused = bool(self.engine and getattr(self.engine, "pause_flag", False))

        # 状态文字沿用老版口径：暂停优先，其次运行，跑过就是已停止
        if running and paused:
            state = "已暂停"
        elif running:
            state = "运行中"
        elif self.run_started_at:
            state = "已停止"
        else:
            state = "未启动"

        runtime = "—"
        if running and self.run_started_at:
            secs = int(time.time() - self.run_started_at)
            runtime = "%02d:%02d:%02d" % (secs // 3600, secs % 3600 // 60, secs % 60)

        payload = {
            "running": running,
            "paused": paused,
            "runtime": runtime,
            "state": state,
            # 组号只认脚本写进进度文件的值（脚本以 App 显示进度为准），
            # 绝不拿本地历史累计组数去推算，不然会冒出跟 App 对不上的数字
            "round": prog.get("round_num"),
            "progress": self._progress_text(prog),
            "words": stats.get("total_words_learned", 0),
            "questions": stats.get("total_questions_answered", 0),
            "accuracy": self._accuracy_text(stats),
        }
        self.statsChanged.emit(payload)

    @staticmethod
    def _progress_text(prog: dict) -> str:
        phase = prog.get("phase")
        if phase == "learning":
            idx = prog.get("learn_local_index")
            return ("%s/30 学习" % idx) if idx else "学习阶段"
        if phase == "testing":
            qn = prog.get("test_current_qn")
            return ("%s/30 考试" % qn) if qn else "考试阶段"
        if phase == "round_start":
            return "准备"
        return "—"

    @staticmethod
    def _accuracy_text(stats: dict) -> str:
        total_q = stats.get("total_questions_answered", 0)
        if not total_q:
            return "—"
        try:
            ratio = stats.get("total_correct_answers", 0) / total_q * 100
        except Exception:
            return "—"
        return "%.1f%%" % ratio
    # ================= 坐标方案 =================
    @Property(QObject, constant=True)
    def coordModel(self):
        return self.coord_model

    def _load_coord_items(self):
        """从 coordinate_profiles.py 里读坐标项清单（和脚本内部用的是同一份，不会走偏）。"""
        p = paths.coord_module_file()
        spec = importlib.util.spec_from_file_location("brush_coord_defs", str(p))
        if spec is None or spec.loader is None:
            raise RuntimeError("加载不了坐标模块：%s" % p)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return list(getattr(module, "COORD_ITEMS", []))

    @Slot()
    def reload_coordinates(self) -> None:
        """把坐标项清单和当前数值读出来，填进界面。"""
        try:
            items = self._load_coord_items()
            if not items:
                self.bus.push("[界面] 坐标项清单是空的")
                return

            cfg = settings.read_json(paths.config_file(), {}) or {}
            regions = cfg.get("regions", {}) if isinstance(cfg, dict) else {}

            rows = []
            for item in items:
                cur = settings.get_by_path(regions, item.get("path", []), None)
                if cur is None:
                    cur = item.get("default", [])
                rows.append({
                    "key": item.get("key", ""),
                    "name": item.get("name", item.get("key", "?")),
                    "value": settings.fmt_nums(cur),
                    "desc": item.get("desc", ""),
                })

            self.coord_model.load(rows)
            self.bus.push("[界面] 已读取 %d 个坐标项" % len(rows))
        except Exception as e:
            self.bus.push("[界面] 坐标项读取失败：%s" % e)

    @Slot(int, str)
    def setCoordValue(self, index: int, text: str) -> None:
        """界面改了某个坐标值，先记在模型里。"""
        try:
            self.coord_model.set_value(int(index), text)
        except Exception:
            pass

    @Slot(result=str)
    def save_coordinates(self) -> str:
        """把界面上填的坐标写回 config.json。返回空字符串表示成功。"""
        try:
            items = self._load_coord_items()
            if not items:
                return "坐标项还没读出来"

            cfg = settings.read_json(paths.config_file(), None)
            if not isinstance(cfg, dict):
                return "读不到配置：%s" % paths.config_file()

            # 先全部解析，任何一个填错就整体不保存，免得写进去一半坏数据
            parsed = []
            for item, row in zip(items, self.coord_model.rows()):
                try:
                    parsed.append((item, settings.parse_nums(row.get("value", ""))))
                except Exception:
                    return "「%s」填的不是数字：%s" % (
                        item.get("name", "?"), row.get("value", ""))

            # 备份一份原配置（只在第一次备份，保住最原始的那份）
            try:
                cfg_bak = paths.config_file().with_suffix(".json.bak")
                if not cfg_bak.exists():
                    shutil.copy2(paths.config_file(), cfg_bak)
            except Exception:
                pass

            regions = cfg.setdefault("regions", {})
            for item, vals in parsed:
                settings.set_by_path(regions, item.get("path", []), vals)

            ok = settings.write_json(paths.config_file(), cfg)
            if not ok:
                return "坐标保存失败"
            return ""
        except Exception as e:
            return "坐标保存出错：%s" % e
    # ================= 题库 =================
    @Property(QObject, constant=True)
    def bankModel(self):
        return self.bank_model

    def _current_bank_path(self):
        """当前用的是哪本题库：先看「当前词典.txt」，没有就取题库文件夹里第一本。"""
        try:
            cur = paths.resource_root() / "当前词典.txt"
            name = ""
            if cur.exists():
                name = (cur.read_text(encoding="utf-8") or "").strip()

            bank_dir = paths.bank_dir()
            if bank_dir.exists():
                files = sorted(bank_dir.glob("题库_*.json"))
                if name:
                    for f in files:
                        if f.stem[len("题库_"):] == name:
                            return name, f
                if files:
                    return files[0].stem[len("题库_"):], files[0]
            return "", None
        except Exception:
            return "", None

    @Slot()
    def reload_bank(self) -> None:
        """把题库里的单词读进界面。"""
        try:
            name, path = self._current_bank_path()
            if not path or not path.exists():
                self.bank_model.clear()
                self.bus.push("[界面] 还没找到题库文件")
                return

            bank = settings.read_json(path, None)
            words = (bank or {}).get("words", []) if isinstance(bank, dict) else []

            rows = []
            for i, w in enumerate(words, start=1):
                if isinstance(w, dict):
                    rows.append({
                        "no": i,
                        "word": str(w.get("word", "")),
                        "meaning": str(w.get("meaning", "") or w.get("definition", "")),
                        "confirmed": bool(w.get("confirmed", False)),
                    })
                else:
                    rows.append({"no": i, "word": str(w), "meaning": "",
                                 "confirmed": False})

            self._bank_all_rows = rows
            self.bank_model.load(rows)
            self.bus.push("[界面] 题库「%s」共 %d 词" % (name, len(rows)))
        except Exception as e:
            self.bus.push("[界面] 题库读取失败：%s" % e)

    @Slot(str)
    def filterBank(self, text: str) -> None:
        """按关键字筛选题库（空白就全部显示）。"""
        try:
            key = (text or "").strip().lower()
            if not key:
                self.bank_model.load(self._bank_all_rows)
                return
            hit = [r for r in self._bank_all_rows
                   if key in str(r.get("word", "")).lower()
                   or key in str(r.get("meaning", "")).lower()]
            self.bank_model.load(hit)
        except Exception:
            pass

    @Slot()
    def openBankFolder(self) -> None:
        """打开题库所在的文件夹。"""
        try:
            os.startfile(str(paths.bank_dir()))
        except Exception as e:
            self.bus.push("[界面] 打不开题库文件夹：%s" % e)
    # ================= 窗口设置（记住上次的位置和大小） =================
    @Slot(result="QVariantMap")
    def uiSettings(self):
        return dict(self._ui)

    @Slot(int, int, int, int)
    def saveWindowGeometry(self, x, y, w, h) -> None:
        """记住窗口现在的位置和大小，下次打开照着摆。"""
        try:
            self._ui["x"] = int(x)
            self._ui["y"] = int(y)
            self._ui["w"] = int(w)
            self._ui["h"] = int(h)
            settings.save_ui_settings(self._ui)
        except Exception:
            pass

    @Slot(str, str)
    def savePreference(self, key: str, value: str) -> None:
        """记住一个偏好（主题、布局、认字引擎、拼写题答案来源等）。"""
        try:
            self._ui[str(key)] = value
            settings.save_ui_settings(self._ui)
        except Exception:
            pass

    @Slot(str)
    def setTopMost(self, on: str) -> None:
        """窗口置顶开关。"""
        try:
            self._ui["top"] = str(on).lower() in ("1", "true", "yes", "on")
            settings.save_ui_settings(self._ui)
        except Exception:
            pass

    @Slot(str)
    def copyText(self, text: str) -> None:
        """把一段文字放进剪贴板。"""
        try:
            app = QGuiApplication.instance()
            if app is not None:
                app.clipboard().setText(str(text or ""))
                self.toast.emit("已复制到剪贴板")
        except Exception as e:
            self.toast.emit("复制失败：%s" % e)

    @Slot(str)
    def openPath(self, path: str) -> None:
        """用系统默认方式打开一个文件或文件夹。"""
        try:
            os.startfile(str(path))
        except Exception as e:
            self.toast.emit("打不开：%s" % e)

    @Slot(result="QVariantMap")
    def windowGeometry(self):
        """返回上次记住的窗口位置和大小（已做防跑偏校正）。

        为什么要校正：如果上次关窗口时的位置，在这台机器上已经跑到屏幕外了
        （换过显示器、拔过外接屏、改过缩放），直接照搬就再也找不着窗口了。
        """
        try:
            x = int(self._ui.get("x", 120))
            y = int(self._ui.get("y", 90))
            w = int(self._ui.get("w", 1180))
            h = int(self._ui.get("h", 760))
        except Exception:
            return {"x": 120, "y": 90, "w": 1180, "h": 760}

        # 不小于窗口能缩到的最小值
        w = max(720, w)
        h = max(520, h)

        app = QGuiApplication.instance()
        avail = None
        try:
            scr = app.primaryScreen() if app is not None else None
            if scr is not None:
                avail = scr.availableGeometry()
        except Exception:
            avail = None

        if avail is not None:
            # 不能超过屏幕大小
            w = min(w, max(720, avail.width()))
            h = min(h, max(520, avail.height()))
            # 保证右下角留一截在屏幕里，不至于整个窗口飘出去
            if x > avail.right() - 80:
                x = max(avail.left(), avail.right() - w)
            if y > avail.bottom() - 80:
                y = max(avail.top(), avail.bottom() - h)
            # 左上角也不能太靠外
            if x < avail.left() - 40:
                x = avail.left()
            if y < avail.top() - 40:
                y = avail.top()

        return {"x": x, "y": y, "w": w, "h": h}

    # ================= 认字引擎（OCR）连通探测 =================
    @Slot(str, result=bool)
    def probeOcr(self, engine: str) -> bool:
        """探测某个认字引擎的本机端口通不通。"""
        key = str(engine or "rapid").lower()
        if key not in ENGINES:
            return False
        return self._port_open(ENGINES[key][1])

    @staticmethod
    def _port_open(port: int, timeout: float = 1.5) -> bool:
        """试试本机的某个端口能不能连上（只是握手，不发数据）。"""
        s = None
        try:
            s = socket.socket()
            s.settimeout(timeout)
            s.connect(("127.0.0.1", int(port)))
            return True
        except Exception:
            return False
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
    # ================= 认字引擎（OCR）：自动拉起与状态监视 =================
    def _launch_ocr_bridge_async(self):
        """在后台线程里拉起内置认字引擎，别挡住界面启动。"""
        threading.Thread(target=self._start_ocr_bridge, daemon=True).start()

    def _start_ocr_watch(self):
        """起一个后台线程，每 5 秒探一次认字服务通不通。"""
        cfg = settings.read_json(paths.config_file(), None)
        url = "http://127.0.0.1:1224/api/ocr"
        if isinstance(cfg, dict):
            url = cfg.get("umi_ocr", {}).get("url", url) or url
        self._ocr_url = url
        threading.Thread(target=self._ocr_watch_loop, daemon=True).start()

    def _ocr_watch_loop(self):
        """循环探测，结果通过信号告诉界面。"""
        while True:
            ok = self._url_alive(self._ocr_url, 2)
            if ok:
                self._ocr_fail_count = 0
            else:
                self._ocr_fail_count += 1

            # 防抖：单次探测失败不算数（引擎忙的时候会抖一下），
            # 连续 2 次（约 10 秒）都不通才对外报「断了」。
            if ok or self._ocr_fail_count >= 2:
                self._ocr_ok = bool(ok)
                try:
                    self.ocrStatusChanged.emit(bool(ok), self._ocr_source or "内置")
                except RuntimeError:
                    return
            time.sleep(5)

    @staticmethod
    def _url_alive(url: str, timeout: float = 1.5) -> bool:
        """对一个 OCR 地址发一个空的 POST，能连上就算通。"""
        import urllib.request
        try:
            req = urllib.request.Request(url, method="POST")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception:
            return False

    def _start_ocr_bridge(self):
        """启动内置认字引擎（Rapid 或 Paddle）。

        先清一遍上次遗留的孤儿进程，避免端口被占满；
        然后在 1225~1239 里挑一个空闲端口，把引擎挂上去。
        """
        self._kill_orphan_engines()
        if self._bridge_proc is not None and self._bridge_proc.poll() is None:
            return

        engine = str(self._ocr_engine or "rapid")
        ocr_dir = paths.resource_root() / "内置OCR"
        bridge = ocr_dir / "ocr_bridge.py"
        bridge_exe = ocr_dir / "ocr_bridge.exe"
        if not (bridge.exists() or bridge_exe.exists()):
            self._ocr_source = "引擎缺失"
            self.ocrStatusChanged.emit(False, self._ocr_source)
            return

        port = self._pick_bridge_port()
        if port is None:
            self._ocr_source = "端口占满"
            self.ocrStatusChanged.emit(False, self._ocr_source)
            return

        try:
            if paths.is_frozen() and bridge_exe.exists():
                cmd = [str(bridge_exe), engine, "--port", str(port)]
            else:
                cmd = [sys.executable, str(bridge), engine, "--port", str(port)]
            env = os.environ.copy()
            env["OCR_BRIDGE_HOME"] = str(ocr_dir)
            self._bridge_proc = subprocess.Popen(
                cmd, cwd=str(ocr_dir), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._bridge_proc = None
            self._ocr_error = traceback.format_exc()
            self._ocr_source = "启动失败"
            self.ocrStatusChanged.emit(False, self._ocr_source)
            return

        self._ocr_source = "启动中"
        self.ocrStatusChanged.emit(False, self._ocr_source)
        self._wait_bridge_ready(engine, port)

    def _wait_bridge_ready(self, engine: str, port: int):
        """等内置引擎就绪（最多等 150 秒），就绪后把 config 指过去。"""
        url = "http://127.0.0.1:%d/api/ocr" % port
        for _ in range(150):
            time.sleep(1)
            if self._url_alive(url, 2):
                self._ocr_url = url
                self._point_config_to(url)
                self._ocr_source = "Paddle" if engine == "paddle" else "Rapid"
                self._ocr_ok = True
                self.ocrStatusChanged.emit(True, self._ocr_source)
                return
            # 进程被外部停掉或自己退了，立刻结束等待，别空转 150 秒
            if self._bridge_proc is None or self._bridge_proc.poll() is not None:
                break

        self._kill_bridge_proc()
        # 内置起不来就退回外部：1224 上如果有 Umi-OCR 还能接着用
        base = self._default_ocr_url()
        if self._url_alive(base, 2):
            self._ocr_url = base
            self._ocr_source = "外部"
            self._ocr_ok = True
            self.ocrStatusChanged.emit(True, self._ocr_source)
        else:
            self._ocr_source = "启动失败"
            self._ocr_ok = False
            self.ocrStatusChanged.emit(False, self._ocr_source)

    @staticmethod
    def _default_ocr_url() -> str:
        return "http://127.0.0.1:1224/api/ocr"

    @Slot(result=str)
    def engine_ready_text(self) -> str:
        """返回当前能用的认字引擎说明；还没就绪返回空字符串。"""
        src = str(self._ocr_source or "")
        bad = ("启动中", "启动失败", "引擎缺失", "端口占满")
        if self._bridge_proc is not None and src and src not in bad:
            return "内置 %s（%s）" % (src, self._ocr_url or "")
        base = self._default_ocr_url()
        if self._url_alive(base, 2):
            return "外部 Umi-OCR（%s）" % base
        return ""

    @staticmethod
    def _pick_bridge_port():
        """在 1225~1239 里挑一个没被占用的端口。"""
        import socket as _socket
        for p in range(1225, 1240):
            s = _socket.socket()
            try:
                s.bind(("127.0.0.1", p))
                return p
            except Exception:
                continue
            finally:
                s.close()
        return None
    def _point_config_to(self, url: str):
        """把刷词脚本用的认字地址指到内置引擎；退出时会自动还原。"""
        cfg = settings.read_json(paths.config_file(), None)
        if not isinstance(cfg, dict):
            return
        cur = str(cfg.get("umi_ocr", {}).get("url", ""))
        if cur == url:
            return
        if self._ocr_original_url is None:
            self._ocr_original_url = cur or self._default_ocr_url()
        cfg.setdefault("umi_ocr", {})["url"] = url
        settings.write_json(paths.config_file(), cfg)

    def _restore_ocr_config(self):
        """退出时把 config.json 里的认字地址还原成原来的值。"""
        orig = self._ocr_original_url
        if not orig:
            return
        cfg = settings.read_json(paths.config_file(), None)
        if isinstance(cfg, dict):
            if str(cfg.get("umi_ocr", {}).get("url", "")) != orig:
                cfg.setdefault("umi_ocr", {})["url"] = orig
                settings.write_json(paths.config_file(), cfg)
        self._ocr_original_url = None

    def _cleanup_stale_ocr_config(self):
        """上次没正常退出时，config 可能还指着内置端口（1225+），开窗口先还原成 1224。"""
        import re
        cfg = settings.read_json(paths.config_file(), None)
        if not isinstance(cfg, dict):
            return
        url = str(cfg.get("umi_ocr", {}).get("url", ""))
        m = re.search(r":(\d{2,5})/", url)
        if m and int(m.group(1)) >= 1225:
            cfg.setdefault("umi_ocr", {})["url"] = self._default_ocr_url()
            settings.write_json(paths.config_file(), cfg)

    def _kill_orphan_engines(self):
        """只收父进程已经没了的孤儿引擎进程；外部 Umi-OCR 正在用的不动。"""
        ps = ("Get-CimInstance Win32_Process | Where-Object {"
              " ($_.Name -eq 'PaddleOCR-json.exe' -or $_.Name -eq 'RapidOCR-json.exe'"
              " -or ($_.Name -like 'python*' -and $_.CommandLine -like '*ocr_bridge.py*'))"
              " -and -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue) }"
              " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
        except Exception:
            pass

    def _kill_bridge_proc(self):
        """启动失败或超时时，必须把认字服务杀掉，否则它会一直占着端口。"""
        p = self._bridge_proc
        if p is not None and p.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                )
            except Exception:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    pass
        self._bridge_proc = None

    def _stop_ocr_bridge(self):
        """停掉内置引擎，并清掉可能残留的孤儿进程。"""
        p = self._bridge_proc
        if p is not None and p.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                )
            except Exception:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    pass
            try:
                p.wait(timeout=5)
            except Exception:
                pass
        self._bridge_proc = None
        self._kill_orphan_engines()
        self._restore_ocr_config()

    def _force_kill_ocr_engines(self):
        """强制结束所有内置认字引擎进程（包括父进程还在的卡死进程）。"""
        ps = ("Get-CimInstance Win32_Process | Where-Object {"
              " ($_.Name -eq 'PaddleOCR-json.exe' -or $_.Name -eq 'RapidOCR-json.exe'"
              " -or ($_.Name -like 'python*' -and $_.CommandLine -like '*ocr_bridge.py*'))"
              " } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
        except Exception:
            pass

    @Slot()
    def restartOcrEngine(self) -> None:
        """强制结束卡死的认字引擎进程，并重新启动当前选择的引擎。"""
        try:
            if str(self._ocr_engine) == "umi":
                ok = self._url_alive(self._default_ocr_url(), 2)
                self._ocr_ok = ok
                self._ocr_source = "外部" if ok else "外部未连接"
                self.ocrStatusChanged.emit(ok, self._ocr_source)
                self.toast.emit("外部 Umi-OCR 已连接" if ok else "外部 Umi-OCR 未启动（端口 1224）")
                return

            self.toast.emit("已强制结束认字引擎，正在重新启动...")
            self._force_kill_ocr_engines()
            self._bridge_proc = None
            self._ocr_ok = False
            self._ocr_source = "重启中"
            self.ocrStatusChanged.emit(False, self._ocr_source)
            self._launch_ocr_bridge_async()
        except Exception as e:
            self._ocr_source = "重启失败"
            self._ocr_ok = False
            self.ocrStatusChanged.emit(False, self._ocr_source)
            self.toast.emit("重启认字引擎失败：%s" % e)

    @Slot(str)
    def setOcrEngine(self, engine: str) -> None:
        """切换认字引擎（rapid / paddle / umi）。"""
        key = str(engine or "rapid").lower()
        if key not in ENGINES:
            key = "rapid"
        self._ocr_engine = key
        try:
            self._ui["ocr_engine"] = key
            settings.save_ui_settings(self._ui)
        except Exception:
            pass
        self._stop_ocr_bridge()
        self._ocr_source = "启动中"
        self.ocrStatusChanged.emit(False, self._ocr_source)
        self._launch_ocr_bridge_async()

    @Slot(result=str)
    def ocrEngine(self) -> str:
        """当前选的是哪个认字引擎。"""
        return str(self._ocr_engine or "rapid")

    @Slot(str, result=bool)
    def probeOcr(self, engine: str) -> bool:
        """探测某个认字引擎的本机端口通不通。"""
        key = str(engine or "rapid").lower()
        if key not in ENGINES:
            return False
        return self._port_open(ENGINES[key][1])

    @staticmethod
    def _port_open(port: int, timeout: float = 1.5) -> bool:
        """试试本机的某个端口能不能连上（只是握手，不发数据）。"""
        s = None
        try:
            s = socket.socket()
            s.settimeout(timeout)
            s.connect(("127.0.0.1", int(port)))
            return True
        except Exception:
            return False
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    @Slot()
    def shutdown(self) -> None:
        """关窗口时收尾：停掉认字引擎、还原配置。"""
        try:
            self._stop_ocr_bridge()
        except Exception:
            pass
    # ================= 给 QML 用的驼峰别名 =================
    # QML 的写法习惯是 reloadBank 这种驼峰，Python 这边是 reload_bank。
    # 加一层别名，省得两边来回改。
    @Slot()
    def reloadCoordinates(self) -> None:
        self.reload_coordinates()

    @Slot(result=str)
    def saveCoordinates(self) -> str:
        return self.save_coordinates()

    @Slot()
    def reloadBank(self) -> None:
        self.reload_bank()

    # ================= 拼写题答案来源 =================
    @Slot(str)
    def setSpellingSource(self, source: str) -> None:
        """切换拼写题答案来源：asr（听音识别）/ wordlist（按词表顺序）。"""
        val = str(source or "asr").lower()
        if val not in ("asr", "wordlist"):
            val = "asr"
        try:
            cfg = settings.read_json(paths.config_file(), {}) or {}
            cfg["spelling_source"] = val
            settings.write_json(paths.config_file(), cfg)
            self._ui["spelling_source"] = val
            settings.save_ui_settings(self._ui)
            # 引擎已经加载过时，直接改它内存里的开关，立刻生效
            if self.engine is not None:
                try:
                    self.engine.SPELLING_SOURCE = val
                except Exception:
                    pass
            self.toast.emit("听音识别已" + ("开启" if val == "asr" else "关闭"))
        except Exception as e:
            self.toast.emit("保存拼写题来源失败：%s" % e)

    @Slot(result=str)
    def spellingSource(self) -> str:
        """当前拼写题答案来源。"""
        try:
            cfg = settings.read_json(paths.config_file(), {}) or {}
            val = str(cfg.get("spelling_source", "asr")).lower()
            return val if val in ("asr", "wordlist") else "asr"
        except Exception:
            return "asr"

    # ================= 随机休息开关 =================
    @Slot(str)
    def setRandomBreak(self, on: str) -> None:
        """随机休息开关：关掉后脚本不再中途模拟走神休息。"""
        try:
            flag = str(on).lower() in ("1", "true", "yes", "on")
            cfg = settings.read_json(paths.config_file(), {}) or {}
            anti = cfg.setdefault("anti_detect", {})
            rb = anti.setdefault("random_break", {})
            rb["enabled"] = flag
            settings.write_json(paths.config_file(), cfg)
            # 引擎已经加载过时，直接改它内存里的开关，立刻生效
            if self.engine is not None:
                try:
                    self.engine.RANDOM_BREAK_ENABLED = flag
                except Exception:
                    pass
            self.toast.emit("随机休息已" + ("开启" if flag else "关闭"))
        except Exception as e:
            self.toast.emit("保存随机休息设置失败：%s" % e)

    # ================= 干跑开关 =================
    @Slot(str)
    def setDryRun(self, on: str) -> None:
        """干跑开关：只识别、不点击、不输入。"""
        try:
            flag = str(on).lower() in ("1", "true", "yes", "on")
            cfg = settings.read_json(paths.config_file(), {}) or {}
            cfg["dry_run"] = flag
            settings.write_json(paths.config_file(), cfg)
            if self.engine is not None:
                try:
                    self.engine.DRY_RUN = flag
                except Exception:
                    pass
            self.toast.emit("干跑模式已" + ("开启（只识别不点击）" if flag else "关闭"))
        except Exception as e:
            self.toast.emit("保存干跑设置失败：%s" % e)

    @Slot(result=bool)
    def dryRunEnabled(self) -> bool:
        """当前干跑开关状态。"""
        try:
            cfg = settings.read_json(paths.config_file(), {}) or {}
            return bool(cfg.get("dry_run", False))
        except Exception:
            return False

    @Slot(result=bool)
    def randomBreakEnabled(self) -> bool:
        """当前随机休息开关状态。"""
        try:
            cfg = settings.read_json(paths.config_file(), {}) or {}
            rb = (cfg.get("anti_detect") or {}).get("random_break") or {}
            return bool(rb.get("enabled", True))
        except Exception:
            return True

    # ================= 坐标方案管理 =================
    def _load_coord_profile_module(self):
        """加载 coordinate_profiles 模块（和引擎用同一份，方案目录才不会错位）。"""
        p = paths.coord_module_file()
        spec = importlib.util.spec_from_file_location("brush_coord_profiles", str(p))
        if spec is None or spec.loader is None:
            raise RuntimeError("加载不了坐标方案模块：%s" % p)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @Slot(result="QVariantList")
    def profileList(self):
        """列出所有已保存的坐标方案。"""
        try:
            m = self._load_coord_profile_module()
            return [{"name": str(x.get("name", ""))} for x in m.list_profiles()]
        except Exception as e:
            self.bus.push("[界面] 读取坐标方案列表失败：%s" % e)
            return []

    @Slot(result=str)
    def currentProfile(self):
        """当前选中的坐标方案名。"""
        try:
            return str(self._load_coord_profile_module().get_current_profile() or "")
        except Exception:
            return ""

    @Slot(str, result=str)
    def switchProfile(self, name: str):
        """切换坐标方案：把方案里的坐标写进 config.json。返回空字符串表示成功。"""
        try:
            name = (name or "").strip()
            if not name:
                return "方案名为空"
            m = self._load_coord_profile_module()
            data = m.load_profile(name)
            if not data:
                return "找不到方案：%s" % name
            regions = data.get("regions", {}) or {}

            cfg_path = paths.config_file()
            # 改配置前先备份一份
            try:
                import shutil as _sh
                bak = cfg_path.with_suffix(".json.bak")
                if cfg_path.exists() and not bak.exists():
                    _sh.copy2(cfg_path, bak)
            except Exception:
                pass

            cfg = settings.read_json(cfg_path, {}) or {}
            cfg["regions"] = regions
            if not settings.write_json(cfg_path, cfg):
                return "写入配置失败"

            m.set_current_profile(name)
            self.reload_coordinates()
            self.bus.push("[界面] 已切换到坐标方案：%s" % name)
            return ""
        except Exception as e:
            return "切换失败：%s" % e

    @Slot(str, result=str)
    def saveProfileAs(self, name: str):
        """把当前坐标页上的值保存为新方案。返回空字符串表示成功。"""
        try:
            name = (name or "").strip()
            if not name:
                return "方案名不能为空"

            items = self._load_coord_items()
            if not items:
                return "坐标项还没读出来"

            # 从现有 config 的 regions 深拷贝一份再覆盖，保证嵌套结构正确
            import copy as _copy
            cfg = settings.read_json(paths.config_file(), {}) or {}
            regions = _copy.deepcopy(cfg.get("regions", {}) or {})
            for item, row in zip(items, self.coord_model.rows()):
                vals = settings.parse_nums(row.get("value", ""))
                settings.set_by_path(regions, item.get("path", []), vals)

            m = self._load_coord_profile_module()
            if not m.save_profile(name, regions):
                return "保存方案失败"
            m.set_current_profile(name)
            self.bus.push("[界面] 已保存坐标方案：%s" % name)
            return ""
        except Exception as e:
            return "保存失败：%s" % e

    @Slot(str, result=str)
    def deleteProfile(self, name: str):
        """删除一个坐标方案。"""
        try:
            name = (name or "").strip()
            if not name:
                return "方案名为空"
            m = self._load_coord_profile_module()
            p = m.get_profile_path(name)
            if p.exists():
                p.unlink()
            return ""
        except Exception as e:
            return "删除失败：%s" % e
    # ================= 试录识别（ASR 设备选择 + 3 秒测试） =================
    def _engine_for_asr(self):
        """拿一个可用的引擎对象；没有就先加载。"""
        if self.engine is not None:
            return self.engine
        self.engine = self._load_engine()
        return self.engine

    @Slot(result=str)
    def asrStatus(self):
        """听音功能状态文字。"""
        try:
            eng = self._engine_for_asr()
            return str(eng.asr_status_text())
        except Exception as e:
            return "未知（%s）" % e

    @Slot(result="QVariantList")
    def asrDevices(self):
        """列出能录到电脑内部声音的设备。"""
        try:
            eng = self._engine_for_asr()
            items = eng.list_loopback_mics() or []
            out = []
            for m in items:
                out.append({
                    "name": str(m.get("name", "")),
                    "loopback": bool(m.get("loopback", False)),
                })
            return out
        except Exception as e:
            self.bus.push("[界面] 列举录音设备失败：%s" % e)
            return []

    @Slot(str)
    def asrTest(self, device_name: str) -> None:
        """录 3 秒并识别，结果通过 asrTestResult 信号返回（后台线程，不卡界面）。"""
        def work():
            try:
                eng = self._engine_for_asr()
                text = eng.asr_listen(seconds=3.0, device_name=(device_name or None))
                self.asrTestResult.emit(str(text or ""))
            except Exception as e:
                self.asrTestResult.emit("试录失败：%s" % e)

        self.bus.push("[试录] 开始录 3 秒，请让 App 读一个单词……")
        threading.Thread(target=work, daemon=True).start()