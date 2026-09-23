# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import re
from typing import List, Optional, Tuple

from .constants import OPTION_LABEL_RE


def clean_whitespace(s: str) -> str:
    """压缩任意空白字符为单空格，并去除首尾空白。"""
    s = html.unescape(s or "")
    s = s.replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def compress_whitespace_keep_lines(s: str) -> str:
    """按行压缩空白：行内连续空白压缩为单空格，去除空行，保留换行结构。"""
    s = html.unescape(s or "")
    s = s.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.splitlines()]
    return "\n".join(line for line in lines if line)


def split_fill_answer(raw: str) -> List[str]:
    """将 LLM 返回的填空答案按 | 分隔切分为每空一项；其他字符不做分割。"""
    parts = [p.strip() for p in (raw or "").split("|")]
    return [p for p in parts if p]


def parse_option_label(raw: str) -> Tuple[str, str]:
    """将 'A. 文本' 解析为 ("A", "文本")；若不匹配，返回 ("", 原文)。"""
    t = (raw or "").strip()
    m = OPTION_LABEL_RE.match(t)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    return "", t


def normalize_letter_answer(ans: str, valid_letters: List[str]) -> Optional[str]:
    """从 LLM 返回文本中提取有效选项字母：
    - 若只有一个字母，就用这个字母；
    - 若有多个字母，则使用“最后一个”且在 valid_letters 中的字母。
    """
    if not ans:
        return None

    text = ans.strip().upper()
    # 找出所有 A-Z 字母
    letters = re.findall(r"[A-Z]", text)
    if not letters:
        return None

    # 从后往前找第一个合法的字母
    for letter in reversed(letters):
        if (not valid_letters) or (letter in valid_letters):
            return letter

    # 有字母但都不在 valid_letters 里
    return None
