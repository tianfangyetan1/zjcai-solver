# -*- coding: utf-8 -*-
"""把页面 DOM 元素渲染为纯文本，并把其中的图片提取为 data URI。"""
from __future__ import annotations

import base64
import logging
import re
from html import unescape
from typing import List, Optional

from selenium.webdriver.common.by import By

from .text_utils import compress_whitespace_keep_lines

# DeepSeek 支持 JPEG / PNG / GIF / WebP，SVG 不在其列，需转成截图
_SUPPORTED_DATA_URI_RE = re.compile(r"^data:image/(jpeg|jpg|png|gif|webp);base64,", re.I)


class ImageCollector:
    """按出现顺序收集一道题里的所有图片，统一分配全局序号。

    题干与各选项共用同一个 collector，保证「第 N 个 [图片N] 占位符」
    与「第 N 张附图」在整道题范围内一一对应。
    """

    def __init__(self) -> None:
        self.images: List[str] = []

    def add(self, data_uri: str) -> int:
        """登记一张图片，返回其 1-based 序号。"""
        self.images.append(data_uri)
        return len(self.images)


def extract_image_data_uri(img_el) -> Optional[str]:
    """把一个 <img> 元素取成可直接传给模型的 data URI。

    页面里的题目图片通常已经是内联的 data:image/png;base64,...，可以直接透传；
    外链图片、SVG 或需要登录态才能访问的图片则退回到元素截图。
    """
    try:
        src = img_el.get_attribute("src") or ""
    except Exception:
        src = ""

    if _SUPPORTED_DATA_URI_RE.match(src):
        return src

    try:
        png_bytes = img_el.screenshot_as_png
    except Exception as e:
        logging.warning("截取图片失败：%s", e)
        return None

    if not png_bytes:
        return None
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def render_element(element, collector: Optional[ImageCollector] = None) -> str:
    """把一个包含 <img> 的 DOM 元素转换为纯文本：

    - 普通文字保持不变；
    - 每个 <img> 按出现顺序替换为 [图片N] 占位符，图片本身交给 collector 收集；
    - 提取失败的图片降级为 [图片]，不中断答题。
    """
    if element is None:
        return ""

    # 用 innerHTML 保留图片在文本中的相对位置
    raw_html = element.get_attribute("innerHTML") or ""
    if not raw_html:
        # 没有 HTML 时退化为纯文本
        return compress_whitespace_keep_lines(element.text)

    # 收集当前元素下所有图片（按 DOM 顺序）
    try:
        imgs = element.find_elements(By.CSS_SELECTOR, "img")
    except Exception:
        imgs = []

    # 与 imgs 等长：元素为图片序号，None 表示提取失败
    indices: List[Optional[int]] = []
    for idx, img_el in enumerate(imgs, start=1):
        data_uri = extract_image_data_uri(img_el) if collector is not None else None
        if data_uri:
            indices.append(collector.add(data_uri))  # type: ignore[union-attr]
        else:
            if collector is not None:
                logging.warning("第 %d 张图片无法提取，将以 [图片] 占位。", idx)
            indices.append(None)

    # 按顺序把 <img> 替换为 [图片N]
    cursor = 0

    def _img_replacer(m: re.Match) -> str:
        nonlocal cursor
        number = indices[cursor] if cursor < len(indices) else None
        cursor += 1
        return f" [图片{number}] " if number else " [图片] "

    # 先把 <pre> 块用占位符保护起来：其内部原样保留（空行/缩进可能是题目内容），
    # 仅去掉 <pre> 标签首尾紧贴的排版换行
    pre_blocks: List[str] = []

    def _pre_protect(m: re.Match) -> str:
        pre_blocks.append(m.group(1).strip("\n"))
        return f"\x00PRE{len(pre_blocks) - 1}\x00"

    raw_html = re.sub(r"(?is)<pre\b[^>]*>(.*?)</pre>", _pre_protect, raw_html)

    # 先把 <br> 转成换行，增强可读性
    raw_html = re.sub(r"(?i)<br\s*/?>", "\n", raw_html)
    # 再替换掉所有 <img ...>
    raw_html = re.sub(r"(?i)<img\b[^>]*>", _img_replacer, raw_html)
    # 去掉剩余 HTML 标签
    raw_html = re.sub(r"<[^>]+>", "", raw_html)
    # 按行压缩空白，保留换行结构（如 <pre> 中的多行输出样例）
    text = compress_whitespace_keep_lines(raw_html)

    # 还原 <pre> 块内容（此时尚未做 HTML 实体反转义，在这里补上）
    def _pre_restore(m: re.Match) -> str:
        return unescape(pre_blocks[int(m.group(1))])

    return re.sub(r"\x00PRE(\d+)\x00", _pre_restore, text)
