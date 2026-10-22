# -*- coding: utf-8 -*-
"""配置读写：所有设置都存成 JSON 文件，读不到就用默认值。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import paths


def _atomic_write(path: Path, text: str) -> bool:
    """先写临时文件再整体替换，避免写一半崩掉把原配置弄坏。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, str(path))
            return True
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
    except Exception:
        return False


def read_json(path: Path, default: Any = None) -> Any:
    try:
        p = Path(path)
        if not p.exists():
            return default
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> bool:
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return False
    return _atomic_write(Path(path), text)


DEFAULT_UI_SETTINGS = {
    "x": 120, "y": 90, "w": 1180, "h": 760,
    "theme": "light", "layout": "tabs",
    "ocr_engine": "rapid", "spelling_source": "asr", "top": True,
}


def load_ui_settings() -> dict:
    data = read_json(paths.ui_settings_file(), None)
    if not isinstance(data, dict):
        data = {}
    merged = dict(DEFAULT_UI_SETTINGS)
    for k, v in data.items():
        if k in merged:
            merged[k] = v
    return merged


def save_ui_settings(data: dict) -> bool:
    try:
        merged = dict(DEFAULT_UI_SETTINGS)
        merged.update({k: v for k, v in (data or {}).items() if k in merged})
        return write_json(paths.ui_settings_file(), merged)
    except Exception:
        return False

# ---------------- 坐标值的小工具 ----------------
def fmt_nums(values) -> str:
    """把一串数字显示成「1467, 188」这样，方便人读也方便改。"""
    try:
        return ", ".join(str(int(round(float(v)))) for v in (values or []))
    except Exception:
        return ", ".join(str(v) for v in (values or []))


def parse_nums(text: str):
    """把「1467, 188」这样的文字变回数字列表。不是数字就抛错，让调用方拦住。"""
    raw = str(text or "").replace("，", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [int(round(float(p))) for p in parts]


def get_by_path(root, path, default=None):
    """按 [a, b, 0] 这样的一串钥匙，从层层嵌套的字典/列表里取值。"""
    node = root
    for p in (path or []):
        try:
            if isinstance(p, int):
                if not isinstance(node, (list, tuple)) or p >= len(node):
                    return default
                node = node[p]
            else:
                if not isinstance(node, dict) or p not in node:
                    return default
                node = node[p]
        except Exception:
            return default
    return node


def set_by_path(root, path, value) -> None:
    """按 [a, b, 0] 这样的一串钥匙，往层层嵌套的字典/列表里写值。"""
    if not path:
        return
    node = root
    for p in path[:-1]:
        if isinstance(p, int):
            while len(node) <= p:
                node.append(None)
            if not isinstance(node[p], (dict, list)):
                node[p] = {}
            node = node[p]
        else:
            if not isinstance(node.get(p), (dict, list)):
                node[p] = {}
            node = node[p]

    last = path[-1]
    if isinstance(last, int):
        while len(node) <= last:
            node.append(None)
        node[last] = value
    else:
        node[last] = value