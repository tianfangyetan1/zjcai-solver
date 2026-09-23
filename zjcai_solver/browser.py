# -*- coding: utf-8 -*-
from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException


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
