# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)

from openai import OpenAI

# =============================
# 配置与常量
# =============================

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

    # 保存 & 翻题
    "save_button_id": "cmd_saveQuestion",
    "next_button_id": "cmd_next",

    # 登录
    "login_username_id": "UserName",
    "login_password_id": "Password",
    "login_submit_css": "button[type='submit']",
}

# 解析选项标签用的正则，例如："A. 选项内容" → ("A", "选项内容")
OPTION_LABEL_RE = re.compile(r"^([A-Z])\s*[\.、．]?\s*(.*)$")

# =============================
# 数据结构
# =============================

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


# =============================
# 工具函数
# =============================

def clean_whitespace(s: str) -> str:
    """压缩任意空白字符为单空格，并去除首尾空白。"""
    return re.sub(r"\s+", " ", s or "").strip()


def split_fill_answer(raw: str) -> List[str]:
    """将 LLM 返回的填空答案切分为每空一项，支持 | 、英文/中文逗号 作为分隔符。"""
    parts = [p.strip() for p in re.split(r"[|,，]", raw or "")]
    return [p for p in parts if p]


def parse_option_label(raw: str) -> Tuple[str, str]:
    """将 'A. 文本' 解析为 ("A", "文本")；若不匹配，返回 ("", 原文)。"""
    t = (raw or "").strip()
    m = OPTION_LABEL_RE.match(t)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    return "", t


# =============================
# LLM 封装
# =============================

class DeepSeekClient:
    """DeepSeek Chat API 的轻量封装。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def ask(self, system_prompt: str, user_prompt: str) -> str:
        """发送对话并返回 assistant 文本."""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
        )
        content = resp.choices[0].message.content
        return (content or "").strip()


# =============================
# 核心自动化类（统一客观题 + 代码题）
# =============================

class QuizSolver:
    """面向页面结构封装的答题执行器。"""

    def __init__(
        self,
        driver: webdriver.Chrome,
        llm: DeepSeekClient,
        language: str = "C语言",
        wait_seconds: int = DEFAULT_WAIT_SECONDS,
    ):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)
        self.llm = llm
        self.language = language or "C语言"

    # ---------- 登录 ----------
    def login(self, url: str, username: str, password: str) -> None:
        """打开链接并完成登录。"""
        self.driver.get(url)
        time.sleep(0.3)
        username_box = self.driver.find_element(By.ID, SELECTORS["login_username_id"])
        password_box = self.driver.find_element(By.ID, SELECTORS["login_password_id"])
        username_box.clear()
        username_box.send_keys(username)
        password_box.clear()
        password_box.send_keys(password)
        time.sleep(0.3)
        submit_btn = self.driver.find_element(By.CSS_SELECTOR, SELECTORS["login_submit_css"])
        submit_btn.click()
        time.sleep(0.6)

    # ---------- 题面获取与解析 ----------
    def wait_for_question_item(self):
        """等待题目容器渲染完成并返回元素对象。"""
        return self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["question_item"]))
        )

    def collect_current_question(self) -> QuestionSnapshot:
        """收集当前题目的关键信息（题干、类型、选项）。"""
        q_el = self.wait_for_question_item()
        qid = q_el.get_attribute("id") or ""
        qtype = (q_el.get_attribute("data-type") or "").upper().strip()

        face_el = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["question_face"]))
        )
        q_text = clean_whitespace(face_el.text)

        options: List[Option] = []
        for lab in self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["answer_labels"]):
            key, text = parse_option_label(lab.text)
            options.append(Option(key=key, text=text))

        return QuestionSnapshot(qid=qid, qtype=qtype, text=q_text, options=options)

    def get_question_text_for_code(self) -> str:
        """用于代码题的题面文本（可包含多个 question-face）。"""
        faces = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["question_faces"])
        raw = "\n".join((el.get_attribute("textContent") or "").strip() for el in faces)
        # 压缩空白
        raw = re.sub(r"\r?\n\s*\r?\n+", "\n", raw)
        raw = re.sub(r"[\t\x0b\x0c]+", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    # ---------- 作答：单选/判断 ----------
    def click_single_choice(self, letter: str) -> None:
        """点击单选/判断题的字母选项（A/B/C/D/…）。"""
        letter = (letter or "").strip().upper()
        css = SELECTORS["option_input_by_value"].format(letter=letter)
        el = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        el.click()

    # ---------- 作答：填空 ----------
    def snapshot_fill_blanks(self) -> list[dict]:
        """采集填空题每个输入框的 label/当前值等，便于调试或日志。"""
        result = []
        inputs = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["blank_inputs"])
        for i, inp in enumerate(inputs, 1):
            label_text = ""
            try:
                label_text = inp.find_element(
                    By.XPATH, "preceding-sibling::label[1]"
                ).text.strip()
            except NoSuchElementException:
                pass
            result.append(
                {
                    "index": i,
                    "label": label_text,
                    "input_id": inp.get_attribute("id"),
                    "value": inp.get_attribute("value") or "",
                }
            )
        return result

    def fill_blanks(self, answer_text: str) -> None:
        """将答案按顺序填入所有空；支持以 | 或 , 分隔；存在“保存”按钮时自动点击保存。"""
        parts = split_fill_answer(answer_text)
        inputs = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["blank_inputs"])
        for idx, inp in enumerate(inputs):
            val = parts[idx] if idx < len(parts) else ""
            inp.clear()
            if val:
                inp.send_keys(val)
        # 显式保存（若有保存按钮）
        try:
            save_btn = self.driver.find_element(By.ID, SELECTORS["save_button_id"])
            if save_btn.is_enabled():
                save_btn.click()
        except NoSuchElementException:
            time.sleep(0.3)

    # ---------- 代码题：编辑器处理 ----------
    def ensure_editor_present(self, timeout: int = DEFAULT_WAIT_SECONDS) -> None:
        """等待任一类型编辑器出现（尽量保证 editor 就绪）。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, SELECTORS["any_editor_candidates"])
                )
            )
        except TimeoutException:
            logging.debug("未在超时时间内发现编辑器候选节点，继续尝试写入。")

    def set_editor_content(self, content: str, timeout: int = 6) -> bool:
        """向常见富文本/代码编辑器写入内容。

        支持：
        1) TinyMCE（遍历 tinymce.editors；仅目标 textarea.question-design-input）
        2) Monaco（iframe 包装：#editorContainer / .code-editor / .monaco-editor）
        3) 纯 textarea（textarea.question-design-input）
        4) contenteditable（#question_content 或 [contenteditable=true]）
        """
        w = WebDriverWait(self.driver, timeout)

        # ---- TinyMCE ----
        try:
            updated = self.driver.execute_script(
                """
                var content = arguments[0];
                try {
                    if (window.tinymce && Array.isArray(tinymce.editors) && tinymce.editors.length) {
                        var ok = false;
                        tinymce.editors.forEach(function(ed){
                            try {
                                var t = ed && ed.targetElm;
                                if (t && t.matches && t.matches('textarea.question-design-input')) {
                                    ed.setContent(content);
                                    ed.fire('change');
                                    ok = true;
                                }
                            } catch(e){}
                        });
                        return ok;
                    }
                } catch(e){}
                return false;
                """,
                content,
            )
            if updated:
                return True
        except Exception:
            pass

        # ---- Monaco ----
        def _try_monaco_in_frame(frame_css: str) -> bool:
            try:
                iframe = w.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, frame_css))
                )
                self.driver.switch_to.frame(iframe)
                try:
                    applied = self.driver.execute_script(
                        """
                        var value = arguments[0];
                        try {
                            if (window.editor && typeof window.editor.setValue === 'function') {
                                window.editor.setValue(value); return true;
                            }
                            if (window.monaco && monaco.editor) {
                                if (monaco.editor.getEditors) {
                                    var eds = monaco.editor.getEditors();
                                    if (eds && eds.length) { eds[0].setValue(value); return true; }
                                }
                                if (monaco.editor.getModels) {
                                    var models = monaco.editor.getModels();
                                    if (models && models.length) { models[0].setValue(value); return true; }
                                }
                            }
                        } catch(e) {}
                        return false;
                        """,
                        content,
                    )
                    return bool(applied)
                finally:
                    self.driver.switch_to.default_content()
            except Exception:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                return False

        for css in ("iframe#editorContainer", "iframe.code-editor", "iframe.monaco-editor"):
            if _try_monaco_in_frame(css):
                return True

        # ---- 纯 textarea ----
        try:
            ta = w.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "textarea.question-design-input")
                )
            )
            self.driver.execute_script(
                """
                var el = arguments[0], val = arguments[1];
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                """,
                ta,
                content,
            )
            return True
        except Exception:
            pass

        # ---- contenteditable ----
        try:
            target = None
            try:
                target = w.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#question_content")
                    )
                )
            except Exception:
                target = w.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "[contenteditable='true']")
                    )
                )
            self.driver.execute_script(
                """
                var el = arguments[0], val = arguments[1];
                el.textContent = val;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                """,
                target,
                content,
            )
            return True
        except Exception:
            pass

        return False

    def try_click_save(self) -> None:
        """如果存在保存按钮则点击。"""
        try:
            btn = WebDriverWait(self.driver, SHORT_WAIT_SECONDS).until(
                EC.element_to_be_clickable((By.ID, SELECTORS["save_button_id"]))
            )
            btn.click()
        except Exception:
            pass

    # ---------- 翻题 ----------
    def go_next_question(self, old_q_el) -> bool:
        """点击“下一题”，等待旧题元素失效；若弹出“最后一题”提示则返回 True 表示结束。"""
        next_btn = self.wait.until(
            EC.element_to_be_clickable((By.ID, SELECTORS["next_button_id"]))
        )
        next_btn.click()

        is_last = False
        # 先处理可能的 alert（“已经是最后一题了。”之类）
        try:
            WebDriverWait(self.driver, SHORT_WAIT_SECONDS).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            msg = (alert.text or "").strip()
            if "最后一题" in msg:
                is_last = True
            alert.accept()
        except TimeoutException:
            pass

        # 再等旧元素真正失效，避免引用旧题
        if old_q_el is not None:
            try:
                WebDriverWait(self.driver, DEFAULT_WAIT_SECONDS).until(
                    EC.staleness_of(old_q_el)
                )
            except TimeoutException:
                logging.debug("等待旧题失效超时，页面可能未刷新或选择器不匹配。")

        return is_last

    # ---------- LLM 决策逻辑 ----------
    def build_llm_prompt(self, q: QuestionSnapshot) -> str:
        """将题干与选项拼装成提示词（供 LLM 使用）。"""
        lines = [q.text]
        for opt in q.options:
            key_display = opt.key or "?"
            lines.append(f"【{key_display}】{opt.text}")
        return "\n".join(lines)

    @staticmethod
    def normalize_letter_answer(ans: str, valid_letters: List[str]) -> Optional[str]:
        """从 LLM 返回文本中提取有效选项字母。"""
        if not ans:
            return None
        text = ans.strip().upper()
        m = re.search(r"([A-Z])", text)
        if m:
            letter = m.group(1)
            if not valid_letters or letter in valid_letters:
                return letter
        return None

    # ---------- 主流程 ----------
    def run(self) -> None:
        count = 1
        while True:
            logging.info("==== 第 %d 题 ====", count)

            q_el = self.wait_for_question_item()
            q = self.collect_current_question()
            logging.info("当前题型：%s", q.qtype)

            try:
                # 1) 单选 / 判断
                if ("SINGLE" in q.qtype) or ("JUDGE" in q.qtype):
                    llm_input = self.build_llm_prompt(q)
                    system_prompt = "请完成以下选择题，直接输出选项大写字母，不要使用代码块。"
                    llm_answer = self.llm.ask(system_prompt, llm_input)
                    logging.info("LLM 返回(选择题): %s", llm_answer)

                    valid_letters = [o.key for o in q.options if o.key]
                    letter = self.normalize_letter_answer(llm_answer, valid_letters)
                    if not letter:
                        letter = valid_letters[0] if valid_letters else "A"
                        logging.warning("无法解析字母，回退使用：%s", letter)

                    self.click_single_choice(letter)

                # 2) 填空 / 程序填空
                elif "FILL" in q.qtype:
                    llm_input = q.text  # 填空题一般没有选项，直接用题干即可
                    system_prompt = "请完成以下填空题，直接输出填入内容，不要使用代码块。"
                    llm_answer = self.llm.ask(system_prompt, llm_input)
                    logging.info("LLM 返回(填空): %s", llm_answer)

                    logging.debug("填空输入框快照: %s", self.snapshot_fill_blanks())
                    self.fill_blanks(llm_answer)

                # 3) 其它大题：程序设计 / SQL / 设计题 / 简答等，按“代码题”处理
                else:
                    prompt_text = self.get_question_text_for_code()
                    logging.debug("代码题题面：%s", prompt_text)

                    self.ensure_editor_present()

                    system_prompt = (
                        f"请使用{self.language}完成以下需求，"
                        f"不要使用注释，不要使用代码块。"
                    )
                    llm_answer = self.llm.ask(system_prompt, prompt_text)
                    logging.info("LLM 返回(代码题) %d 字符", len(llm_answer))

                    if not self.set_editor_content(llm_answer):
                        logging.warning("未能写入富文本/代码编辑器，或未找到可写节点。")

                    self.try_click_save()

            except Exception as e:
                logging.exception("答题过程中出错: %s", e)

            # 翻到下一题
            is_last = self.go_next_question(q_el)
            if is_last:
                logging.info("已到最后一题，流程结束。")
                break

            count += 1
            time.sleep(0.2)


# =============================
# 启动与参数读取
# =============================

def load_config(cfg_path: Path = Path("config.json")) -> dict:
    """读取配置文件。"""
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return cfg


def build_driver(chromedriver_path: str) -> webdriver.Chrome:
    """创建并返回 Chrome WebDriver。"""
    options = webdriver.ChromeOptions()
    try:
        if chromedriver_path:
            service = Service(executable_path=chromedriver_path)
            return webdriver.Chrome(service=service, options=options)
        else:
            return webdriver.Chrome(options=options)
    except WebDriverException as e:
        raise RuntimeError(f"启动 Chrome 失败：{e}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    cfg = load_config()
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    deepseek_api_key = cfg.get("deepseek_api_key", "")
    chromedriver_path = cfg.get("chromedriver_path", "")

    if not (username and password and deepseek_api_key):
        raise SystemExit("config.json 缺少必要字段（username/password/deepseek_api_key）")

    question_url = input("请输入答题链接：").strip()
    if not question_url:
        raise SystemExit("未输入答题链接，已退出。")

    language = input("请输入代码题编程语言（例如 C语言、C++、Java、Python 等）：").strip() or "C语言"

    llm = DeepSeekClient(api_key=deepseek_api_key)
    driver = build_driver(chromedriver_path)

    try:
        solver = QuizSolver(
            driver=driver,
            llm=llm,
            language=language,
            wait_seconds=DEFAULT_WAIT_SECONDS,
        )
        solver.login(question_url, username, password)
        solver.run()
    finally:
        if os.name == "nt":
            os.system("pause")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
