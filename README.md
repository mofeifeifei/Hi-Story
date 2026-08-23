# Hi Story

<p align="center">
  <img src="Hi%20Story.png" alt="Hi Story" width="96">
</p>

<p align="center">
  <a href="https://github.com/mofeifeifei/Hi-Story"><img src="https://img.shields.io/badge/repository-GitHub-181717?style=flat-square&logo=github" alt="GitHub repository"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-f05a28?style=flat-square" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10 or newer">
</p>

Hi Story 是一个面向长篇小说创作的本地写作工作台。项目使用 Python 提供本地 Web 服务，使用 React 构建前端界面，使用 SQLite 保存作品数据。它用于组织作品设定、全书大纲、分卷规划、章节细纲、正文、修订记录和章节记忆，并通过用户配置的模型服务完成生成任务。

## 功能范围

- 管理作品基本信息、题材约束、人物、世界规则、伏笔和时间线。
- 生成和编辑全书大纲、分卷规划及章节细纲。
- 根据作品资料、前文上下文和当前细纲生成章节正文。
- 对正文进行上下文衔接、情节因果、人物一致性、重复表达等检查。
- 生成修订意见，保留候选版本，并支持继续编辑和保存。
- 从确认后的章节内容生成章节记忆，供后续章节使用。
- 保存草稿、最终稿、阅读位置、任务状态和模型调用记录。
- 导出整本作品、章节范围或单章的 TXT、DOCX 文件。
- 在设置页获取当前接口返回的模型列表，并从下拉框选择主模型或智能体模型。

项目不保证模型输出的文学质量、事实准确性或平台审核结果。发布前应由作者自行校对和审核。

## 环境要求

- Windows 10 或更高版本
- Python 3.10 或更高版本，并加入系统 PATH
- 使用真实模型服务时，需要可用的 API 地址、API 密钥和模型名称
- 首次安装依赖时需要网络连接

## 安装与启动

### 使用启动脚本

在项目根目录双击 `Hi Story.bat`。脚本会完成以下工作：

1. 检查 Python 版本。
2. 在项目目录创建 `.venv` 虚拟环境。
3. 安装 `requirements.txt` 中的依赖。
4. 启动本地 Web 服务并打开浏览器。

首次启动需要等待依赖安装。项目数据和运行日志会写入 `data/` 目录。

### 手动启动

在项目根目录打开 PowerShell，执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main_web.py
```

服务默认监听本机地址 `http://127.0.0.1:8765/`。如果默认端口被占用，程序会选择可用端口，并将实际地址写入 `data/logs/server.url`。

本地 API 使用启动时生成的令牌保护。正常使用时应通过启动脚本或 `server.url` 中的地址访问，不要将服务绑定到公网地址。

## 模型配置

启动 Web 工作台后，进入“设置”页面，创建或选择一个 AI 通道，填写：

- API 地址
- API 密钥
- 接口协议
- 默认模型

项目支持以下两种调用协议：

- OpenAI 兼容协议
- Anthropic Messages API

保存设置后可以测试连接。对于提供标准 `/models` 接口的 OpenAI 兼容服务，可以点击“获取列表”，随后直接从下拉框选择模型；未提供模型列表接口的服务需要手动填写模型名称。

高级设置可以让不同智能体使用当前通道内的不同模型，也可以让所有智能体跟随主模型。通道切换会同时切换该通道保存的 API 地址、密钥、协议和模型配置。

不使用真实模型服务时，可以在设置中启用模拟模式，用于检查页面和基本工作流程。模拟模式不用于生成正式小说内容。

## 使用流程

1. 新建作品，填写创意、题材、目标平台和写作要求。
2. 完善作品设定和题材约束。
3. 生成全书大纲和分卷规划，并按需修改。
4. 生成目标章节的细纲，确认章节目标、场景、人物行动和承接关系。
5. 在正文页面生成或编辑正文。
6. 查看检查结果和修订意见，必要时生成修订版本。
7. 确认当前版本后保存为最终稿。
8. 根据最终稿生成章节记忆。
9. 在导出页面生成 TXT 或 DOCX 文件。

检查未通过的内容不会因此丢失，仍可作为草稿或候选版本继续编辑。作者应根据实际内容决定是否保存为最终稿及是否写入记忆。

## 数据、配置与安全

作品数据默认保存在以下目录：

```text
data/works/<作品目录>/work.db
```

本地配置文件为项目根目录下的 `config.json`。其中可能包含 API 密钥，不应提交到 GitHub。`.gitignore` 已排除以下本地文件和目录：

- `config.json`、环境变量文件
- `.venv/` 和前端依赖目录
- `data/`、数据库、日志和导出文件
- 测试报告、缓存和临时截图

API 密钥仅保存在本机配置中。设置页面默认显示掩码，只有点击查看操作时才请求显示已保存密钥。

关闭模拟模式后，作品设定、章节上下文、正文和修订要求会发送到所配置的模型服务。使用前请阅读相应服务商的数据处理政策。建议在升级项目或迁移设备前备份整个 `data/` 目录。

## 命令行

命令行入口为 `main.py`。查看完整命令：

```powershell
python main.py --help
```

常用命令如下：

```powershell
# 初始化 SQLite 数据库
python main.py init-db
# 列出已有作品
python main.py list-works
# 查看指定作品的完整资料
python main.py show-work --work-id 1
# 列出指定作品的章节
python main.py list-chapters --work-id 1
# 查看指定作品的某一章
python main.py show-chapter --work-id 1 --chapter 1
# 生成全书大纲和分卷规划
python main.py generate-outline --work-id 1
# 生成指定范围内的章节细纲
python main.py generate-chapter-outlines --work-id 1 --start 1 --count 3
# 生成指定章节的正文
python main.py generate-chapter --work-id 1 --chapter 1
# 连续生成指定范围内的多章正文
python main.py generate-chapters --work-id 1 --start 1 --count 3
# 导出整本作品为 TXT
python main.py export-txt --work-id 1
# 导出整本作品为 DOCX
python main.py export-docx --work-id 1
```

生成正文时可以使用 `--skip-review`、`--skip-revise` 和 `--skip-memory` 跳过相应步骤；是否自动写入记忆由 `--apply-memory` 控制。正式使用前应先通过 Web 工作台确认作品和模型配置。

## 开发构建

普通使用不需要重新构建前端，仓库中的 `web/` 目录已经包含可运行的构建结果。

修改前端源码时，在 `frontend/` 目录执行：

```powershell
npm install
npm run typecheck
npm run build
```

构建结果会写入上级目录的 `web/`。Python 后端源码、提示词、数据库代码和前端源码分别位于以下目录：

```text
Hi Story/
├── app/             Python 后端、数据库、服务和提示词
├── frontend/        React 前端源码
├── web/             前端构建结果
├── main.py          命令行入口
├── main_web.py      Web 服务入口
├── Hi Story.bat     Windows 启动脚本
├── requirements.txt Python 依赖
├── LICENSE
└── README.md
```

## 问题反馈

请通过 GitHub Issues 提交问题，并尽量提供：

- Windows 版本和 Python 版本
- 复现步骤
- 错误信息或相关日志片段
- 使用的接口协议和模型名称

请勿提交 API 密钥、完整配置文件、私人作品数据库或未脱敏的正文内容。

## 许可证

本项目采用 [MIT License](LICENSE)。许可证正文同时提供英文条款和中文译文；使用、修改和分发本项目时，请以许可证文件为准。
