# Zjcai Solvers — 使用指南

本仓库包含两份互不依赖的脚本，用于在浏览器中自动完成 [zjcai.com](https://zjcai.com) 的在线题目，并调用 DeepSeek API 自动填充答案：

1. `quiz_solver_mc_fill.py` — 处理单选/判断/填空题
2. `quiz_solver_code.py` — 处理代码类题目，向站点的编辑器写入答案

## 安装依赖

使用以下任意一种方式即可

### 直接安装（方便）

```bash
pip install -r requirements.txt
```

### 创建虚拟环境并安装（环境隔离）

#### macOS / Linux

```bash
python -m venv .venv
source ./.venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

#### Windows PowerShell

```bash
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

> Selenium 4.25+ 会通过 Selenium Manager 自动匹配并下载对应驱动，无需手动配置 chromedriver。

## 获取 DeepSeek API Key

1. 注册/登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，创建 **API Key** 并充值。
2. 复制生成的 Key（形如 `sk-...`）。
3. 将其写入仓库根目录的 `config.json`（见下节）。

## 配置 `config.json`

编辑仓库根目录下的 `config.json`：

```json
{
  "username": "你的登录用户名",
  "password": "你的登录密码",
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

- `username` / `password`：网站登录凭据（用于脚本自动填充登录表单）。
- `deepseek_api_key`：DeepSeek 的 API Key。

## 版本固定（可选）

若你希望完全可复现，可固定版本：

```txt
selenium==4.25.0
openai==1.52.2
```
