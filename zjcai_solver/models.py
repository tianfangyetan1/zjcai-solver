# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Option:
    key: str  # 选项字母，如 "A"
    text: str  # 选项文本


@dataclass
class QuestionSnapshot:
    qid: str
    qtype: str  # 原页面 data-type 字段，已大写化，例如 SINGLE_CHIOCE/JUDGE/FILL_BLANK/PROGRAM_DESIGN 等
    text: str
    options: List[Option]
    images: List[str] = field(default_factory=list)  # 题干与选项中的图片（data URI），顺序对应 [图片N]
