# ToolMaster

系统应用程序智能操作工具——通过AI Agent理解用户意图，自动扫描、分析、操作Windows系统中的各类应用程序。

## 功能概述

ToolMaster 通过5个核心模块协作，实现对系统内应用程序（Word、Excel、Outlook、PowerPoint、Browser、IDE等）的智能化操作：

| 模块 | 功能 |
|------|------|
| **窗口扫描模块** | 扫描指定窗口的UI元素树，递归遍历子组件，生成结构化的扫描文件 |
| **应用管理模块** | 维护已扫描应用目录，追踪当前任务状态 |
| **Agent模块** | 连接云端/本地大模型API，进行思考、分析、规划和决策 |
| **执行模块** | 执行Agent下发的操作任务，支持截图反馈和重试机制 |
| **CLI模块** | 命令行交互界面，支持所有操作的指令入口 |

## 项目结构

```
ToolMaster/
├── main.py                     # 入口脚本
├── requirements.txt            # 依赖包列表
├── README.md                   # 项目说明
├── config/
│   └── config.json             # 全局配置文件
├── data/                       # 运行时数据目录（自动创建）
│   ├── application_directory.txt   # 应用目录
│   ├── current_working.txt         # 当前工作状态
│   ├── parallel_working.txt        # 并行执行规划
│   ├── voice_input.txt             # 语音输入规划
│   ├── scans/                      # 扫描结果
│   │   ├── xxx_scan_element.txt
│   │   └── xxx_scan_element_detail.txt
│   ├── experience/                 # 经验记录
│   │   └── xxx_experience.txt
│   ├── executions/                 # 执行日志
│   ├── screenshots/                # 截图
│   └── logs/                       # 运行日志
├── toolmaster/
│   ├── __init__.py             # 包入口
│   ├── cli.py                  # CLI模块
│   ├── scanner.py              # 窗口扫描模块
│   ├── manager.py              # 应用管理模块
│   ├── agent.py                # Agent模块
│   ├── executor.py             # 执行模块
│   ├── config.py               # 配置管理
│   └── utils.py                # 工具函数
└── .trae/
    └── rules/
        ├── architecture.txt    # 架构设计文档
        └── toolmaster_rules.md # 项目规则
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

核心依赖：
- `pywin32` - Windows API 访问
- `uiautomation` - Windows UI Automation 深度扫描
- `requests` - Agent API 调用
- `Pillow` - 截图功能（可选）

### 2. 配置API密钥

编辑 `config/config.json`，填入大模型API密钥：

```json
{
    "agent": {
        "api_type": "cloud",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_key": "your-api-key-here",
        "model": "gpt-4"
    }
}
```

支持任何兼容 OpenAI API 格式的服务（包括本地部署的 LLM）。

### 3. 启动

```bash
python main.py
```

### 4. 使用命令

进入 CLI 后，输入 `help` 查看所有可用命令。

## 命令说明

### 窗口扫描

```bash
scan Notepad          # 扫描Notepad窗口的UI元素并AI分析
windows               # 列出所有可见窗口
windows chrome        # 过滤含"chrome"的窗口
```

### 应用管理

```bash
dir                   # 显示应用目录
dir Notepad           # 查看Notepad详情
status                # 显示系统状态
register Notepad scan.txt detail.txt  # 手动注册应用
set_task Word 撰写报告     # 设置当前任务
clear_task                # 清除当前任务
```

### Agent智能

```bash
think 如何用Excel创建数据透视表   # Agent思考问题
plan 打开浏览器搜索天气预报       # Agent生成执行计划
```

### 经验记忆

```bash
record Notepad "创建文本" "成功" "需先定位编辑区域"   # 记录经验
experience                       # 列出所有经验
experience Notepad               # 查询Notepad的经验
experience Notepad "创建"        # 按关键词搜索经验
```

### 任务执行

```bash
execute 打开Word创建一份会议纪要     # 执行完整任务
parallel 任务A | 任务B | 任务C       # 规划并行执行
```

### 其他

```bash
config                 # 查看配置
config set agent.model gpt-3.5-turbo   # 修改配置
voice                  # 查看语音输入规划
quit                   # 退出
```

## 数据流

```
用户输入 (CLI)
    │
    ▼
Agent模块 ──think()──▶ 理解意图、分析元素
    │
    ├──▶ 窗口扫描模块 ──scan()──▶ xxx_scan_element.txt
    │                                      │
    │                              analyze() (Agent)
    │                                      ▼
    │                            xxx_scan_element_detail.txt
    │
    ├──▶ Agent.act() ──▶ 生成执行计划 (steps)
    │
    ▼
执行模块 ──execute_task()──▶ 按步骤操作应用
    │                              │
    │                      截图/文字反馈
    │                              │
    ▼                              ▼
经验记录 ◀────────── 结果分析 ──── 执行日志
```

## 安全规则

1. 所有操作须经用户明确授权
2. 不得读取/修改/传输用户隐私数据
3. 模块间通过文件系统通信，状态可追溯
4. Agent思考结果必须落地为文件

## 许可证

本项目仅供个人学习和研究使用。
