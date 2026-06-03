# Hi Story

Hi Story 是一个面向长篇小说创作的本地 AI 写作工作台。它把设定、整本契约、大纲、章节细纲、正文生成、审稿修订、记忆入库和导出整合在同一个 Web 界面中，适合用来管理连续创作项目。

项目默认在本地运行，作品数据保存在本机 SQLite 数据库中。你可以使用 mock 模式体验流程，也可以配置自己的模型接口进行真实生成。

## 功能特性

- **设定工作台**：维护作品基础信息、风格控制和整本契约，锁定后可防止误改核心设定。
- **设定草稿生成**：根据创意生成书名候选、简介、人物、世界观规则和核心卖点。
- **大纲与细纲**：生成全书大纲、分卷大纲和章节任务单，并支持手动编辑。
- **正文生成流程**：按章节生成正文，可选择只生成、生成并审稿、生成审稿后修订。
- **审稿与修订**：检查承接、爽点兑现、历史质感、人物一致性和章节钩子。
- **记忆入库**：把章节变化同步到人物、时间线、伏笔、历史资料等资料库。
- **资料库管理**：维护人物、世界观、伏笔、时间线和历史资料。
- **导出**：支持导出 TXT 和 DOCX，可导出整本、单章或章节范围。
- **运行记录**：记录本次操作、Agent 调用历史和生成任务流水，方便追踪问题。

## 项目结构

```text
Hi Story/
├── app/                  # Python 后端、工作流、数据库、Agent 和导出逻辑
│   ├── core/             # JSON 契约和结构规范
│   ├── database/         # SQLite schema、迁移和仓库层
│   ├── exporters/        # TXT / DOCX 导出
│   ├── prompts/          # Planner / Writer / Reviewer 等提示词
│   ├── services/         # AI 客户端和各类 Agent
│   ├── utils/            # 配置、格式化、校验、上下文过滤
│   └── web/              # 本地 Web 服务和 API
├── web/                  # 前端页面、样式和交互脚本
├── main.py               # 命令行入口
├── main_web.py           # Web 工作台入口
├── Hi Story.bat          # Windows 一键启动脚本
├── Hi Story.png          # 项目 logo
├── requirements.txt      # Python 依赖
└── .gitignore
```

运行后会自动生成本地文件：

```text
config.json              # 本地模型配置，包含 API Key，默认不提交
data/                    # 本地作品数据库和生成数据，默认不提交
```

## 环境要求

- Python 3.10 或更高版本
- Windows、macOS 或 Linux
- 可选：支持 OpenAI 兼容接口的模型服务

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 快速启动

### Windows

双击运行：

```text
Hi Story.bat
```

或者在项目目录执行：

```powershell
python main_web.py
```

默认会启动本地 Web 服务，并打开浏览器。

### 命令行初始化

```powershell
python main.py init-db
```

如果只是想先体验流程，可以保持 `mock_mode` 为 `true`，不需要配置真实 API Key。

## 模型配置

首次运行时，程序会根据默认配置生成 `config.json`。你也可以手动创建或修改它。

示例配置：

```json
{
  "model_provider": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "wire_api": "chat_completions",
  "api_key": "",
  "default_model": "gpt-4o-mini",
  "mock_mode": true,
  "timeout": 300,
  "max_retries": 2,
  "max_output_tokens": 12000,
  "use_system_proxy": false,
  "proxy_url": ""
}
```

常用字段说明：

- `base_url`：模型接口地址，需兼容 OpenAI Chat Completions 或 Responses API。
- `api_key`：你的模型服务密钥。不要提交到 GitHub。
- `default_model`：默认使用的模型名称。
- `wire_api`：可选 `chat_completions` 或 `responses`。
- `mock_mode`：为 `true` 时使用内置模拟输出，适合演示和测试流程。
- `agent_models`：可分别指定 planner、writer、reviewer、reviser、memory 使用的模型。

也可以通过命令行修改配置：

```powershell
python main.py set-config --base-url "https://api.openai.com/v1" --api-key "你的密钥" --default-model "gpt-4o-mini" --mock-mode false
```

## Web 工作流

推荐使用 Web 工作台完成创作：

1. 在左侧新建或选择文章。
2. 在“设定”页填写基础信息、风格控制和整本契约。
3. 点击“保存基础信息”，再生成并采用设定草稿。
4. 进入“大纲与细纲”页，生成全书大纲和章节细纲。
5. 进入“写作”页，载入章节并生成正文。
6. 根据审稿结果修订，确认后保存最终稿。
7. 生成记忆入库，沉淀人物状态、伏笔、时间线和历史资料。
8. 在“导出”页导出 TXT 或 DOCX。

## 常用命令

列出作品：

```powershell
python main.py list-works
```

查看作品资料包：

```powershell
python main.py show-work --work-id 1
```

创建作品并生成基础设定：

```powershell
python main.py create-work --title "示例小说" --idea "一句话创意" --genre "历史穿越" --platform "起点" --target-words 500000
```

生成全书大纲：

```powershell
python main.py generate-outline --work-id 1
```

生成章节细纲：

```powershell
python main.py generate-chapter-outlines --work-id 1 --start 1 --count 3
```

生成单章正文：

```powershell
python main.py generate-chapter --work-id 1 --chapter 1
```

导出整本：

```powershell
python main.py export-txt --work-id 1
python main.py export-docx --work-id 1
```

## 数据与隐私

本项目默认把用户数据保存在本地：

- `config.json`：模型配置和 API Key。
- `data/`：作品数据库、章节、设定、资料库和运行记录。
- 导出文件：通常位于作品目录下的 exports 目录。

这些文件已经在 `.gitignore` 中排除。开源或提交代码前，请务必检查：

```powershell
git status
git diff --cached --name-only
rg -n "sk-|api_key|password|token|Authorization|Bearer" .
```

如果曾经把真实 API Key 提交到 Git 历史中，请立即在服务商后台重置密钥，并清理仓库历史。

## 开发说明

后端使用 Python 标准库 `http.server` 提供本地 Web API，数据层使用 SQLite。前端是原生 HTML、CSS 和 JavaScript，不需要额外构建步骤。

运行基本检查：

```powershell
python -B -c "import app.web.server; print('server import ok')"
node --check web/app.js
```

如果没有安装 Node.js，可以跳过 `node --check`。

## 开源建议

建议提交到 GitHub 的文件包括：

```text
app/
web/
main.py
main_web.py
Hi Story.bat
Hi Story.png
requirements.txt
README.md
.gitignore
```

不要提交：

```text
config.json
data/
__pycache__/
*.pyc
*.db
*.sqlite
exports/
```

## License

如果你希望别人可以自由使用、修改和分发，可以添加 MIT License。当前仓库尚未附带 LICENSE 文件时，默认仍然保留作者版权，别人不能自动获得开源授权。
