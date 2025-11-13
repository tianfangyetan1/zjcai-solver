# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from openai import OpenAI

# =============================
# 常量与选择器
# =============================
DEFAULT_WAIT_SECONDS = 15
SHORT_WAIT_SECONDS = 3

SELECTORS = {
    # 登录
    "login_username_id": "UserName",
    "login_password_id": "Password",
    "login_submit_css": "button[type='submit']",
    # 题面与编辑器
    "question_faces": ".question-face",
    # 这里尽可能覆盖多种可能的编辑器容器
    "any_editor_candidates": (
        "#question_content, textarea.question-design-input, iframe#editorContainer, "
        "iframe.code-editor, iframe.monaco-editor, [contenteditable='true']"
    ),
    # 保存与下一题
    "save_button_id": "cmd_saveQuestion",
    "next_button_id": "cmd_next",
}

# =============================
# 工具函数
# =============================

def build_driver() -> webdriver.Chrome:
    """构建并返回 Chrome WebDriver；支持通过 HEADLESS=1 环境变量启用无头模式。"""
    options = webdriver.ChromeOptions()
    if os.getenv("HEADLESS") == "1":
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as e:
        raise SystemExit(f"[fatal] 启动 Chrome 失败：{e}")


def load_config(path: Path = Path("config.json")) -> dict:
    """读取配置文件。缺失字段将抛出异常。"""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("username", "password", "deepseek_api_key"):
        if key not in cfg or not cfg[key]:
            raise SystemExit(f"[fatal] config.json 缺少必要字段：{key}")
    return cfg


def init_llm_client(api_key: str, base_url: str = "https://api.deepseek.com") -> OpenAI:
    """初始化 OpenAI 客户端以使用 DeepSeek 兼容接口。"""
    return OpenAI(api_key=api_key, base_url=base_url)


def wait_for(driver: webdriver.Chrome, timeout: int = DEFAULT_WAIT_SECONDS) -> WebDriverWait:
    """简写的 WebDriverWait 工厂。"""
    return WebDriverWait(driver, timeout)


def get_question_text(driver: webdriver.Chrome) -> str:
    """收集所有题干节点的 textContent，拼接为一个字符串。"""
    faces = driver.find_elements(By.CSS_SELECTOR, SELECTORS["question_faces"])
    # 使用 textContent 可拿到隐藏换行等，随后统一清洗
    raw = "\n".join(
        (el.get_attribute("textContent") or "").strip() for el in faces
    )
    # 压缩空白为单空格/单换行，避免上下文噪声
    raw = re.sub(r"\r?\n\s*\r?\n+", "\n", raw)
    raw = re.sub(r"[\t\x0b\x0c]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def ensure_editor_present(driver: webdriver.Chrome, timeout: int = DEFAULT_WAIT_SECONDS) -> None:
    """等待任一类型编辑器出现（TinyMCE/Monaco/textarea/contenteditable）。"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["any_editor_candidates"]))
        )
    except TimeoutException:
        # 不致命：有些题目可能在下方区域才出现编辑器
        logging.debug("未在超时时间内发现编辑器候选节点，继续尝试写入。")


def set_editor_content(driver: webdriver.Chrome, content: str, timeout: int = 6) -> bool:
    """向常见富文本/代码编辑器写入内容。

    支持：
    1) TinyMCE（遍历 tinymce.editors；仅目标 textarea.question-design-input）
    2) Monaco（常见 iframe 包装：#editorContainer / .code-editor / .monaco-editor）
    3) 纯 textarea（textarea.question-design-input）
    4) contenteditable 节点（#question_content 或 [contenteditable=true]）
    """
    w = WebDriverWait(driver, timeout)

    # ---- TinyMCE ----
    try:
        updated = driver.execute_script(
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
            iframe = w.until(EC.presence_of_element_located((By.CSS_SELECTOR, frame_css)))
            driver.switch_to.frame(iframe)
            try:
                applied = driver.execute_script(
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
                driver.switch_to.default_content()
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            return False

    for css in ("iframe#editorContainer", "iframe.code-editor", "iframe.monaco-editor"):
        if _try_monaco_in_frame(css):
            return True

    # ---- 纯 textarea ----
    try:
        ta = w.until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea.question-design-input")))
        driver.execute_script(
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
        # 优先 #question_content；后备 [contenteditable=true]
        target = None
        try:
            target = w.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#question_content")))
        except Exception:
            target = w.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[contenteditable='true']")))
        driver.execute_script(
            """
            var el = arguments[0], val = arguments[1];
            // 依据站点偏好：用 textContent 写纯文本
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


def try_click_save(driver: webdriver.Chrome) -> None:
    """如果存在保存按钮则点击。"""
    try:
        btn = WebDriverWait(driver, SHORT_WAIT_SECONDS).until(
            EC.element_to_be_clickable((By.ID, SELECTORS["save_button_id"]))
        )
        btn.click()
    except Exception:
        pass


def go_next_and_check_last(driver: webdriver.Chrome, old_face_el) -> bool:
    """点击“下一题”，等待旧题元素失效。如果出现“最后一题”弹窗则返回 True。"""
    next_btn = WebDriverWait(driver, DEFAULT_WAIT_SECONDS).until(
        EC.element_to_be_clickable((By.ID, SELECTORS["next_button_id"]))
    )
    next_btn.click()

    # 处理潜在弹窗
    is_last = False
    try:
        WebDriverWait(driver, SHORT_WAIT_SECONDS).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        msg = (alert.text or "").strip()
        if "最后一题" in msg:
            is_last = True
        alert.accept()
    except TimeoutException:
        pass

    # 等旧元素真正失效，避免引用旧题
    try:
        WebDriverWait(driver, DEFAULT_WAIT_SECONDS).until(EC.staleness_of(old_face_el))
    except TimeoutException:
        logging.debug("等待旧题失效超时，页面可能未刷新或选择器不匹配。")

    return is_last


# =============================
# 主流程
# =============================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    cfg = load_config()
    username = cfg["username"]
    password = cfg["password"]
    api_key = cfg["deepseek_api_key"]

    question_url = input("请输入答题链接：").strip()
    if not question_url:
        raise SystemExit("[fatal] 未输入答题链接。")

    language = input("请输入代码题编程语言（例如 C语言、C++、Java、Python 等）：").strip() or "C语言"

    client = init_llm_client(api_key)
    driver = build_driver()

    try:
        # ---------- 登录 ----------
        driver.get(question_url)
        time.sleep(0.3)
        user_box = driver.find_element(By.ID, SELECTORS["login_username_id"])
        pwd_box = driver.find_element(By.ID, SELECTORS["login_password_id"])
        user_box.clear(); user_box.send_keys(username)
        pwd_box.clear(); pwd_box.send_keys(password)
        time.sleep(0.2)
        driver.find_element(By.CSS_SELECTOR, SELECTORS["login_submit_css"]).click()
        time.sleep(0.6)

        wait = wait_for(driver)
        count = 1

        while True:
            logging.info("==== 第 %d 题 ====", count)

            # 确保题面加载
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["question_faces"])))
            faces = driver.find_elements(By.CSS_SELECTOR, SELECTORS["question_faces"])  # 留作 staleness 监控
            old_face_el = faces[0] if faces else None

            prompt_text = get_question_text(driver)
            logging.debug("题面：%s", prompt_text)

            ensure_editor_present(driver)

            # ---------- 调用 LLM ----------
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": f"请使用{language}完成以下需求，不要使用注释，不要使用代码块"},
                        {"role": "user", "content": prompt_text},
                    ],
                    stream=False,
                )
                if resp.choices[0].message.content is None:
                    raise Exception
                else:
                    answer = resp.choices[0].message.content.strip()
                    logging.info("LLM 返回 %d 字符", len(answer))
            except Exception as e:
                logging.exception("LLM 请求失败：%s", e)
                answer = ""  # 允许空写入尝试

            # ---------- 写入编辑器 ----------
            if not set_editor_content(driver, answer):
                logging.warning("未能写入富文本/代码编辑器，或未找到可写节点。")

            # 尝试保存
            try_click_save(driver)

            # 下一题
            if old_face_el is None:
                # 若无法拿到旧元素，仍然尝试直接下一题
                logging.debug("无法获取旧题元素引用，将直接翻题。")
            is_last = go_next_and_check_last(driver, old_face_el)
            if is_last:
                logging.info("[info] 已经是最后一题，退出。")
                break

            count += 1
            time.sleep(0.2)

    finally:
        # Windows 下保留 pause 体验
        if os.name == "nt":
            try:
                os.system("pause")
            except Exception:
                pass
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
