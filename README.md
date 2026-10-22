# 刷单词助手 · BrushEnglish

一个 Windows 桌面端的背单词自动化助手。它把「学习单词 → 测试 → 成绩统计」这一套流程做成图形界面，支持本地 OCR 认字、语音识别拼写、选择题自动匹配和进度恢复。

> 本项目仅供个人学习与自动化研究使用。使用前请确认你使用的目标应用允许自动化操作。

## 功能

- 图形界面：PySide6 + QML，浅色主题，可缩放窗口
- 学习阶段：自动翻词、点击释义、标记“太简单”、每 7 个词继续下一批
- 测试阶段：自动识别题号、题型、选项和拼写题
- 认字引擎：内置 RapidOCR / PaddleOCR，也可连接外部 Umi-OCR
- 拼写题：支持本地 Whisper 语音识别，失败时退回词表顺序
- 选择题匹配：词性 + 中文关键词 + 整句相似度打分，低置信度时不乱选
- 进度恢复：按 App 显示进度校准，支持断电/重启后续跑
- 自动恢复：页面跑偏、OCR 失败时自动重试导航，多次失败后停止并提示
- 词典工具：支持导出词表、补全缺失释义

## 目录结构

```
完整脚本_学习测试循环.py   核心自动化引擎
刷单词助手新版.py          图形界面启动入口
appcore/                   控制层（状态机、配置、日志、OCR 引擎管理）
qml/                       界面（主窗口、组件、页面）
coordinate_profiles.py     坐标方案管理
auto_updater.py            版本检查（示例地址，需自行修改）
题库/                      通用考试词典（ECDICT 派生）
config.example.json        示例配置
```

## 环境要求

- Windows 10 / 11
- Python 3.13
- PySide6 6.8.x
- 一个可用的 OCR 引擎（三选一）：
  - 内置 RapidOCR（推荐，启动快）
  - 内置 PaddleOCR（中文识别更稳，启动慢）
  - 外部 Umi-OCR（HTTP 服务，默认端口 1224）

安装依赖：

```bash
pip install -r requirements.txt
```

## 运行

1. 把 `config.example.json` 复制为 `config.json`
2. 准备 OCR 引擎：
   - 内置引擎：把 `PaddleOCR-json.exe` / `RapidOCR-json.exe` 及其模型放到 `内置OCR/` 下（仓库不包含这些二进制文件）
   - 或启动 Umi-OCR 并开启 HTTP 服务（默认 `http://127.0.0.1:1224/api/ocr`）
3. 启动：

```bash
python 刷单词助手新版.py
```

## 配置说明

- `config.json`：坐标、OCR 地址、匹配阈值、反检测参数等
- `ui_settings.json`：窗口位置、主题、引擎选择
- `logs/`：运行日志
- `stats.json`：学习统计

这些运行数据默认已被 `.gitignore` 排除，不会上传。

## 词典来源

`题库/题库_通用考试词典.json` 由开源项目 **ECDICT** 整理而来：

- 项目地址：https://github.com/skywind3000/ECDICT
- 许可证：MIT

感谢 ECDICT 作者的工作。

## 许可证

本项目使用 **GPL-3.0** 许可证，详见 `LICENSE`。

## 说明

- 仓库只包含源码和示例配置，不包含打包后的 exe、OCR 引擎二进制、运行日志和截图。
- 自动化脚本涉及屏幕截图、鼠标键盘模拟和 OCR，请在了解风险的前提下使用。
