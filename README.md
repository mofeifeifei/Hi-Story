# Hi Story

<p align="center">
  <img src="Hi%20Story.png" alt="Hi Story" width="96">
</p>

<p align="center">
  <a href="https://github.com/mofeifeifei/Hi-Story/stargazers"><img src="https://img.shields.io/github/stars/mofeifeifei/Hi-Story?style=flat-square" alt="GitHub Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-f05a28?style=flat-square" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/React-19-149ECA?style=flat-square&logo=react&logoColor=white" alt="React 19">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-1877C9?style=flat-square" alt="Windows, macOS and Linux">
</p>

Hi Story 是一个本地运行的长篇小说写作工具，用于管理作品设定、分卷大纲、章节细纲、正文、修订意见和长期记忆。项目提供 Web 工作台和命令行工具，作品数据默认保存在本机 SQLite 数据库中。

## 主要功能

- 管理作品设定、题材契约、人物、世界规则、伏笔和时间线。
- 生成并编辑全书大纲、分卷规划和章节细纲。
- 生成细纲时判断当前卷是否完成，并在满足条件后自动切换到下一卷。
- 根据上一章结尾、章节交接信息和当前细纲生成正文。
- 检查上下文承接、情节因果、篇幅、重复表达和常见机器化句式。
- 提供审稿建议、定向修订和候选稿管理，不用问题稿直接覆盖最终稿。
- 从最终稿提取章节记忆，供后续章节继续使用。
- 保存本地草稿、章节阅读位置、任务状态和模型调用记录。
- 支持整本、章节范围和单章的 TXT、DOCX 导出。
- 支持获取兼容服务商提供的模型列表，并分别设置各智能体使用的模型。

## 环境要求

- Python 3.10 或更高版本
- Windows、macOS 或 Linux
- 首次安装依赖时需要网络连接
- 使用真实模型时，需要兼容 OpenAI 请求格式的 API 地址、密钥和模型名称

## 快速开始

### Windows

下载并解压项目后，双击：

```text
Hi Story.bat
```

启动脚本会自动创建 `.venv`、安装依赖、启动本地服务并打开浏览器。首次启动需要等待依赖安装，以后会直接使用现有环境。

### macOS 和 Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main_web.py
```

### Windows 手动启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main_web.py
```

服务默认使用 `http://127.0.0.1:8765/`。如果端口已被占用，程序会选择后续可用端口，并将实际地址写入 `data/logs/server.url`。

## 模型配置

启动工作台后，打开左侧的“设置”页面，填写服务商、API 地址、API 密钥、接口协议和主模型。保存后可以测试连接或获取当前密钥可用的模型列表。部分服务商不提供模型列表接口，此时可以手动填写模型名称。

开启“所有智能体跟随主模型”后，策划、写作、审稿、修订和记忆使用同一个模型；关闭后可以分别指定模型。

生成参数包含两个输出上限：

- **普通任务输出上限**：用于大纲、审稿等结构化任务。
- **正文与修订输出上限**：用于正文、修订和记忆等长文本任务，默认值为 `24000`。

不配置真实 API 时，可以开启本地模拟模式检查页面和工作流程。模拟模式不会生成可用于正式创作的小说内容。

## 基本流程

1. 新建作品并填写书名、题材、创意、目标平台和写作方向。
2. 生成或手动填写作品设定与题材契约。
3. 生成全书大纲和分卷规划。
4. 生成章节细纲，确认章节目标、场景和承接关系。
5. 在“正文写作”页面生成或编辑正文。
6. 查看修订建议，按需要生成修订稿。
7. 确认内容后保存为最终稿。
8. 根据最终稿生成章节记忆。
9. 在“导出”页面导出 TXT 或 DOCX 文稿。

自动检查未通过的正文仍会保留为问题稿或候选稿。作者可以继续编辑，也可以自行确认并保存为最终稿。

## 数据与安全

作品数据默认保存在：

```text
data/works/<作品目录>/work.db
```

以下内容已通过 `.gitignore` 排除，不会随正常 Git 提交上传：

- `config.json`
- `.venv/`
- `data/`
- 数据库、日志和本地导出文件

API 密钥保存在本机 `config.json` 中。设置页面不会把已经保存的完整密钥重新返回给浏览器。

关闭模拟模式后，完成任务所需的作品设定、章节上下文、正文和修改要求会发送给所配置的模型服务。使用前请确认服务商的数据处理政策。

建议定期备份整个 `data/` 目录。升级项目、清理文件或更换电脑前，应先确认备份可以正常读取。

## 命令行

查看可用命令：

```bash
python main.py --help
```

常用示例：

```bash
python main.py list-works
python main.py list-chapters --work-id 1
python main.py generate-outline --work-id 1
python main.py generate-chapter-outlines --work-id 1 --start 1 --count 3
python main.py generate-chapter --work-id 1 --chapter 1
python main.py export-txt --work-id 1
python main.py export-docx --work-id 1
```

## 项目结构

```text
Hi Story/
├── app/             Python 后端、数据库、智能体和提示词
├── frontend/        React 前端源码
├── web/             已构建的 Web 页面
├── main.py          命令行入口
├── main_web.py      Web 服务入口
├── Hi Story.bat     Windows 启动脚本
├── requirements.txt
└── LICENSE
```

## 参与项目

发现问题或有功能建议，可以在 GitHub Issues 中提交。请说明操作步骤、错误信息和使用的系统版本，不要附带 API 密钥或包含私人作品内容的数据库。

## 许可证

本项目采用 [MIT License](LICENSE)。具体授权条款和自愿捐赠倡议以 `LICENSE` 文件为准。

模型生成内容的质量、事实准确性和平台合规性需要由使用者自行审核。
