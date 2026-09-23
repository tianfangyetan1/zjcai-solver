# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import time
from typing import List, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from .constants import DEFAULT_WAIT_SECONDS, SELECTORS, SHORT_WAIT_SECONDS
from .llm import DeepSeekClient
from .models import Option, QuestionSnapshot
from .page import ImageCollector, render_element
from .text_utils import (
    clean_whitespace,
    normalize_letter_answer,
    parse_option_label,
    split_fill_answer,
)

# 该题带图时追加到系统提示词末尾
IMAGE_PROMPT_SUFFIX = "题目中的图片已作为附件提供，请结合图片作答。"


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
        """收集当前题目的关键信息（题干、类型、选项），并把图片提取为 data URI。"""
        q_el = self.wait_for_question_item()
        qid = q_el.get_attribute("id") or ""
        qtype = (q_el.get_attribute("data-type") or "").upper().strip()

        face_el = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["question_face"]))
        )
        # 题干与所有选项共用一个 collector，使图片序号在整道题内唯一
        collector = ImageCollector()
        q_text = render_element(face_el, collector)

        options: List[Option] = []
        # 注意：选项里也可能有图片，所以同样走 render_element
        for lab in self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["answer_labels"]):
            label_text = render_element(lab, collector)
            key, text = parse_option_label(label_text)
            options.append(Option(key=key, text=text))

        return QuestionSnapshot(
            qid=qid,
            qtype=qtype,
            text=q_text,
            options=options,
            images=collector.images,
        )

    def get_question_text_for_code(self) -> Tuple[str, List[str]]:
        """用于代码题的完整提示文本，返回 (文本, 图片列表)：

        - 题目描述（question-face，图片替换为 [图片N] 占位符）
        - 文本编辑器前置代码（题目给的代码骨架 / 示例，通常在 <pre> 里）
        """
        collector = ImageCollector()

        # 1) 题干（可能有多个 .question-face）
        faces = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["question_faces"])
        face_texts: List[str] = []
        for el in faces:
            txt = render_element(el, collector)
            if txt:
                face_texts.append(txt)
        face_text = "\n".join(face_texts).strip()

        # 2) 题目给的起始代码（pre 里的内容）
        template_codes: List[str] = []
        for pre in self.driver.find_elements(
            By.CSS_SELECTOR,
            SELECTORS.get("code_template_pre", ".question-answer pre, pre[data-lang]")
        ):
            txt = (pre.get_attribute("textContent") or "").replace("\r\n", "\n")
            txt = txt.strip("\n")
            if txt:
                template_codes.append(txt)

        parts: List[str] = []

        if face_text:
            parts.append("【题目描述】")
            parts.append(face_text)

        if template_codes:
            parts.append("【系统给出的起始代码（不要随意删除，通常是 main 函数等框架）】")
            parts.append("\n\n".join(template_codes))

        # 如果啥都没有，就退回最原始文本当兜底（图片已收集，仍然一并返回）
        if not parts:
            try:
                raw = "\n".join(
                    (el.get_attribute("textContent") or "").strip() for el in faces
                )
                return raw.strip(), collector.images
            except Exception:
                return "", collector.images

        return "\n\n".join(parts), collector.images

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

    def count_blank_inputs(self) -> int:
        """返回当前填空题的空格数量。"""
        try:
            return len(
                self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["blank_inputs"])
            )
        except Exception:
            return 0

    def fill_blanks(self, answer_text: str) -> None:
        """将答案按顺序填入所有空；仅以 | 分隔；存在“保存”按钮时自动点击保存。"""
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

    def dismiss_judge_popup(self, timeout: int = SHORT_WAIT_SECONDS) -> None:
        """部分代码题（data-type-judgeonsave=1）保存后会弹出阅卷/测试用例弹窗（fancybox），
        检测并关闭，避免遮挡后续的翻题操作。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, SELECTORS["judge_popup_overlay"])
                )
            )
        except TimeoutException:
            return  # 没有弹窗，直接返回

        # 尝试读取 iframe 内的阅卷结果，便于日志核对
        try:
            iframe = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, SELECTORS["judge_popup_iframe"])
                )
            )
            self.driver.switch_to.frame(iframe)
            try:
                body = WebDriverWait(self.driver, DEFAULT_WAIT_SECONDS).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                result_text = clean_whitespace(body.text)
                if result_text:
                    logging.info("阅卷弹窗内容：%s", result_text)
            finally:
                self.driver.switch_to.default_content()
        except Exception:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

        # 关闭弹窗：优先点击关闭按钮，兜底调用 $.fancybox.close()
        closed = False
        try:
            close_btn = self.driver.find_element(
                By.CSS_SELECTOR, SELECTORS["judge_popup_close"]
            )
            close_btn.click()
            closed = True
        except Exception:
            pass
        if not closed:
            try:
                self.driver.execute_script(
                    "try { $.fancybox.close(); } catch(e) {}"
                )
            except Exception:
                pass

        # 等待遮罩消失，避免遮挡后续操作
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, SELECTORS["judge_popup_overlay"])
                )
            )
        except TimeoutException:
            logging.warning("测试用例弹窗未能关闭，可能影响后续操作。")

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
        """将题干与选项（含 [图片N] 占位符）拼装成提示词（供 LLM 使用）。"""
        lines = [q.text]
        for opt in q.options:
            lines.append(opt.text)
        return "\n".join(lines)

    # ---------- 主流程 ----------
    def run(self) -> None:
        count = 1
        while True:
            logging.info("==== 第 %d 题 ====", count)

            q_el = self.wait_for_question_item()
            q = self.collect_current_question()
            logging.info("题型：%s", q.qtype)
            if q.images:
                logging.info("题目包含 %d 张图片，已随请求一并上传。", len(q.images))

            try:
                # 1) 单选 / 判断
                if ("SINGLE" in q.qtype) or ("JUDGE" in q.qtype):
                    llm_input = self.build_llm_prompt(q)
                    system_prompt = (
                        f"请完成以下{self.language}选择题，直接输出选项大写字母，不要使用代码块。"
                    )
                    if q.images:
                        system_prompt += IMAGE_PROMPT_SUFFIX
                    llm_answer = self.llm.ask(system_prompt, llm_input, images=q.images)
                    logging.info("LLM 返回(选择题): %s", llm_answer)

                    valid_letters = [o.key for o in q.options if o.key]
                    letter = normalize_letter_answer(llm_answer, valid_letters)
                    if not letter:
                        letter = valid_letters[0] if valid_letters else "A"
                        logging.warning("无法解析字母，回退使用：%s", letter)

                    self.click_single_choice(letter)

                # 2) 填空 / 程序填空
                elif "FILL" in q.qtype:
                    # q.text 已经包含题干 + 原位置的 [图片N]
                    llm_input = q.text
                    blank_count = self.count_blank_inputs()
                    separator_hint = (
                        f"共有{blank_count}个空，请按顺序使用竖线 | 分隔各空答案，"
                        "不要添加其他内容。"
                        if blank_count > 1
                        else ""
                    )
                    system_prompt = (
                        f"请完成以下{self.language}填空题，直接输出填入内容，不要使用代码块。"
                        f"{separator_hint}"
                    )
                    if q.images:
                        system_prompt += IMAGE_PROMPT_SUFFIX
                    llm_answer = self.llm.ask(system_prompt, llm_input, images=q.images)
                    logging.info("LLM 返回(填空): %s", llm_answer)
                    logging.debug("填空输入框快照: %s", self.snapshot_fill_blanks())
                    self.fill_blanks(llm_answer)

                # 3) 其它大题：程序设计 / SQL / 设计题 / 简答等，按“代码题”处理
                elif any(t in q.qtype for t in ("PROGRAM", "SQL", "DESIGN", "CORRECT", "DB_SQL")):
                    prompt_text, code_images = self.get_question_text_for_code()
                    logging.debug("代码题题面：%s", prompt_text)

                    self.ensure_editor_present()

                    system_prompt = (
                        "你现在在一个在线判题系统中作答编程题。\n"
                        "我会给你：\n"
                        "1. 题目描述（段落）；\n"
                        "2. 系统给出的起始代码（如果有）；\n\n"
                        f"请只使用{self.language}，在不破坏题目已有代码框架的前提下（如果有），写出或补全代码，使之通过所有测试。\n"
                        "要求：\n"
                        "1. 直接输出最终完整代码文本，如果要求在前置代码基础上添加，则只输出需要添加的内容；\n"
                        "2. 不要使用 Markdown 代码块标记；\n"
                        "3. 不要输出任何解释性文字；\n"
                        "4. 不要添加注释。"
                    )
                    if code_images:
                        system_prompt += "\n" + IMAGE_PROMPT_SUFFIX
                    llm_answer = self.llm.ask(
                        system_prompt, prompt_text, images=code_images
                    )
                    logging.info("LLM 返回(代码题) %d 字符", len(llm_answer))

                    if not self.set_editor_content(llm_answer):
                        logging.warning("未能写入富文本/代码编辑器，或未找到可写节点。")

                    self.try_click_save()
                    self.dismiss_judge_popup()
                else:
                    logging.warning("未知题型 %s，跳过。", q.qtype)

            except Exception as e:
                logging.exception("答题过程中出错: %s", e)

            # 翻到下一题
            is_last = self.go_next_question(q_el)
            if is_last:
                logging.info("已到最后一题，程序结束。")
                break

            count += 1
            time.sleep(0.2)
