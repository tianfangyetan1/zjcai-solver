# Zjcai Solver

[![GitHub Release](https://img.shields.io/github/v/release/tianfangyetan1/zjcai-solver)](https://github.com/tianfangyetan1/zjcai-solver/releases/latest)
[![GitHub Release Date](https://img.shields.io/github/release-date/tianfangyetan1/zjcai-solver)](https://github.com/tianfangyetan1/zjcai-solver/releases/latest)

此脚本用于自动完成 [zjcai.com](https://zjcai.com) 的在线题目。通过 Python Selenium 操作浏览器，然后调用 DeepSeek API 获取答案。

## TODO

- [x] 题目图片识别
- [x] 对每种题型单独设置是否开启深度思考

### 题型适配情况

- [x] 单选题/判断题
- [x] 填空题
  - [x] 多个填空的情况
- [x] 程序设计题
  - [x] 获取题目中给出的代码片段

## 使用方法

### 0. 前置条件

- 克隆本仓库
- 安装 [Python](https://www.python.org/)
- 安装 [Chrome](https://www.google.com/chrome/?standalone=1&platform=win64)
- （可选，但是推荐使用）安装 [VS Code](https://code.visualstudio.com/) 或者 [PyCharm](https://www.jetbrains.com/zh-cn/pycharm/)

### 1. 安装 Microsoft Visual C++ Build Tools（可选）

如果你不需要识别图片中的公式，可以跳过此步骤。

1. 下载 [Build Tools for Visual Studio](https://visualstudio.microsoft.com/zh-hant/visual-cpp-build-tools/)。
   
2. 安装时勾选“使用 C++ 的桌面开发 (Desktop development with C++)”这一整块，或者至少包含：MSVC v14.x 生成工具、Windows 10/11 SDK。

### 2. 安装所需模块

- 包含图片公式识别

  ```bash
  pip install -r requirements.txt
  ```

- 不包含图片公式识别

  ```bash
  pip install -r requirements-without-latex.txt
  ```

### 3. 获取 DeepSeek API Key

1. 注册/登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，创建 API Key 并充值。
   
2. 复制生成的 API Key（形如 `sk-...`）。
   
3. 将其写入仓库根目录的 `config.json`（见第 5 节）。

### 4. 配置 Chrome Driver（可选）

1. 前往 [Chrome for Testing availability](https://googlechromelabs.github.io/chrome-for-testing/#stable) 下载和你的 Chrome 大版本相同的 Chrome Driver。
   
2. 将下载后的 `chromedriver.exe` 保存在合适的位置，并将路径填入 `config.json`（见第 5 节）。

### 5. 修改配置文件

编辑仓库根目录下的 `config.json`（不要添加注释）

> [!TIP]
> 本项目支持 Schemas JSON，将鼠标移动到属性名称上即可查看说明，支持格式校验。

```js
{
  "account": {
    "username": "",   // 该网站的用户名
    "password": ""    // 该网站的密码
  },
  "deepseek-api-key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
  "llm-models": {
    "normal": "deepseek-chat",      // 未启用深度思考
    "reasoner": "deepseek-reasoner" // 启用深度思考
  },
  "enable-reasoning": {    // 分题型控制是否启用深度思考
    "single-or-judge": false,   // 单选 / 判断题
    "fill-blank": false,        // 填空题
    "programming": false        // 代码 / SQL / 程序设计等大题
  },
  "chromedriver-path": "",   // Chrome Driver 的路径（可选）
  "enable-latex-ocr": true   // 启用 Latex 公式识别（默认为false）
}
```

## 常见问题

### 1. 启动很慢怎么办？

默认情况下，Selenium 会在运行时自动下载合适的 Chrome Driver 版本。如果下载速度很慢，可以[手动下载并配置路径](https://github.com/tianfangyetan1/zjcai-solver?tab=readme-ov-file#4-%E9%85%8D%E7%BD%AE-chrome-driver%E5%8F%AF%E9%80%89)。

### 2. 初始化 LaTeX-OCR 模型时卡住怎么办？

首次使用需要下载模型数据，~~成为*魔法少女*可以加快这一步骤~~。

### 3. LLM 生成的回答质量较差怎么办？

默认不开启深度思考，开启深度思考可以提升回答质量，但是回答速度会变慢，而且消耗的 token 更多。

`config.json` 中 `enable_reasoning` 配置项可以分别设置每种题型是否开启深度思考。
