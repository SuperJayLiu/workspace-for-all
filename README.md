# 学术工作台 · Scholar Workspace

[English](README.en.md) · [安装与使用](docs/安装与使用.md) · [参与贡献](CONTRIBUTING.md)

[![Tests](https://github.com/SuperJayLiu/scholar-workspace/actions/workflows/tests.yml/badge.svg)](https://github.com/SuperJayLiu/scholar-workspace/actions/workflows/tests.yml)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个本地优先、零依赖的个人学术工作台：用浏览器管理稿件、期刊、会议、文献、想法和日程，数据始终是你磁盘上可直接阅读的 Markdown 文件。

- 无云端账号、无订阅、无数据库
- Python 标准库后端 + 原生 JavaScript 前端
- 支持 Zotero / EndNote / Mendeley 导出文件的文献索引
- 稿件、想法、文献、会议和日程可双向关联
- 可选的 AI 自动任务、学术雷达和多设备 Git 同步

> 界面目前为简体中文。源码仓库只包含通用示例数据，不包含作者的个人记录、账号、路径、密钥或使用历史。

## 一分钟启动

需要 **Python 3.9+**，无需 `pip install`。

```bash
git clone https://github.com/SuperJayLiu/scholar-workspace.git
cd scholar-workspace
python3 server.py
```

浏览器会自动打开 <http://127.0.0.1:8765/>。首次进入时，设置向导会带你完成可选配置。

也可以直接双击：

- macOS：`安装-Mac.command`（安装并设为开机启动）或 `启动.command`（只运行一次）
- Windows：`安装-Windows.bat` 或 `启动.bat`

## 你能用它做什么

| 模块 | 用途 |
|---|---|
| 稿件流程 | 记录 started → submitted → R&R → accepted，统计真实审稿周期 |
| 文献库 | 索引 `.bib`、`.ris`、CSL-JSON、`.nbib`，链接 DOI、PDF 与文献管理器 |
| 研究网络 | 双向关联想法、稿件、论文、会议和日程 |
| 阅读复习 | 结构化笔记与 1 / 7 / 30 / 90 天复习队列 |
| 自动任务 | 可选的研究体检、周报、方法扫描和文献雷达 |
| 多设备 | 用你自己的私有 Git 仓库同步学术数据；本地私密数据不参与同步 |

## 数据与隐私

| 路径 | 内容 | 默认进入 Git？ |
|---|---|---|
| `data/` | 学术记录、配置及通用示例 | 是 |
| `local/` | 密钥、个人生活数据、备份、本机路径、日志 | **否** |
| `attachments/` | 大附件 | **否** |
| `app/` | 无构建步骤的前端 | 是 |

`local/` 和 `attachments/` 已写入 `.gitignore`。诊断包也只包含版本、平台、记录数量和脱敏后的状态，不包含记录正文。

如果要在多台设备同步自己的记录，请新建一个**私有仓库**作为个人数据仓库；不要把个人数据推回本公共源码仓库。

## 检查与开发

运行全部核心检查：

```bash
bash tests/跑全部.sh
```

13 个 Python 测试套件零依赖。5 个浏览器测试需要 Playwright；未安装时会自动跳过：

```bash
npm i -D playwright
npx playwright install chromium
bash tests/跑全部.sh
```

测试会在临时副本上运行，不会修改你的真实数据。GitHub Actions 会在每次 push 和 pull request 时运行核心测试。

## 文档

- [完整安装与使用说明](docs/安装与使用.md)
- [详细使用教程](使用教程.md)
- [参与贡献](CONTRIBUTING.md)
- [安全说明](SECURITY.md)
- [测试说明](tests/README.md)

## 已知限制

- 界面目前仅提供简体中文。
- Chromium 与 macOS/Linux 覆盖最完整；Windows 和 Safari 仍需要更多真实环境验证。
- 局域网访问必须设置访问码，且默认只读。不要把本地服务直接暴露到公网。

## 许可证

[MIT](LICENSE) © 2026 Scholar Workspace contributors
