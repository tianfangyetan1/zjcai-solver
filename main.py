# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import sys

from zjcai_solver.browser import build_driver
from zjcai_solver.config import load_config
from zjcai_solver.constants import DEFAULT_WAIT_SECONDS
from zjcai_solver.llm import DeepSeekClient
from zjcai_solver.notify import notify_exam_finished
from zjcai_solver.solver import QuizSolver


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    cfg = load_config()

    question_url = input("请输入答题链接：").strip()
    if not question_url:
        raise SystemExit("未输入答题链接，已退出。")

    language = input("请输入编程语言（例如 C语言、C++、Java、Python 等）：").strip() or "C语言"

    llm = DeepSeekClient(
        api_key=cfg.api_key,
        model=cfg.model,
        reasoning_effort=cfg.reasoning_effort,
    )
    driver = build_driver(cfg.chromedriver_path)

    try:
        solver = QuizSolver(
            driver=driver,
            llm=llm,
            language=language,
            wait_seconds=DEFAULT_WAIT_SECONDS,
        )
        solver.login(question_url, cfg.username, cfg.password)
        solver.run()

        notify_exam_finished(
            title="自动答题已完成",
            message=f"{question_url} 已完成自动作答。"
        )
    finally:
        if os.name == "nt":
            os.system("pause")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
