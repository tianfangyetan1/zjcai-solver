# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import logging
import os

# Windows 10+ 原生 Toast 通知
try:
    from win10toast import ToastNotifier  # type: ignore
    _WIN10_TOAST_AVAILABLE = True
except Exception:
    ToastNotifier = None  # type: ignore
    _WIN10_TOAST_AVAILABLE = False


def notify_exam_finished(
    title: str = "答题完成",
    message: str = "本次试卷自动答题已完成。"
) -> None:
    """在 Windows 下弹出系统通知（优先 Toast，失败则退回 MessageBox）。"""
    if os.name != "nt":
        return  # 只在 Windows 上尝试通知

    # 1) 优先尝试 Windows 10 Toast 通知
    if _WIN10_TOAST_AVAILABLE and ToastNotifier is not None:
        try:
            toaster = ToastNotifier()
            # threaded=True 不阻塞主线程，duration 为秒数
            toaster.show_toast(title, message, duration=5, threaded=True)
            return
        except Exception as e:
            logging.warning("Windows Toast 通知发送失败，将退回 MessageBox: %s", e)

    # 2) 兜底：使用原生 MessageBox 对话框
    try:
        # 0x40: MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        # 如果连 MessageBox 也失败，就静默忽略
        pass
