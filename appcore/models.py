# -*- coding: utf-8 -*-
"""数据模型：把 Python 里的列表，翻译成界面列表能直接显示的样子。

白话解释：
界面上的列表（QML 的 ListView）不认识 Python 的列表和字典。
这两个模型就是「翻译官」：把 Python 数据摆成列表要的格式，
数据一变还会主动通知界面刷新，不用手动去刷。
"""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class _BaseListModel(QAbstractListModel):
    """列表模型的公共部分：存一堆字典，按角色名往外给。"""

    #: 子类要覆盖，写清楚「角色 → 显示名」
    _ROLE_MAP: Dict[int, bytes] = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []

    def roleNames(self) -> Dict[int, bytes]:
        return dict(self._ROLE_MAP)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        name = self._ROLE_MAP.get(role)
        if name is None:
            return None
        return row.get(name.decode("utf-8"), "")

    def load(self, rows: List[Dict[str, Any]]) -> int:
        """整表替换（会通知界面整体刷新）。"""
        self.beginResetModel()
        self._rows = list(rows or [])
        self.endResetModel()
        return len(self._rows)

    def clear(self) -> None:
        self.load([])

    def row(self, i: int) -> Dict[str, Any]:
        if 0 <= i < len(self._rows):
            return self._rows[i]
        return {}

    def rows(self) -> List[Dict[str, Any]]:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


class CoordListModel(_BaseListModel):
    """坐标项列表：名称 + 坐标数字。"""

    R_KEY = Qt.UserRole + 1
    R_NAME = Qt.UserRole + 2
    R_VALUE = Qt.UserRole + 3
    R_DESC = Qt.UserRole + 4

    _ROLE_MAP = {
        R_KEY: b"key",
        R_NAME: b"name",
        R_VALUE: b"value",
        R_DESC: b"desc",
    }

    def set_value(self, i: int, text: str) -> None:
        """改某一行的坐标文字（会通知界面刷新这一行）。"""
        if not (0 <= i < len(self._rows)):
            return
        self._rows[i]["value"] = str(text or "")
        idx = self.index(i, 0)
        self.dataChanged.emit(idx, idx, [self.R_VALUE])


class BankListModel(_BaseListModel):
    """题库列表：序号 + 单词 + 释义 + 是否已确认。"""

    R_NO = Qt.UserRole + 1
    R_WORD = Qt.UserRole + 2
    R_MEANING = Qt.UserRole + 3
    R_CONFIRMED = Qt.UserRole + 4

    _ROLE_MAP = {
        R_NO: b"no",
        R_WORD: b"word",
        R_MEANING: b"meaning",
        R_CONFIRMED: b"confirmed",
    }