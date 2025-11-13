# Zjcai Solvers

本仓库包含两份互不依赖的脚本，用于在浏览器中自动完成 [zjcai.com](https://zjcai.com) 的在线题目，并调用 DeepSeek API 自动填充答案：

1. `quiz_solver_mc_fill.py` - 处理单选/判断/填空题
2. `quiz_solver_code.py` - 处理代码类题目，向网站的编辑器写入答案

## TODO

- [ ] 增加题目图片识别

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 获取 DeepSeek API Key

1. 注册/登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，创建 API Key 并充值。
2. 复制生成的 API Key（形如 `sk-...`）。
3. 将其写入仓库根目录的 `config.json`（见第 4 节）。

### 3. 配置 Chrome Driver（可选）

前往 [Chrome for Testing availability](https://googlechromelabs.github.io/chrome-for-testing/#stable) 下载和你的 Chrome 大版本相同的版本。
将下载后的文件保存在合适的位置，并将路径填入 `config.json`（见第 4 节）。

### 4. 修改配置文件

编辑仓库根目录下的 `config.json`：

```json
{
  "username": "该网站的用户名",
  "password": "该网站的密码",
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
  "chromedriver_path": "ChromeDriver 的路径（可选）"
}
```

## 常见问题

### 启动很慢怎么办？

默认情况下，selenium 会在运行时自动下载合适的 ChromeDriver 版本。如果下载速度很慢，可以手动下载并配置路径。
