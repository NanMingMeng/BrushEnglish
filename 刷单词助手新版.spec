# -*- mode: python ; coding: utf-8 -*-
# 刷单词助手（新版）打包配置
# 先出「目录版」：一堆文件放在一个文件夹里，启动快、好排错。
# 等目录版跑通，再考虑压缩成单文件或做安装包。

import os

datas = [
    ("qml", "qml"),
    ("内置OCR", "内置OCR"),
    ("完整脚本_学习测试循环.py", "."),
    ("coordinate_profiles.py", "."),
    ("config.json", "."),
    ("题库", "题库"),
    ("四级英语新大纲词汇表.json", "."),
    ("word_dict_umi.json", "."),
    ("auto_updater.py", "."),
    ("助手窗口设置.json", "."),
    ("coordinate_profiles", "coordinate_profiles"),
    ("current_profile.json", "."),
]

# faster-whisper 的 VAD 模型文件（打包时容易漏，必须显式带上）
try:
    from PyInstaller.utils.hooks import collect_data_files
    datas += collect_data_files("faster_whisper")
except Exception:
    pass

hiddenimports = [
    # 界面
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickLayouts",
    "PySide6.QtSvg",
    # 自动化操控（坐标项读取、鼠标键盘）
    "pyautogui",
    "pyscreeze",
    "pymsgbox",
    "pytweening",
    "pygetwindow",
    "mouseinfo",
    "mss",
    "PIL",
    "PIL.Image",
    "keyboard",
    "pefile",
    # 语音识别（拼写题听音）
    "faster_whisper",
    "soundcard",
    "ctranslate2",
    "tokenizers",
    "huggingface_hub",
]

a = Analysis(
    ["刷单词助手新版.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="刷单词助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="刷单词助手",
)