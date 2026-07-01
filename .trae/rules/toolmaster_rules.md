description: 本项目意图建立一个可以使用系统内各应用程序的工具，包括但不限于：
  - Word
  - Excel
  - Outlook
  - PowerPoint
  - Browser
  - Other Email
  - Other Application(IDE, Database, Server, etc.)
  - Video Player
  - Audio Player

  最高优先级规则（安全与合规）：
    - 所有操作必须在用户明确授权下执行，不得擅自操作系统应用
    - 不得读取、修改或传输用户的隐私数据和敏感文件
    - 执行模块在操作应用程序前须确认用户意图

  次高优先级规则（架构与可靠性）：
    - 所有模块之间的通信通过文件系统（txt/md/json）进行，保证状态可追溯
    - Agent思考结果必须落地为结构化文件，不得仅存在于内存
    - 执行模块必须将结果以文字或截图方式反馈给Agent

  普通优先级规则（交互与体验）：
    - CLI模块必须给用户清晰的指引信息和状态展示
    - 所有扫描、分析、执行的动作必须有可阅读的日志输出
    - 记忆模块在写入经验前必须去重，避免冗余记录
