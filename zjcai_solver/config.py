# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# DeepSeek 支持的思考强度取值（详见 https://api-docs.deepseek.com/zh-cn/guides/thinking_mode）
VALID_REASONING_EFFORTS = ("low", "high", "max")

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_REASONING_EFFORT = "high"

# 配置文件位于仓库根目录（本文件的上上级），这样从任意工作目录运行都能找到
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class AppConfig:
    username: str
    password: str
    api_key: str
    model: str
    reasoning_effort: str
    chromedriver_path: str


def load_config(cfg_path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """读取并校验 config.json。"""
    if not cfg_path.exists():
        raise SystemExit(f"找不到配置文件：{cfg_path}")

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"config.json 不是合法的 JSON：{e}")

    account_cfg = cfg.get("account")
    if not isinstance(account_cfg, dict):
        raise SystemExit("config.json 缺少 account 参数或格式不正确")

    username = account_cfg.get("username", "")
    password = account_cfg.get("password", "")
    api_key = cfg.get("deepseek-api-key", "")
    if not (username and password and api_key):
        raise SystemExit("config.json 缺少必要字段（username/password/deepseek-api-key）")

    model = (cfg.get("llm-model") or DEFAULT_MODEL).strip()

    reasoning_effort = (cfg.get("reasoning-effort") or DEFAULT_REASONING_EFFORT).strip()
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        raise SystemExit(
            f"config.json -> reasoning-effort 取值不合法：{reasoning_effort}，"
            f"可选值为 {'/'.join(VALID_REASONING_EFFORTS)}"
        )

    return AppConfig(
        username=username,
        password=password,
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
        chromedriver_path=cfg.get("chromedriver-path", ""),
    )
