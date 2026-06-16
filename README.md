# Hi Story

Hi Story 是一个本地运行的长篇小说写作工作台。它把作品设定、全书大纲、分卷规划、章节细纲、正文生成、审稿修订、资料库记忆和文稿导出放在同一个 Web 界面里。

项目默认使用 SQLite 保存数据。作品、章节、运行记录和导出文件都留在本机，不依赖云端数据库。你可以先用 `mock_mode` 跑通流程，也可以接入兼容 OpenAI API 格式的模型服务进行真实生成。

## 功能

- **作品设定**：维护书名、题材、平台、目标字数、创意、风格和基础设定。
- **题材契约卡**：每本书保存一张短契约卡，用来约束题材核心、读者期待、冲突来源、章节回报、开头偏好和避雷点。
- **设定锁定**：设定确认后可以锁定，避免后续误改基础信息和整本契约。
- **大纲与分卷**：生成全书大纲、分卷大纲和章节任务单，支持人工编辑。
- **自动换卷**：生成章节细纲时，系统会根据当前卷章数、退出条件、里程碑和未回收伏笔判断是否进入下一卷，并进行程序校验。
- **正文生成**：支持正式生成和快速试稿。正式生成会走写作、审稿、修订和质量检查。
- **质量闸门**：检查章节标题泄漏、短摘要、字数偏差、空泛章尾、模板句、破折号滥用和开篇承接问题。
- **问题稿**：未通过质量闸门的正文会保存为问题稿，仍可在前端查看、修改，并可由作者保存为最终稿。
- **资料库记忆**：将通过质量检查的章节沉淀到人物、世界观、伏笔、时间线和历史资料中。
- **运行记录**：记录本次操作、Agent 调用、生成任务状态和 token 估算。
- **文稿导出**：支持 TXT 和 DOCX，可导出整本、单章或章节范围。Web 导出前会检查缺章、空章和问题稿。

## 环境要求

- Python 3.10+
- Windows、macOS 或 Linux
- 可选：兼容 OpenAI API 格式的模型服务

安装依赖：

```bash
python -m pip install -r requirements.txt
```

## 快速开始

初始化数据库：

```bash
python main.py init-db
```

启动 Web 工作台：

```bash
python main_web.py
```

Windows 用户也可以双击：

```text
Hi Story.bat
```

默认配置可以使用 `mock_mode`。在 mock 模式下，不需要 API Key，也可以检查页面、流程和数据写入是否正常。

## 本地服务令牌

Web 服务启动时会生成一个随机令牌，并注入到前端页面。除 `/api/health` 外，所有本地 API 请求都需要携带 `X-HiStory-Token`。

这个令牌用于防止其他网页误打或恶意调用本机接口。正常使用时不需要手动填写。如果页面提示“本地页面令牌无效”，通常是浏览器还连着旧后台：

1. 关闭旧的 Hi Story 后台进程。
2. 重新启动 `Hi Story.bat` 或 `python main_web.py`。
3. 刷新浏览器页面。

## 配置

首次运行时，程序会在项目根目录生成 `config.json`。该文件保存模型服务地址、API Key、模型名称和运行参数。

示例：

```json
{
  "model_provider": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "wire_api": "chat_completions",
  "requires_openai_auth": true,
  "api_key": "",
  "default_model": "gpt-4o-mini",
  "review_model": "gpt-4o-mini",
  "agent_models": {
    "planner": "gpt-4o-mini",
    "writer": "gpt-4o-mini",
    "reviewer": "gpt-4o-mini",
    "reviser": "gpt-4o-mini",
    "memory": "gpt-4o-mini"
  },
  "model_reasoning_effort": "medium",
  "disable_response_storage": true,
  "model_context_window": 1000000,
  "model_auto_compact_token_limit": 900000,
  "temperature": 0.8,
  "timeout": 300,
  "max_retries": 2,
  "max_output_tokens": 12000,
  "use_system_proxy": false,
  "proxy_url": "",
  "mock_mode": true
}
```

常用字段：

- `base_url`：模型服务地址。
- `api_key`：模型服务密钥。
- `wire_api`：请求协议，可选 `chat_completions` 或 `responses`。
- `default_model`：默认模型。
- `review_model`：审稿模型。为空时使用默认模型或 `agent_models.reviewer`。
- `agent_models`：为 planner、writer、reviewer、reviser、memory 分别指定模型。
- `model_reasoning_effort`：部分模型支持的推理强度。
- `disable_response_storage`：是否要求服务端不保存响应。
- `model_context_window`：模型上下文窗口估算值。
- `model_auto_compact_token_limit`：上下文自动压缩阈值。
- `temperature`：生成温度。
- `timeout`：单次请求超时时间，单位为秒。
- `max_output_tokens`：最大输出 token。
- `mock_mode`：是否使用模拟输出。

也可以用命令行修改配置：

```bash
python main.py set-config --base-url "https://api.openai.com/v1" --api-key "YOUR_API_KEY" --default-model "gpt-4o-mini" --mock-mode false
```

`config.json` 包含 API Key，已经被 `.gitignore` 忽略。不要把它提交到 GitHub。

## Web 使用流程

推荐从 Web 界面完成完整写作流程：

1. 新建文章，填写基础信息、创意和风格。
2. 生成设定草稿，确认无误后采用入库。
3. 检查题材契约卡，必要时手动补充读者期待、冲突来源和避雷点。
4. 生成全书大纲和分卷大纲。
5. 生成章节细纲。系统会在这一步判断是否需要自动换卷。
6. 进入写作页，载入章节。
7. 使用正式生成或快速试稿生成正文。
8. 如果生成结果变成问题稿，可以修改后保存为最终稿，也可以直接保存为最终稿。
9. 最终稿通过质量闸门后，再生成记忆入库。
10. 导出 TXT 或 DOCX。

## 自动换卷

生成章节细纲时，系统会先判断当前卷是否应该继续。判断依据包括：

- 当前卷已有章数。
- 是否达到 `min_chapters`。
- 是否接近 `target_chapters`。
- 是否超过 `soft_max_chapters`。
- 是否达到 `hard_max_chapters`。
- 当前卷 `exit_condition` 是否完成。
- `required_milestones` 完成情况。
- 当前卷仍未回收的伏笔和人物线。

程序会做硬校验：

- 未达到 `min_chapters` 时不能换卷。
- 达到 `hard_max_chapters` 时会强制进入下一卷或要求收束。
- 不能跳卷。
- 下一卷必须存在。

如果发生换卷，前端会显示切换提示。章节编号仍按全书连续编号，不会在新卷重新从第 1 章开始。

## 问题稿和质量闸门

问题稿是“已生成但未通过质量闸门”的正文。它不会被丢弃，仍会显示在前端，方便修改和对照。

问题稿默认不会直接用于：

- 下一章上下文承接。
- 正式导出。

这样做是为了避免坏稿自动污染后续章节。如果你认可问题稿，可以直接在写作页保存为最终稿。生成记忆时，如果当前章节仍是问题稿且没有最终稿，系统会先把当前问题稿保存为最终稿，再生成记忆。

手动保存时，质量闸门只做提醒，不再因为开头承接、破折号、模板句、字数偏差等问题阻止保存。只有正文为空、明显混入 JSON、Markdown 代码块或结构化协议内容时，才会拒绝保存。

质量闸门重点检查：

- 开头是否承接上一章结尾。
- 是否复制细纲句子当正文。
- 是否频繁使用“不是……而是……”等模板句。
- 是否滥用破折号。
- 是否出现空泛总结式结尾。
- 是否过短、像摘要或任务说明。
- 是否泄漏章节标题或 JSON 痕迹。

## 导出

Web 导出支持：

- 整本导出。
- 单章导出。
- 章节范围导出。
- TXT。
- DOCX。

导出前会检查章节完整性。缺章、空章和没有最终稿的问题稿会阻止导出，并返回具体章节号。勾选草稿兜底时，普通草稿可以作为兜底内容，但问题稿不会被当作正式可导出内容。

CLI 导出命令更适合快速导出和脚本调用。需要严格检查缺章和问题稿时，优先使用 Web 导出。

## CLI 用法

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

连续生成多章正文：

```bash
python main.py generate-chapters --work-id 1 --start 1 --count 3
```

生成后自动写入记忆：

```bash
python main.py generate-chapter --work-id 1 --chapter 1 --apply-memory
```

跳过审稿或修订：

```bash
python main.py generate-chapter --work-id 1 --chapter 1 --skip-review
python main.py generate-chapter --work-id 1 --chapter 1 --skip-revise
```

导出文稿：

```bash
python main.py export-txt --work-id 1
python main.py export-docx --work-id 1
python main.py export-chapter-txt --work-id 1 --chapter 1
python main.py export-chapter-docx --work-id 1 --chapter 1
```

## 项目结构

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
├── data/                 # 本地作品数据
├── main.py               # CLI 入口
├── main_web.py           # Web 启动入口
├── Hi Story.bat          # Windows 启动脚本
├── Hi Story.png          # Logo
└── requirements.txt
```

## 数据存储

Hi Story 默认将数据保存在项目本地：

- `config.json`：模型服务配置，包含 API Key。
- `data/`：作品索引、每本作品的 SQLite 数据库、运行记录和导出目录。
- `data/works/<作品>/work.db`：单本作品的主要数据库。
- `data/works/<作品>/exports/`：该作品的导出文件。
- `data/logs/server.url`：当前本地服务地址和启动令牌。

这些文件是本地运行数据，不是源码。请按自己的方式备份重要作品。

## 开发检查

后端使用 Python 标准库 `http.server` 提供本地服务，数据层使用 SQLite。前端使用原生 HTML、CSS 和 JavaScript，不需要构建步骤。

常用检查：

```bash
python -B -c "import app.web.server; print('server import ok')"
python -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['app/web/server.py','app/web/state.py','app/services/ai_client.py']]"
node --check web/app.js
```

如果没有安装 Node.js，可以跳过 JavaScript 语法检查。

## 注意事项

- `config.json`、`data/`、数据库文件和导出文件不要提交到 GitHub。
- 取消生成时，系统会尽量关闭本地请求，并阻止迟到结果入库；已经发出的模型请求不一定能在服务商侧立刻停止。
- 多个长任务会使用独立的 workflow 和 AI client，减少并发串状态的风险。
- 质量闸门不能替代人工审稿。它负责拦截明显坏稿，最终文本仍需要作者判断。
- 当前仓库暂未附带 LICENSE 文件。
