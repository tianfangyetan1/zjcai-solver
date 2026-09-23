# Zjcai Solver

[![GitHub Release](https://img.shields.io/github/v/release/tianfangyetan1/zjcai-solver)](https://github.com/tianfangyetan1/zjcai-solver/releases/latest)
[![GitHub Release Date](https://img.shields.io/github/release-date/tianfangyetan1/zjcai-solver)](https://github.com/tianfangyetan1/zjcai-solver/releases/latest)

此脚本用于自动完成 [zjcai.com](https://zjcai.com) 的在线题目。通过 Python Selenium 操作浏览器，然后调用 DeepSeek API 获取答案。

## 题型适配情况

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

### 1. 安装所需模块

```bash
pip install -r requirements.txt
```

### 2. 获取 DeepSeek API Key

1. 注册/登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，创建 API Key 并充值。
   
2. 复制生成的 API Key（形如 `sk-...`）。
   
3. 将其写入仓库根目录的 `config.json`（见第 4 节）。

### 3. 配置 Chrome Driver（可选）

1. 前往 [Chrome for Testing availability](https://googlechromelabs.github.io/chrome-for-testing/#stable) 下载和你的 Chrome 大版本相同的 Chrome Driver。
   
2. 将下载后的 `chromedriver.exe` 保存在合适的位置，并将路径填入 `config.json`（见第 4 节）。

### 4. 修改配置文件

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
  "llm-model": "deepseek-flash",  // 答题使用的模型
  "reasoning-effort": "high",     // 思考强度
  "chromedriver-path": ""         // Chrome Driver 的路径（可选）
}
```

> [!IMPORTANT]
> 题目中的图片依赖模型的图像理解能力，目前只有 `deepseek-flash` 支持，请不要改成 `deepseek-v4-pro`。

## 常见问题

### 1. 启动很慢怎么办？

默认情况下，Selenium 会在运行时自动下载合适的 Chrome Driver 版本。如果下载速度很慢，可以[手动下载并配置路径](https://github.com/tianfangyetan1/zjcai-solver?tab=readme-ov-file#4-%E9%85%8D%E7%BD%AE-chrome-driver%E5%8F%AF%E9%80%89)。

### 2. LLM 生成的回答质量较差怎么办？

调高 `config.json` 中的 `reasoning-effort`，模型会思考得更久，回答质量更好，但速度会变慢、消耗的 token 更多。

可选值为 `minimal` / `low` / `medium` / `high` / `xhigh` / `max` / `ultra`，默认 `high`。实际映射关系：`minimal`、`low` → 低强度，`medium`、`high`、`xhigh` → 高强度，`max`、`ultra` → 最高强度。

### 3. 题目中的图片是怎么处理的？

图片会随题目一起上传给模型，题面文本中以 `[图片1]`、`[图片2]` 的形式标注其原本所在位置。无需安装任何本地识别模块。
