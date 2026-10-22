# -*- coding: utf-8 -*-
"""路径治理：把「程序自带的只读零件」和「用户用出来的可写数据」分开。

白话解释：
- 只读资源 = 软件自带的东西，比如刷单词脚本、认字引擎程序、模型文件。
  打包之后这些东西躺在程序内部目录里，不应该被改写。
- 可写数据 = 你用软件产生的东西，比如配置、统计、日志、坐标方案。
  这些必须放在「程序关掉之后还在、而且有权限写」的地方。

为什么要分开？
因为如果打包后把数据写进临时解压目录，程序一退出那个目录就被删掉，
你的统计和坐标方案全没了。分开就能避免这种丢数据的情况。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 程序在 Windows 开始菜单 / 应用列表里显示的名字
APP_NAME = "刷单词助手"


def is_frozen() -> bool:
    """判断现在是在「跑源码」还是「跑打包好的 exe」。"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """程序根目录：源码模式=项目目录，打包模式=exe 所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """只读资源根目录。

    打包后 PyInstaller 会把附带的文件解压到一个内部临时目录
    （代码里叫 _MEIPASS），自带的零件都从这儿读。
    """
    if is_frozen():
        return Path(str(getattr(sys, "_MEIPASS", str(app_root()))))
    return app_root()


def user_data_root() -> Path:
    """可写数据根目录。

    统一用 exe 同级（便携模式）：
    刷单词引擎的 BASE_DIR 也是 exe 同级，两边必须指向同一处，
    否则会出现「界面把 OCR 地址改成 1225、脚本却还读 1224」的问题。

    代价：程序要放在有写权限的目录（比如桌面、D 盘），
    不要装进 Program Files 这种需要管理员权限的地方。
    """
    return app_root()


def first_existing(*candidates: Path) -> Path:
    """在一串候选路径里挑第一个真实存在的（打包/源码两种布局都能兼容）。"""
    for c in candidates:
        try:
            if c and Path(c).exists():
                return Path(c)
        except Exception:
            continue
    return Path(candidates[0])


# ---------------- 具体文件 ----------------
_UI_SETTINGS_NAME = "助手窗口设置.json"


def engine_file() -> Path:
    return first_existing(
        resource_root() / "完整脚本_学习测试循环.py",
        app_root() / "完整脚本_学习测试循环.py",
    )


def coord_module_file() -> Path:
    # 优先用 exe 同级那份：引擎的 BASE_DIR 也是 exe 同级，
    # 这样方案目录（coordinate_profiles/）和 current_profile.json 两边才会一致。
    return first_existing(
        app_root() / "coordinate_profiles.py",
        resource_root() / "coordinate_profiles.py",
    )


def config_file() -> Path:
    return first_existing(
        user_data_root() / "config.json",
        resource_root() / "config.json",
        app_root() / "config.json",
    )


def ui_settings_file() -> Path:
    return user_data_root() / _UI_SETTINGS_NAME


def qml_dir() -> Path:
    return first_existing(
        resource_root() / "qml",
        app_root() / "qml",
    )

def progress_file() -> Path:
    """脚本写的当前进度文件"""
    return user_data_root() / "progress.json"


def stats_file() -> Path:
    """历史累计统计文件"""
    return user_data_root() / "stats.json"


def monitor_state_file() -> Path:
    """监管模式状态文件"""
    return user_data_root() / "monitor_state.json"


def bank_dir() -> Path:
    """题库文件夹"""
    return first_existing(
        user_data_root() / "题库",
        resource_root() / "题库",
    )
def ensure_user_files() -> None:
    """打包后把 _internal 里的可写数据复制到 exe 同级。

    为什么要这个：
    PyInstaller 6 默认把附带文件放进 _internal 子目录，而刷单词引擎
    是按 exe 同级目录读写配置和题库的。两边路径不一致，就会出现
    「界面把 OCR 地址改成了 1225，脚本却还读 1224」这种对不上的问题。
    这里在启动时把数据复制一份到 exe 同级，保证两边读写同一份文件。
    """
    if not is_frozen():
        return
    root = app_root()
    res = resource_root()
    if root == res:
        return

    import shutil

    files = [
        "config.json",
        "助手窗口设置.json",
        "stats.json",
        "progress.json",
        "monitor_state.json",
        "完整脚本_学习测试循环.py",
        "coordinate_profiles.py",
        "四级英语新大纲词汇表.json",
        "word_dict_umi.json",
        "auto_updater.py",
    ]
    dirs = ["题库", "coordinate_profiles"]

    for name in files:
        src = res / name
        dst = root / name
        try:
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
        except Exception:
            pass

    for name in dirs:
        src = res / name
        dst = root / name
        try:
            if src.is_dir() and not dst.exists():
                shutil.copytree(src, dst)
        except Exception:
            pass