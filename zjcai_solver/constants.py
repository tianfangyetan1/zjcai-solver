# -*- coding: utf-8 -*-
from __future__ import annotations

import re

DEFAULT_WAIT_SECONDS = 15
SHORT_WAIT_SECONDS = 3

# 页面选择器集中管理
SELECTORS = {
    # 通用题目区域
    "question_item": "#c-grid-ajax .question-item",
    "question_face": "#c-grid-ajax .question-item .question-face",
    "question_faces": ".question-face",

    # 选择题/判断题
    "answer_labels": ".question-answer label",
    "option_input_by_value": (
        "#c-grid-ajax .question-item .question-answer "
        "input.question-option-input[value=\"{letter}\"]"
    ),

    # 填空题
    "blank_inputs": "#c-grid-ajax .question-item .question-answer .question-blank-input",

    # 代码题编辑器候选（TinyMCE / Monaco / textarea / contenteditable）
    "any_editor_candidates": (
        "#question_content, textarea.question-design-input, "
        "iframe#editorContainer, iframe.code-editor, iframe.monaco-editor, "
        "[contenteditable='true']"
    ),

    # 代码题文本编辑器前置内容
    "code_template_pre": ".question-answer pre, pre[data-lang]",

    # 保存 & 翻题
    "save_button_id": "cmd_saveQuestion",
    "next_button_id": "cmd_next",

    # 代码题保存后的阅卷/测试用例弹窗（fancybox）
    "judge_popup_overlay": ".fancybox-overlay",
    "judge_popup_iframe": "iframe.fancybox-iframe",
    "judge_popup_close": ".fancybox-close",

    # 登录
    "login_username_id": "UserName",
    "login_password_id": "Password",
    "login_submit_css": "button[type='submit']",
}

# 解析选项标签用的正则，例如："A. 选项内容" → ("A", "选项内容")
OPTION_LABEL_RE = re.compile(r"^([A-Z])\s*[\.、．]?\s*(.*)$")
