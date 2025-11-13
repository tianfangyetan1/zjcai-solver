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
SHORT_WAIT_SECONDS = 2

# 页面选择器集中管理：如页面结构变动，仅需在此处调整
SELECTORS = {
    "question_item": "#c-grid-ajax .question-item",
    "question_face": "#c-grid-ajax .question-item .question-face",
    "answer_labels": ".question-answer label",
    "option_input_by_value": (
        '#c-grid-ajax .question-item .question-answer '
        'input.question-option-input[value="{letter}"]'
    ),
    "blank_inputs": (
        "#c-grid-ajax .question-item .question-answer .question-blank-input"
    ),
    "save_button_id": "cmd_saveQuestion",
    "next_button_id": "cmd_next",
    "login_username_id": "UserName",
    "login_password_id": "Password",
}

# 解析选项标签用的正则，例如："A. 选项内容" → ("A", "选项内容")
OPTION_LABEL_RE = re.compile(r"^([A-Z])\s*[\.、．]?\s*(.*)$")

# =============================
# 数据结构
# =============================

@dataclass
class Option:
    key: str  # 选项字母，如 "A"
    text: str # 选项文本

@dataclass
class QuestionSnapshot:
    qid: str
    qtype: str  # 原页面 data-type 字段，已大写化，例如 SINGLE/JUDGE/FILL_BLANK 等
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

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat"):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def ask(self, system_prompt: str, user_prompt: str) -> str:
        """发送对话并返回 assistant 文本。出现异常时抛出。"""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
        )

        if resp.choices[0].message.content is None:
            print("错误：LLM 未返回结果")
            return ""

        return resp.choices[0].message.content.strip()

# =============================
# 核心自动化类
# =============================

class QuizSolver:
    """面向页面结构封装的答题执行器。"""

    def __init__(self, driver: webdriver.Chrome, llm: DeepSeekClient, wait_seconds: int = DEFAULT_WAIT_SECONDS):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)
        self.llm = llm

    # ---------- 登录 ----------
    def login(self, url: str, username: str, password: str) -> None:
        """打开链接并完成登录。"""
        self.driver.get(url)
        # 输入用户名
        username_box = self.driver.find_element(By.ID, SELECTORS["login_username_id"])
        username_box.clear()
        username_box.send_keys(username)
        # 输入密码
        password_box = self.driver.find_element(By.ID, SELECTORS["login_password_id"])
        password_box.clear()
        password_box.send_keys(password)
        time.sleep(0.3)
        # 提交
        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_btn.click()
        time.sleep(0.6)

    # ---------- 题面获取与解析 ----------
    def wait_for_question_item(self):
        """等待题目容器渲染完成并返回元素对象。"""
        return self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["question_item"])))

    def collect_current_question(self) -> QuestionSnapshot:
        """收集当前题目的关键信息（题干、类型、选项）。"""
        q_el = self.wait_for_question_item()
        qid = q_el.get_attribute("id")
        if qid is None:
            qid = ""
        qtype = (q_el.get_attribute("data-type") or "").upper().strip()

        face_el = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["question_face"])) )
        q_text = clean_whitespace(face_el.text)

        options: List[Option] = []
        for lab in self.driver.find_elements(By.CSS_SELECTOR, SELECTORS["answer_labels"]):
            key, text = parse_option_label(lab.text)
            options.append(Option(key=key, text=text))

        return QuestionSnapshot(qid=qid, qtype=qtype, text=q_text, options=options)

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
                label_text = inp.find_element(By.XPATH, "preceding-sibling::label[1]").text.strip()
            except NoSuchElementException:
                pass
            result.append({
                "index": i,
                "label": label_text,
                "input_id": inp.get_attribute("id"),
                "value": inp.get_attribute("value") or "",
            })
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
            # 无保存按钮则略微等待，留给页面脚本自动保存
            time.sleep(0.3)

    # ---------- 翻题 ----------
    def go_next_question(self, old_q_el) -> bool:
        """点击“下一题”，等待旧题元素失效；若弹出“最后一题”提示则返回 True 表示结束。"""
        next_btn = self.wait.until(EC.element_to_be_clickable((By.ID, SELECTORS["next_button_id"])) )
        next_btn.click()
        # 等旧元素真正被替换，避免引用失效
        self.wait.until(EC.staleness_of(old_q_el))

        # 检测是否为最后一题
        is_last = False
        try:
            WebDriverWait(self.driver, SHORT_WAIT_SECONDS).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            msg = (alert.text or "").strip()
            if "最后一题" in msg:
                is_last = True
            alert.accept()
        except TimeoutException:
            pass
        return is_last

    # ---------- LLM 决策逻辑 ----------
    def build_llm_prompt(self, q: QuestionSnapshot) -> str:
        """将题干与选项拼装成提示词（供 LLM 使用）。"""
        lines = [q.text]
        for opt in q.options:
            # 若解析不到字母，仍然把原始文本拼上
            key_display = opt.key or "?"
            lines.append(f"【{key_display}】{opt.text}")
        return "\n".join(lines)

    @staticmethod
    def normalize_letter_answer(ans: str, valid_letters: List[str]) -> Optional[str]:
        """从 LLM 返回文本中提取有效选项字母。"""
        if not ans:
            return None
        text = ans.strip().upper()
        # 常见格式清洗，如 "答案：A"、"A. ..."、"选 A" 等
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

            # 构建给 LLM 的文本
            llm_input = self.build_llm_prompt(q)
            logging.debug("LLM input: %s", llm_input)

            try:
                if ("SINGLE" in q.qtype) or ("JUDGE" in q.qtype):
                    # 单选/判断
                    system_prompt = "请完成以下选择题，直接输出选项大写字母，不要使用代码块"
                    llm_answer = self.llm.ask(system_prompt, llm_input)
                    logging.info("LLM 返回: %s", llm_answer)

                    valid_letters = [o.key for o in q.options if o.key]
                    letter = self.normalize_letter_answer(llm_answer, valid_letters)
                    if not letter:
                        # 若无法解析，保底选择第一个有字母的选项
                        letter = valid_letters[0] if valid_letters else "A"
                        logging.warning("无法从 LLM 返回解析字母，回退使用：%s", letter)

                    self.click_single_choice(letter)

                elif "FILL" in q.qtype:  # FILL_BLANK / PROGRAM_FILL_BLANK
                    system_prompt = "请完成以下填空题，直接输出填入内容，不要使用代码块"
                    llm_answer = self.llm.ask(system_prompt, llm_input)
                    logging.info("LLM 返回(填空): %s", llm_answer)

                    # 可选：记录快照，便于调试
                    logging.debug("填空输入框快照: %s", self.snapshot_fill_blanks())
                    self.fill_blanks(llm_answer)

                else:
                    logging.info("题型 %s 暂不处理，自动跳过。", q.qtype)

            except Exception as e:
                logging.exception("写入答案失败: %s", e)

            # 下一题
            is_last = self.go_next_question(q_el)
            if is_last:
                logging.info("已到最后一题，流程结束。")
                break

            count += 1

# =============================
# 启动与参数读取
# =============================

def load_config(cfg_path: Path = Path("config.json")) -> dict:
    """读取配置文件。"""
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def build_driver(chromedriver_path) -> webdriver.Chrome:
    """创建并返回 Chrome WebDriver。可在此处追加启动项配置。"""
    options = webdriver.ChromeOptions()
    try:
        if chromedriver_path != "":
            service = Service(
                executable_path=chromedriver_path
            )
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
        raise SystemExit("config.json 缺少必要字段")

    question_url = input("请输入答题链接：").strip()
    if not question_url:
        raise SystemExit("未输入答题链接，已退出。")

    llm = DeepSeekClient(api_key=deepseek_api_key)
    driver = build_driver(chromedriver_path)

    try:
        solver = QuizSolver(driver=driver, llm=llm, wait_seconds=DEFAULT_WAIT_SECONDS)
        solver.login(question_url, username, password)
        solver.run()
    finally:
        # 仅在 Windows 上停顿一下，方便查看控制台输出
        if os.name == "nt":
            os.system("pause")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
