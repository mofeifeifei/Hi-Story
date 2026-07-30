# Hi Story

Hi Story 是一个本地运行的长篇小说写作工作台。它将作品设定、分卷大纲、章节细纲、正文生成、审稿修订、记忆入库和文稿导出放在同一个界面中，适合需要长期维护剧情上下文的连载创作。

作品数据库、导出文件和运行记录默认保存于本机。关闭 `mock_mode` 后，当前任务所需的设定、细纲、正文和修订指令会发送给你在 `config.json` 中配置的模型服务。

本项目采用 [MIT License](LICENSE) 开源，允许使用、复制、修改、发布、分发和商用；分发副本或衍生版本时，请保留许可证与版权声明。

## 功能

- **作品设定**：维护书名、题材、平台、创意、目标字数、风格、读者定位和锁定事实。
- **题材契约卡**：每本书保存简短契约，用来约束读者期待、冲突来源、章节回报、开头偏好和避雷项。
- **大纲与分卷**：生成全书大纲、分卷规划和可编辑的章节任务单；细纲包含场景目标、阻力、信息增量、情绪变化与场景出口。
- **自动换卷**：生成细纲时，模型先判断是否换卷；程序再根据章节数量、退出条件、里程碑、伏笔和下一卷状态进行校验。
- **章节生成**：正式生成会结合章节交接、题材契约、细纲、人物状态、伏笔和近期章首章尾避重记录；也支持快速试稿。
- **承接与避重**：上下章通过动作、物件、对白、证据和未解决问题交接，检查近期章首、章尾、标题和常见句式的重复风险。
- **审稿与修订**：审稿结果会整理为可复制的中文修订话术；修订稿出现风格退化时保留为候选稿，不直接覆盖最终稿。
- **问题稿与版本**：未通过自动质量检查的文本仍会保存并显示，可继续编辑、修订或由作者确认保存为最终稿；手动保存前会保留旧版本。
- **记忆入库**：从最终稿提取人物、关系、伏笔、时间线和章节接力棒，供后续章节使用。
- **标题与导出**：根据正文实际发生的行动、发现、选择或代价生成标题候选，支持 TXT、DOCX、整本、单章和范围导出。
- **运行记录**：记录任务状态、智能体调用、耗时和令牌估算，页面将内部技术字段转换为中文显示。

## 使用流程

1. 新建作品，填写基础信息和一句话创意。
2. 生成设定草稿，确认后采用入库；必要时锁定作品设定。
3. 检查题材契约卡，补足读者期待、冲突发动机和避雷项。
4. 生成全书大纲和分卷规划。
5. 生成章节细纲。系统会在此评估是否需要进入下一卷。
6. 在“写作”页载入章节，生成正文或编辑已有正文。
7. 查看右侧“修订”面板，复制修改话术到修订输入框，生成修订稿。
8. 确认文本后保存最终稿，再生成记忆入库。
9. 在“导出”页检查范围和格式后导出文稿。

写作页会保存每章阅读位置和未保存的本地临时稿；切换章节时会提示，避免误丢编辑内容。

## 环境与启动

### 环境要求

- Python 3.10 或更高版本
- Windows、macOS 或 Linux
- 可选：兼容 OpenAI 请求格式的模型服务

安装依赖：

```bash
python -m pip install -r requirements.txt
```

初始化数据库：

```bash
python main.py init-db
```

启动 Web 工作台：

```bash
python main_web.py
```

Windows 用户可以直接双击 `Hi Story.bat`。脚本会尝试关闭旧服务、启动新服务，并自动打开浏览器。

服务默认监听 `127.0.0.1`，优先使用 `8765` 端口；端口被占用时会选择后续可用端口。实际地址写入 `data/logs/server.url`。

## 模型配置

首次启动时，程序会在项目根目录创建 `config.json`。可以在 Web 的“设置”页填写，也可以使用命令行。

最小示例：

```json
{
  "model_provider": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "wire_api": "chat_completions",
  "api_key": "YOUR_API_KEY",
  "default_model": "gpt-4o-mini",
  "mock_mode": false
}
```

| 字段 | 说明 |
| --- | --- |
| `base_url` | 模型服务地址。 |
| `api_key` | 模型服务密钥。 |
| `wire_api` | 请求协议：`chat_completions` 或 `responses`。 |
| `default_model` | 默认模型。 |
| `agent_models` | 分别指定策划、写作、审稿、修订、记忆使用的模型。 |
| `review_model` | 审稿模型；为空时按默认模型或审稿智能体模型处理。 |
| `model_reasoning_effort` | 部分模型支持的推理强度。 |
| `timeout` | 单次请求超时时间，单位为秒。 |
| `max_retries` | 请求失败后的重试次数。 |
| `max_output_tokens` | 单次最大输出令牌数。 |
| `mock_mode` | 开启后不调用外部模型，用于检查流程和页面。 |

命令行示例：

```bash
python main.py set-config --base-url "https://api.openai.com/v1" --api-key "YOUR_API_KEY" --default-model "gpt-4o-mini" --mock-mode false
```

## 正文、质量检查与候选稿

正式生成的主要流程：

```text
细纲校验
→ 写作
→ 本地质量检查
→ 审稿
→ 自动修订
→ 风格回归检查
→ 最终稿或问题稿
```

质量检查会关注：

- 开头是否接住上一章的具体承接债。
- 正文是否像摘要、细纲或结构化协议。
- 近期章节是否重复相似的开头、结尾、标题或动作框架。
- “不是……而是……”等对照判断句、破折号和模板化表达是否过密。
- 章尾是否重复落在物件、文书或抽象感慨上。
- 篇幅、段落结构和移动端阅读风险。

质量检查用于发现风险，不替代作者判断。自动生成未通过时，正文会保存为“问题稿”，不会丢失；作者仍可直接保存为最终稿。手动保存仅会拒绝空正文、JSON、Markdown 代码块等明显不应作为小说正文的内容，其余问题以提醒形式保留。

修订稿如果引入更多模板句、破折号或其他风格退化，会被保存为候选稿，供你查看、载入或丢弃，不会自动覆盖当前最终稿。

## 自动换卷

生成细纲前，系统会汇总当前卷的章数、里程碑、退出条件、未回收伏笔和下一卷信息。模型给出换卷建议后，程序执行硬校验：

- 当前卷未达到 `min_chapters` 时，不允许提前切换。
- 达到 `hard_max_chapters` 时，系统会要求切入下一卷或收束当前卷。
- 不允许跳过中间卷。
- 下一卷不存在时，不会写入无效的分卷编号。

切换成功后，新细纲会归入下一卷，章节编号不会重置；运行记录会保留切换原因和需要带入下一卷的线索。

## 本地数据与安全

以下内容已被 `.gitignore` 忽略，不应上传到 GitHub：

- `config.json`、`.env`：可能包含 API Key。
- `data/`：作品数据库、正文、运行记录、导出文件和本地服务地址。
- `*.db`、`*.log`：数据库与日志文件。

本地 Web 服务每次启动都会生成随机令牌。除 `/api/health` 外，所有 API 请求必须携带 `X-HiStory-Token`；正常使用时令牌会自动注入页面，无需手工填写。

请注意：本地保存不等于不出网。关闭 `mock_mode` 后，章节上下文、待生成内容和修订指令会发送到你指定的模型服务。请自行确认服务商的数据政策，避免在作品资料中填写不应外发的敏感信息。

取消任务会停止本地后续流程并关闭当前客户端；已经送达模型服务的请求能否立刻终止，取决于服务商的接口能力。

## 开源许可

Hi Story 按 [MIT License](LICENSE) 开源。你可以自由使用、复制、修改、分发和商用本项目；分发源码或重要衍生部分时，需保留 `LICENSE` 中的版权声明与许可文本。

软件按“现状”提供，不附带任何明示或默示担保。小说内容、模型服务费用、第三方 API 合规性和导出文本的使用后果由使用者自行负责。

## 命令行

查看全部命令：

```bash
python main.py --help
```

常用命令：

```bash
# 创建作品并生成基础设定
python main.py create-work --title "示例小说" --idea "一句话创意" --genre "历史穿越" --platform "起点" --target-words 500000

# 查看作品与章节
python main.py list-works
python main.py show-work --work-id 1
python main.py list-chapters --work-id 1
python main.py show-chapter --work-id 1 --chapter 1

# 生成大纲、细纲和正文
python main.py generate-outline --work-id 1
python main.py generate-chapter-outlines --work-id 1 --start 1 --count 3
python main.py generate-chapter --work-id 1 --chapter 1

# 连续生成，并在每章完成后生成记忆
python main.py generate-chapters --work-id 1 --start 1 --count 3 --apply-memory

# 需要时跳过审稿或自动修订
python main.py generate-chapter --work-id 1 --chapter 1 --skip-review
python main.py generate-chapter --work-id 1 --chapter 1 --skip-revise

# 导出
python main.py export-txt --work-id 1
python main.py export-docx --work-id 1
python main.py export-chapter-txt --work-id 1 --chapter 1
python main.py export-chapter-docx --work-id 1 --chapter 1
```

CLI 导出适合脚本调用；Web 导出会额外校验整本或指定范围内是否存在缺章、空章和不可导出的正文。

## 目录结构

```text
Hi Story/
├── app/
│   ├── core/             # 数据契约与输出标准化
│   ├── database/         # SQLite、迁移和仓储层
│   ├── exporters/        # TXT / DOCX 导出
│   ├── prompts/          # 策划、写作、审稿、修订、记忆提示词
│   ├── services/         # 模型客户端和智能体
│   ├── utils/            # 上下文、格式化、质量检查和标题工具
│   └── web/              # 本地 Web API 与任务状态
├── web/                  # 页面、样式和浏览器交互
├── data/                 # 本地作品数据，默认不提交
├── main.py               # CLI 入口
├── main_web.py           # Web 服务入口
├── Hi Story.bat          # Windows 启动脚本
├── LICENSE               # MIT 开源许可证
└── requirements.txt
```

## 备份与发布前检查

重要作品位于 `data/works/<作品目录>/work.db`，导出文件位于对应作品的 `exports/` 目录。升级或清理项目之前，请先复制整个 `data/` 目录进行备份。

发布到 GitHub 前，建议执行：

```bash
git status
git check-ignore -v config.json data/index.db
python -B main.py --help
node --check web/app.js
```

确认 `config.json`、`.env`、`data/`、数据库和日志均未出现在待提交文件中，再提交源码与文档。

## 已知边界

- 质量检查只能降低明显的重复、承接和模板化风险，不能替代作者审稿。
- 模型输出质量依赖模型能力、题材资料、细纲质量和当前上下文；同一提示词在不同模型上的表现可能不同。
- 历史资料卡只提供约束与参考，正式历史考据仍应由作者核验来源。
