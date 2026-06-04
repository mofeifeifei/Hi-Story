# Hi Story

Hi Story 是一个本地运行的 AI 长篇小说写作工作台。它把作品设定、大纲规划、章节细纲、正文生成、审稿修订、资料库记忆和文稿导出整合到一个 Web 界面中，帮助作者更稳定地推进长篇创作。

项目默认使用本地 SQLite 保存作品数据。你可以在 mock 模式下先体验完整流程，也可以接入兼容 OpenAI API 的模型服务进行真实生成。

## Features

- **作品设定管理**：维护书名、题材、平台、目标字数、创意、风格控制和整本契约。
- **设定保护**：锁定作品设定后，基础信息、风格和整本契约不可误改。
- **AI 设定草稿**：根据创意生成简介、人物、世界观规则、卖点和可读设定稿。
- **大纲与细纲**：生成全书大纲、分卷大纲和章节任务单，支持人工编辑。
- **章节写作流程**：支持正文生成、审稿、修订和最终稿保存。
- **资料库记忆**：将章节变化沉淀到人物、世界观、伏笔、时间线和历史资料中。
- **运行记录**：记录本次操作、Agent 调用和生成任务状态。
- **文稿导出**：支持 TXT 和 DOCX，可导出整本、单章或章节范围。

## Screenshots

> 可以在这里补充 Web 工作台截图，例如设定页、大纲页、写作页和资料库页。

## Requirements

- Python 3.10+
- Windows、macOS 或 Linux
- 可选：兼容 OpenAI API 的模型服务

安装依赖：

```bash
python -m pip install -r requirements.txt
```

## Quick Start

启动 Web 工作台：

```bash
python main_web.py
```

Windows 用户也可以双击：

```text
Hi Story.bat
```

初始化数据库：

```bash
python main.py init-db
```

默认配置启用 `mock_mode`，即使没有模型 API Key，也可以先体验主要流程。

## Configuration

首次运行时，程序会在项目根目录生成 `config.json`。该文件用于保存模型服务地址、API Key、模型名称和运行参数。

示例：

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

常用配置：

- `base_url`：模型服务地址。
- `api_key`：模型服务密钥。
- `default_model`：默认模型名称。
- `wire_api`：请求协议，可选 `chat_completions` 或 `responses`。
- `mock_mode`：是否使用模拟输出。
- `agent_models`：为 planner、writer、reviewer、reviser、memory 分别指定模型。

也可以通过命令行修改配置：

```bash
python main.py set-config --base-url "https://api.openai.com/v1" --api-key "YOUR_API_KEY" --default-model "gpt-4o-mini" --mock-mode false
```

## Web Workflow

推荐使用 Web 界面完成完整创作流程：

1. 新建文章，填写基础信息、风格控制和整本契约。
2. 生成设定草稿，确认后采用入库。
3. 生成或编辑全书大纲与分卷大纲。
4. 生成章节细纲，形成可执行的章节任务单。
5. 进入写作页，载入章节并生成正文。
6. 查看审稿结果，按需要修订并保存最终稿。
7. 生成记忆入库，更新人物状态、伏笔、时间线和资料库。
8. 导出 TXT 或 DOCX 文稿。

## CLI Usage

列出作品：

```bash
python main.py list-works
```

查看作品资料包：

```bash
python main.py show-work --work-id 1
```

创建作品：

```bash
python main.py create-work --title "示例小说" --idea "一句话创意" --genre "历史穿越" --platform "起点" --target-words 500000
```

生成全书大纲：

```bash
python main.py generate-outline --work-id 1
```

生成章节细纲：

```bash
python main.py generate-chapter-outlines --work-id 1 --start 1 --count 3
```

生成单章正文：

```bash
python main.py generate-chapter --work-id 1 --chapter 1
```

导出文稿：

```bash
python main.py export-txt --work-id 1
python main.py export-docx --work-id 1
```

## Project Structure

```text
Hi Story/
├── app/
│   ├── core/             # JSON 契约与结构规范
│   ├── database/         # SQLite schema、迁移和仓库层
│   ├── exporters/        # TXT / DOCX 导出
│   ├── prompts/          # 各 Agent 使用的提示词
│   ├── services/         # AI 客户端和 Agent 实现
│   ├── utils/            # 配置、格式化、校验和上下文工具
│   └── web/              # 本地 Web API
├── web/                  # 前端页面、样式和交互脚本
├── main.py               # CLI 入口
├── main_web.py           # Web 启动入口
├── Hi Story.bat          # Windows 启动脚本
├── Hi Story.png          # Logo
└── requirements.txt
```

## Data Storage

Hi Story 默认将数据保存在项目本地：

- `config.json`：模型服务配置。
- `data/`：作品索引、每本作品的 SQLite 数据库、章节、设定和运行记录。
- `exports/`：导出的 TXT 或 DOCX 文稿。

这些文件属于本地运行数据，不是项目源码的一部分。请根据自己的备份策略保存重要作品。

## Development

后端使用 Python 标准库 `http.server` 提供本地 Web 服务，数据层使用 SQLite。前端使用原生 HTML、CSS 和 JavaScript，不需要额外构建步骤。

常用检查：

```bash
python -B -c "import app.web.server; print('server import ok')"
node --check web/app.js
```

如果没有安装 Node.js，可以跳过 JavaScript 语法检查。

## Roadmap

- 更完善的配置模板和首次启动引导。
- 更细致的资料库编辑体验。
- 更稳定的长篇上下文压缩策略。
- 更多导出样式和排版模板。

## License

当前仓库暂未附带 LICENSE 文件。若你希望以开源协议分发，请在仓库中添加明确的许可证文件。
