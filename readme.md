# Zjcai Quiz Solvers — 使用指南

本仓库包含两份互不依赖的脚本，用于在浏览器中自动完成 zjcai.com 的在线题目，并调用 DeepSeek 自动填充答案：

1. **Refactored Quiz Solver（选择/判断/填空）**  — 处理单选/判断/填空题。
2. **Code-Question Solver（代码题）** — 处理代码类题目，向站点的编辑器（TinyMCE / Monaco / textarea / contenteditable）写入答案。

---

## 安装依赖

### 创建虚拟环境并安装

```bash
# macOS / Linux
python -m venv .venv
source ./.venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Windows PowerShell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

> 以上可满足脚本运行；Selenium 4.25+ 会通过 **Selenium Manager** 自动匹配并下载对应驱动，无需手动配置 chromedriver。

---

## 获取 DeepSeek API Key

1. 注册/登录 DeepSeek 平台，在控制台创建 **API Key**。
2. 复制生成的 Key（形如 `sk-...`）。
3. 将其写入仓库根目录的 `config.json`（见下节）。

> 这两份脚本通过 OpenAI SDK 指向 DeepSeek 兼容接口（`base_url=https://api.deepseek.com`），**无需**设置 `OPENAI_API_KEY` 环境变量。

---

## 配置 `config.json`

在仓库根目录创建 `config.json`：

```json
{
  "username": "你的登录用户名",
  "password": "你的登录密码",
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

* `username` / `password`：网站登录凭据（用于脚本自动填充登录表单）。
* `deepseek_api_key`：DeepSeek 的 API Key。

---

## 法律与合规

* 请确保遵守目标网站的**使用条款/学术诚信规范**。本代码仅用于学习与自动化技术研究，**不鼓励**在未获许可的场景中使用。
* 请勿在公开仓库中泄露账号、密码、API Key 等敏感信息。

---

## 版本固定（可选）

若你希望完全可复现，可固定版本：

```txt
selenium==4.25.0
openai==1.52.2
```
