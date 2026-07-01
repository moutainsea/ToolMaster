"""
CLI模块 (Command Line Interface Module)

功能：
  - 给用户提供对话界面，有指引信息
  - 可输入命令控制各模块
  - 呈现正在执行的任务信息、已有应用目录信息
  - 语音输入思考文档（voice_input.txt，暂不实现功能）
"""
import os
import sys
import cmd
from datetime import datetime
from toolmaster.utils import (
    logger, write_text_file, read_text_file
)
from toolmaster.config import DATA_DIR, load_config
from toolmaster.scanner import WindowScanner, scan_window, list_available_windows
from toolmaster.manager import ApplicationManager, get_manager
from toolmaster.agent import Agent
from toolmaster.executor import TaskExecutor


class ToolMasterCLI(cmd.Cmd):
    """ToolMaster 命令行交互界面"""

    intro = r"""
╔══════════════════════════════════════════════════════╗
║          Welcome to ToolMaster                       ║
║     系统应用程序智能操作工具                          ║
║                                                     ║
║  输入 help 查看可用命令                              ║
║  输入 quit 退出                                      ║
╚══════════════════════════════════════════════════════╝
"""

    def __init__(self):
        super().__init__()
        config = load_config()
        self.prompt = config["cli"]["prompt_prefix"]
        self.max_history = config["cli"]["max_history"]

        # 初始化各模块
        self.scanner = WindowScanner()
        self.manager = get_manager()
        self.agent = Agent()
        self.executor = TaskExecutor()

        logger.info("ToolMaster CLI 已启动")

    # ========== 扫描相关命令 ==========

    def do_scan(self, arg):
        """扫描指定窗口的UI元素
用法: scan <窗口名称关键字>
示例: scan Notepad"""
        if not arg.strip():
            print("错误: 请指定窗口名称\n用法: scan <窗口名称关键字>")
            return

        window_title = arg.strip()
        print(f"\n正在扫描窗口: '{window_title}' ...\n")

        result = scan_window(
            window_title, agent=self.agent, use_uia=True
        )

        if not result["elements"]:
            print(f"未找到窗口 '{window_title}' 或其UI元素")
            # 列出可用窗口供参考
            print("\n当前可用的窗口:")
            for win in self.scanner.list_windows()[:10]:
                print(f"  - {win['title']}")
            return

        print(f"扫描完成！发现 {len(result['elements'])} 个元素")
        print(f"扫描结果: {result['scan_file']}")

        if result["detail_file"]:
            print(f"分析结果: {result['detail_file']}")

        # 注册到应用管理模块
        self.manager.register_application(
            window_title,
            result["scan_file"],
            result.get("detail_file"),
        )

    def do_windows(self, arg):
        """列出当前所有可见窗口
用法: windows [过滤关键字]"""
        keyword = arg.strip().lower()
        windows = self.scanner.list_windows()
        if keyword:
            windows = [w for w in windows if keyword in w["title"].lower()]

        if not windows:
            print("未找到窗口")
            return

        print(f"\n当前可见窗口 ({len(windows)} 个):")
        print("-" * 60)
        for win in windows:
            print(f"  [{win['class_name']}] {win['title']}")


    def do_start_multi_scan(self, arg):
        """开始多页面扫描模式
用法: start-multi-scan <应用名称>
示例: start-multi-scan PowerPoint

说明：
  1. 输入此命令开始多页面扫描
  2. 手动切换到想扫描的页面
  3. 输入 'scan-next' 扫描当前页面
  4. 重复步骤2-3直到所有页面扫描完成
  5. 输入 'scan-done' 结束扫描
  6. 重合度超过95%的页面会被认为是同一页面"""
        if not arg.strip():
            print("错误: 请指定应用名称\n用法: start-multi-scan <应用名称>")
            return

        app_name = arg.strip()
        result = self.scanner.start_multi_page_scan(app_name)
        
        print(f"\n{'=' * 60}")
        print(f"多页面扫描模式已启动")
        print(f"应用名称: {result['app_name']}")
        print(f"重合度阈值: {result['instructions'][-1]}")
        print(f"\n操作步骤:")
        for i, instruction in enumerate(result['instructions'][:-1], 1):
            print(f"  {instruction}")
        print(f"{'=' * 60}\n")

    def do_scan_next(self, arg):
        """扫描下一个页面（多页面扫描模式）
用法: scan-next <窗口名称关键字>

说明：在 start-multi-scan 后使用，先手动切换到要扫描的页面，再执行此命令"""
        status = self.scanner.get_multi_page_status()
        if status["mode"] != "multi_page":
            print("错误: 未启用多页面扫描模式")
            print("请先执行: start-multi-scan <应用名称>")
            return

        window_title = arg.strip() or status["app_name"]
        print(f"\n正在扫描页面... (第 {status['scan_count'] + 1} 次)\n")

        result = self.scanner.scan_next_page(window_title)

        if not result["success"]:
            print(f"扫描失败: {result.get('error', '未知错误')}")
            return

        print(f"{'=' * 60}")
        print(f"扫描结果:")
        print(f"  扫描序号: {result['page_index']}")
        print(f"  元素数量: {result['elements_count']}")
        print(f"  唯一指纹: {result['fingerprint_count']}")
        print(f"  重合度: {result['overlap_ratio']:.1%}")
        print(f"  详情: {result['details']}")
        print(f"  判定: {'✓ 新页面' if result['is_new_page'] else '✗ 已有页面，跳过保存'}")
        
        if result.get("page_file"):
            print(f"  保存位置: {result['page_file']}")
        
        print(f"{'=' * 60}\n")

    def do_scan_done(self, arg):
        """结束多页面扫描模式
用法: scan-done"""
        status = self.scanner.get_multi_page_status()
        if status["mode"] != "multi_page":
            print("错误: 未启用多页面扫描模式")
            return

        print("\n正在结束多页面扫描...\n")
        summary = self.scanner.finish_multi_page_scan()

        print(f"{'=' * 60}")
        print(f"多页面扫描完成!")
        print(f"  应用名称: {summary['app_name']}")
        print(f"  总扫描次数: {summary['total_scans']}")
        print(f"  识别页面数: {summary['new_pages_saved']}")
        print(f"  汇总文件: {summary.get('summary_file', 'N/A')}")
        print(f"\n页面列表:")
        for page in summary.get("pages", []):
            print(f"  Page {page['page_index']}: {page['fingerprint_count']} 个唯一元素")
        print(f"{'=' * 60}\n")

    def do_scan_status(self, arg):
        """查看多页面扫描状态
用法: scan-status"""
        status = self.scanner.get_multi_page_status()
        
        if status["mode"] != "multi_page":
            print("\n多页面扫描模式: 未启用")
        else:
            print(f"\n{'=' * 60}")
            print(f"多页面扫描状态:")
            print(f"  应用名称: {status['app_name']}")
            print(f"  已扫描次数: {status['scan_count']}")
            print(f"  已保存页面: {status['saved_pages']}")
            print(f"{'=' * 60}\n")

    def do_pages(self, arg):
        """查看已扫描的页面文件
用法: pages [应用名称]"""
        from toolmaster.scanner import PAGE_DIR
        import glob
        
        app_name = arg.strip()
        if app_name:
            pattern = f"{app_name}_Page_*.txt"
        else:
            pattern = "*_Page_*.txt"
        
        files = glob.glob(os.path.join(PAGE_DIR, pattern))
        files.extend(glob.glob(os.path.join(PAGE_DIR, f"*_pages_summary.txt")))
        
        if not files:
            print("未找到页面扫描文件")
            print(f"页面目录: {PAGE_DIR}")
            return
        
        print(f"\n页面扫描文件 ({len(files)} 个):")
        print("-" * 60)
        for f in sorted(files):
            size = os.path.getsize(f)
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
            print(f"  {os.path.basename(f)} ({size} bytes, {mtime})")
        print(f"\n目录: {PAGE_DIR}")
        print(f"{'=' * 60}\n")

    # ========== 应用管理相关命令 ==========

    def do_dir(self, arg):
        """显示应用目录
用法: dir [应用名称]  - 无参数显示全部，指定名称显示详情"""
        arg = arg.strip()
        if arg:
            info = self.manager.get_app_info(arg)
            if info:
                print(f"\n应用详情: {arg}")
                for k, v in info.items():
                    print(f"  {k}: {v}")
            else:
                print(f"未找到应用: '{arg}'")
        else:
            print(f"\n{self.manager.get_directory()}")

    def do_status(self, arg):
        """显示当前系统状态
用法: status"""
        print(f"\n{self.manager.show_status()}")

    def do_register(self, arg):
        """手动注册应用到目录
用法: register <窗口名称> <扫描文件名> [分析文件名]"""
        parts = arg.strip().split(maxsplit=2)
        if len(parts) < 2:
            print("用法: register <窗口名称> <扫描文件名> [分析文件名]")
            return

        window_name = parts[0]
        scan_file = parts[1]
        detail_file = parts[2] if len(parts) > 2 else None
        self.manager.register_application(window_name, scan_file, detail_file)
        print(f"已注册应用: {window_name}")

    def do_set_task(self, arg):
        """设置当前正在执行的任务
用法: set_task <应用名称> <任务描述>"""
        if not arg.strip():
            print("用法: set_task <应用名称> <任务描述>")
            return

        parts = arg.split(maxsplit=1)
        app_name = parts[0]
        task = parts[1] if len(parts) > 1 else ""
        self.manager.set_current_working(app_name, task)
        print(f"当前任务已设置: [{app_name}] {task}")

    def do_clear_task(self, arg):
        """清除当前任务状态
用法: clear_task"""
        self.manager.clear_current_working()
        print("当前任务已清除")

    # ========== Agent相关命令 ==========

    def do_think(self, arg):
        """让Agent思考一个问题
用法: think <问题描述>"""
        if not arg.strip():
            print("用法: think <问题描述>")
            return

        print("\nAgent 思考中...\n")
        result = self.agent.think(arg.strip())
        print(result)

    def do_plan(self, arg):
        """让Agent为一个任务生成执行计划
用法: plan <任务描述>"""
        if not arg.strip():
            print("用法: plan <任务描述>")
            return

        print("\n正在生成执行计划...\n")
        plan = self.agent.act(arg.strip())
        print("执行计划:")
        for step in plan.get("steps", []):
            print(f"  {step['index']}. {step.get('action', '?')} -> {step.get('target', '?')}")
            print(f"     {step.get('description', '')}")

    # ========== 经验相关命令 ==========

    def do_record(self, arg):
        """记录应用操作经验
用法: record <应用名称> <任务> <结果> <经验总结>"""
        parts = arg.strip().split(maxsplit=3)
        if len(parts) < 4:
            print("用法: record <应用名称> <任务> <结果> <经验总结>")
            return

        app_name, task, result, lesson = parts
        self.agent.record_experience(app_name, task, result, lesson)
        print(f"经验已记录: {app_name}")

    def do_experience(self, arg):
        """查询应用操作经验
用法: experience <应用名称> [查询关键词]"""
        parts = arg.strip().split(maxsplit=1)
        if not parts[0]:
            # 列出所有经验
            exps = self.agent.get_all_experiences()
            if exps:
                print(f"\n已记录经验的应用 ({len(exps)} 个):")
                for exp in exps:
                    size_kb = exp["size"] / 1024
                    print(f"  - {exp['app_name']} ({size_kb:.1f} KB)")
            else:
                print("暂无经验记录")
            return

        app_name = parts[0]
        hint = parts[1] if len(parts) > 1 else None
        result = self.agent.query_experience(app_name, hint)
        if result:
            print(result)
        else:
            print(f"应用 '{app_name}' 暂无经验记录")

    # ========== Skill 相关命令 ==========

    def do_skills(self, arg):
        """列出所有已注册的 Skill
用法: skills [应用名称]"""
        try:
            from toolmaster.skills import skill_registry
        except Exception as e:
            print(f"Skill 系统未加载: {e}")
            return

        app_name = arg.strip() or None
        vocab = skill_registry.get_skill_vocabulary(app_name=app_name)
        print(f"\n{vocab}")
        print(f"\n总计: {skill_registry.get_count()} 个 Skill")

    def do_skill_run(self, arg):
        """手动执行一个 Skill
用法: skill-run <Skill名称> [参数JSON]
示例: skill-run PowerPoint_Launch"""
        parts = arg.strip().split(maxsplit=1)
        if not parts[0]:
            print("用法: skill-run <Skill名称> [参数JSON]")
            return

        skill_name = parts[0]
        params = {}
        if len(parts) > 1 and parts[1].strip():
            try:
                import json
                params = json.loads(parts[1])
            except json.JSONDecodeError:
                print(f"参数JSON解析失败: {parts[1]}")
                return

        try:
            from toolmaster.skills import skill_registry
        except Exception as e:
            print(f"Skill 系统未加载: {e}")
            return

        skill = skill_registry.get(skill_name)
        if not skill:
            print(f"Skill 未找到: {skill_name}")
            print("使用 'skills' 命令查看所有可用 Skill")
            return

        print(f"\n执行 Skill: {skill_name}")
        print(f"描述: {skill.description}")
        print(f"参数: {params}\n")

        # 确保 executor 已注入
        if not skill.executor:
            skill.executor = self.executor

        result = skill.run(**params)
        print(f"\n结果: {result}")
        if result.data:
            print(f"数据: {result.data}")

    def do_skill_info(self, arg):
        """查看 Skill 详细信息
用法: skill-info <Skill名称>"""
        skill_name = arg.strip()
        if not skill_name:
            print("用法: skill-info <Skill名称>")
            return

        try:
            from toolmaster.skills import skill_registry
        except Exception as e:
            print(f"Skill 系统未加载: {e}")
            return

        skill = skill_registry.get(skill_name)
        if not skill:
            print(f"Skill 未找到: {skill_name}")
            return

        print(f"\n{'=' * 60}")
        print(f"Skill 名称: {skill.name}")
        print(f"所属应用: {skill.app_name}")
        print(f"分类:     {skill.category}")
        print(f"超时:     {skill.timeout}s")
        print(f"重试次数: {skill.retry_count}")
        print(f"描述:     {skill.description}")
        
        alts = skill.get_alternatives()
        if alts:
            print(f"\n备选方案:")
            for i, (desc, _) in enumerate(alts, 1):
                print(f"  {i}. {desc}")
        print(f"{'=' * 60}\n")

    # ========== 执行相关命令 ==========

    def do_execute(self, arg):
        """执行Agent规划的任务
用法: execute <任务描述>
示例: execute 使用PowerPoint生成股票市场分析PPT"""
        if not arg.strip():
            print("用法: execute <任务描述>")
            return

        task = arg.strip()
        print(f"\n执行任务: {task}\n")

        # 自动提取应用名称（从任务描述中检测）
        app_names = ["PowerPoint", "Word", "Excel", "Outlook", "Notepad", "Chrome", "Edge", "Firefox"]
        detected_app = None
        for app in app_names:
            if app.lower() in task.lower():
                detected_app = app
                break

        # 第一步：生成执行计划（传入应用名称以加载扫描结果作为上下文）
        print("[1/3] 生成执行计划...")
        if detected_app:
            print(f"  检测到目标应用: {detected_app}")
            plan = self.agent.act(task, app_name=detected_app)
        else:
            plan = self.agent.act(task)
        print(f"  共 {len(plan.get('steps', []))} 个步骤")

        # 第二步：执行
        print("[2/3] 执行中...")
        result = self.executor.execute_task(task, plan)
        print(f"  执行完成，状态: {result['status']}")

        # 第三步：保存结果
        print("[3/3] 保存结果...")
        self.manager.set_current_working(detected_app or "Unknown", task)

        # 显示结果
        print(f"\n执行报告 (任务 ID: {result['task_id']}):")
        print(f"  状态: {result['status']}")
        print(f"  耗时: {result['start_time']} -> {result['end_time']}")
        for r in result.get("results", []):
            status_icon = "OK" if r["success"] else "FAIL"
            verify_icon = "✓验证" if r.get("verified") else "✗未验证"
            
            if r.get("mode") == "skill":
                # Skill 步骤显示
                skill_name = r.get("skill", "Unknown")
                params_str = str(r.get("params", {}))[:50]
                output_str = f" | {r['output'][:60]}" if r.get("output") else ""
                print(f"  步骤{r['step_index']}: [{status_icon}] [{verify_icon}] [Skill] {skill_name}({params_str}){output_str}")
            else:
                # Direct Action 步骤显示
                action = r.get("action", "?")
                target = r.get("target", "")
                content_str = f" [{r['content'][:20]}]" if r.get("content") else ""
                output_str = f" | {r['output'][:60]}" if r.get("output") else ""
                print(f"  步骤{r['step_index']}: [{status_icon}] [{verify_icon}] {action} -> {target}{content_str}{output_str}")

        if result.get("screenshots"):
            print(f"  截图: {result['screenshots']}")

        # 记录经验
        app_for_exp = detected_app or "通用任务"
        lessons = f"任务'{task}'完成，状态: {result['status']}"
        self.agent.record_experience(app_for_exp, task, result["status"], lessons)

    def do_parallel(self, arg):
        """规划并行执行方案
用法: parallel <任务1> | <任务2> | <任务3>"""
        if not arg.strip():
            print("用法: parallel <任务1> | <任务2> | <任务3>")
            return

        tasks = [t.strip() for t in arg.split("|") if t.strip()]
        if len(tasks) < 2:
            print("需要至少2个任务才能规划并行执行")
            return

        print(f"\n为 {len(tasks)} 个任务规划并行方案...")
        plan_file = self.executor.plan_parallel_execution(tasks, self.agent)
        print(f"并行执行规划已保存: {plan_file}")

    # ========== 配置相关命令 ==========

    def do_config(self, arg):
        """显示或修改配置
用法: config              - 显示当前配置
      config set <key> <value> - 修改配置项"""
        arg = arg.strip()
        config = load_config()

        if not arg:
            import json
            print(json.dumps(config, indent=2, ensure_ascii=False))
            return

        parts = arg.split(maxsplit=2)
        if parts[0] == "set" and len(parts) >= 3:
            key = parts[1]
            value = parts[2]
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass  # 保持字符串格式

            # 支持点号分隔的嵌套key，如 agent.api_key
            keys = key.split(".")
            target = config
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value

            from toolmaster.config import save_config
            save_config(config)
            print(f"配置已更新: {key} = {value}")
        else:
            print("用法: config 或 config set <key> <value>")

    # ========== 语音输入规划命令 ==========

    def do_voice(self, arg):
        """语音输入功能规划（暂不实现）
用法: voice"""
        voice_file = os.path.join(DATA_DIR, "voice_input.txt")
        content = (
            f"# 语音输入功能规划\n"
            f"# 生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"# 状态: 规划中，暂不实现\n"
            f"\n"
            f"## 设计方案\n"
            f"1. 使用 speech_recognition 库进行语音转文字（STT）\n"
            f"2. 支持实时录音和WAV文件导入两种模式\n"
            f"3. 集成方案：\n"
            f"   - 导入 speech_recognition 库\n"
            f"   - 使用麦克风录音（speech_recognition.Microphone）\n"
            f"   - 调用本地离线引擎或云端API进行语音识别\n"
            f"   - 将识别文本传入CLI命令处理流程\n"
            f"4. 触发方式：\n"
            f"   - CLI命令: listen（开始录音）\n"
            f"   - 快捷键: 待定\n"
            f"   - CLI命令: listen <wav文件路径>（从文件导入）\n"
            f"5. 依赖：\n"
            f"   - speech_recognition (pip install SpeechRecognition)\n"
            f"   - pyaudio (pip install PyAudio)\n"
            f"   - 或 Azure Speech SDK / 讯飞语音SDK（云端方案）\n"
            f"6. 注意事项：\n"
            f"   - 录音时需提示用户\n"
            f"   - 识别失败时提供文字输入回退\n"
            f"   - 支持中英文混合识别\n"
            f"   - 录音文件临时存储，处理完毕后清理\n"
        )
        write_text_file(voice_file, content)
        print(f"语音输入规划已保存: {voice_file}")
        print("\n语音输入功能暂未实现，规划要点：")
        print("  - 使用 speech_recognition 库进行STT")
        print("  - 支持实时录音导入和WAV文件导入")
        print("  - 识别文本传入CLI命令处理流程")

    # ========== 通用命令 ==========

    def do_help(self, arg):
        """显示帮助信息"""
        if arg:
            super().do_help(arg)
            return

        help_text = """
ToolMaster 命令列表
═══════════════════════════════════════════════════════════

【窗口扫描】
  scan <窗口名称>      扫描指定窗口的UI元素并分析
  windows [过滤关键字]  列出当前可见窗口

【应用管理】
  dir [应用名称]        查看应用目录(无参数=全部，指定=详情)
  status                显示系统当前状态
  register <窗口名> <扫描文件> [分析文件]  手动注册应用
  set_task <应用> <任务>   设置当前工作状态
  clear_task               清除当前工作状态

【Agent智能】
  think <问题>          让Agent思考一个问题
  plan <任务描述>       让Agent生成任务执行计划

【经验记忆】
  record <应用> <任务> <结果> <经验>  记录操作经验
  experience [应用] [关键词]         查询操作经验

【任务执行】
  execute <任务>        执行Agent规划的任务
  parallel <任务1> | <任务2> | ...   规划并行执行方案

【其他】
  voice                 查看语音输入功能规划
  config [set <key> <value>] 查看/修改配置
  quit / exit           退出程序
"""
        print(help_text)

    def do_quit(self, arg):
        """退出ToolMaster"""
        print("再见！")
        return True

    def do_exit(self, arg):
        """退出ToolMaster"""
        return self.do_quit(arg)

    def emptyline(self):
        """空行不重复执行上一条命令"""
        pass

    def default(self, line):
        """处理未知命令"""
        if line.strip():
            print(f"未知命令: '{line}'，输入 help 查看可用命令")


def main():
    """ToolMaster 入口函数"""
    try:
        cli = ToolMasterCLI()
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n\n再见！")
        sys.exit(0)


if __name__ == "__main__":
    main()
