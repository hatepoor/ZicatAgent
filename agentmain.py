import os, sys, threading, queue, time, json, re, random, locale, glob
os.environ.setdefault('ZICAT_LANG', 'zh' if any(k in (locale.getlocale()[0] or '').lower() for k in ('zh', 'chinese')) else 'en')
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
elif hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(errors='replace')
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
elif hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(errors='replace')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zicat import ZicatAgentHandler, smart_format, get_global_memory, format_error, consume_file
from core import commands as core_commands

DEFAULT_ENGINE = 'graph'   # P5 后仅保留 LangGraph 引擎

script_dir = os.path.dirname(os.path.abspath(__file__))

lang_suffix = '_en' if os.environ.get('ZICAT_LANG', '') == 'en' else ''
mem_dir = os.path.join(script_dir, 'memory')
if not os.path.exists(mem_dir): os.makedirs(mem_dir)
mem_txt = os.path.join(mem_dir, 'facts.txt')
if not os.path.exists(mem_txt): open(mem_txt, 'w', encoding='utf-8').write('# [Global Memory - L2]\n')
mem_insight = os.path.join(mem_dir, 'l1_fallback.txt')
if not os.path.exists(mem_insight):
    t = os.path.join(script_dir, f'assets/l1_template{lang_suffix}.txt')
    open(mem_insight, 'w', encoding='utf-8').write(open(t, encoding='utf-8').read() if os.path.exists(t) else '')

def get_system_prompt():
    with open(os.path.join(script_dir, f'assets/sys_prompt{lang_suffix}.txt'), 'r', encoding='utf-8') as f: prompt = f.read()
    prompt += f"\nToday: {time.strftime('%Y-%m-%d %a')}\n"
    prompt += get_global_memory()
    return prompt

# SDK 用法示例（后台起一个 agent，然后投递任务、从返回队列取输出）：
# agent = ZicatAgent(); threading.Thread(target=agent.run, daemon=True).start()
# output1_queue = agent.put_task(prompt1)
# output2_queue = agent.put_task(prompt2)
class ZicatAgent:
    def __init__(self):
        os.makedirs(os.path.join(script_dir, 'temp'), exist_ok=True)
        self.lock = threading.Lock()
        self.task_dir = None
        self.history = []; self.handler = None; self.all_outputs = []
        self.task_queue = queue.Queue() 
        self.is_running = False; self.stop_sig = False
        # 当前正在执行任务的输出队列（空闲时为 None）。让丢失句柄的 UI（刷新页面、
        # 第二个客户端）能重新挂到正在跑的任务上。
        self._current_queue = None  
        self.inc_out = False; self.verbose = True
        self.peer_hint = True
        logid = f'{(time.time_ns() + random.randrange(1_000_000)) % 1_000_000:06d}'
        self.log_path = os.path.join(script_dir, f'temp/model_responses/model_responses_{logid}.txt')
        self.engine = DEFAULT_ENGINE
        self.graph_thread_id = ''
        # FIX-S 会话分离：当前会话的工作目录（注册表绑定；handler/工具 cwd 跟随）
        self.default_workspace = os.path.abspath(os.path.join(os.getcwd(), 'temp'))
        self.workspace_root = self.default_workspace
        self.workspace_exact = False       # 用户显式指定工作空间时，不再套标题子目录
        self.workspace_dir = self.default_workspace
        try:
            os.makedirs(self.default_workspace, exist_ok=True)
        except OSError:
            pass
        self.last_graph_usage = {}
        self.pending_interrupts = []
        self.graph_rewind_to = ''
        self.graph_drop_thread = False   # 首轮被中断：下个任务先清空该 thread
        # 中断回退按 thread 记账：中途切走再切回来，被取消的指令仍然不会复活
        self.graph_rewinds = {}          # thread_id -> checkpoint_id
        self.graph_drop_threads = set()  # 首轮中断且无可回退检查点的 thread
        self.extra_sys_prompts = []
        self.intervene = self.extrakeyinfo = None

    def get_llm_name(self, b=None, model=False):
        try:
            from engine.settings import oai_configs
            cfg = (oai_configs() or [{}])[0]
        except Exception:
            cfg = {}
        if model:
            return str(cfg.get('model') or '?')
        return str(cfg.get('name') or cfg.get('model') or '?')

    def get_ctx_multiplier(self): return 1.0

    def abort(self):
        if not self.is_running: return
        print('Abort current task...')
        self.stop_sig = True
        if self.handler is not None: self.handler.code_stop_signal.append(1)
            
    def put_task(self, query, source="user", images=None):
        display_queue = queue.Queue()
        self.task_queue.put({"query": query, "source": source, "images": images or [], "output": display_queue})
        return display_queue

    def set_workspace(self, path=None, exact=True):
        """切换工作空间；无参回到当前目录下的 temp。返回绝对路径。"""
        raw = path or os.environ.get('ZICAT_WORKSPACE') or self.default_workspace
        root = os.path.abspath(os.path.expanduser(str(raw)))
        os.makedirs(root, exist_ok=True)
        self.workspace_root = root
        self.workspace_dir = root
        self.workspace_exact = bool(exact)
        try:
            from core import sessions
            sessions.add_workspace(root)
            if self.graph_thread_id:
                self.workspace_dir = sessions.set_workspace(self.graph_thread_id, root)
        except Exception:
            pass
        return self.workspace_dir

    def get_workspace(self):
        if self.graph_thread_id:
            try:
                from core import sessions
                return sessions.workspace_of(
                    self.graph_thread_id,
                    self.workspace_root or self.default_workspace)
            except Exception:
                pass
        return self.workspace_dir or self.workspace_root or self.default_workspace

    def new_session(self):
        """开新会话：丢弃当前 thread 与内存历史，下一任务重新注册。"""
        self.graph_thread_id = ""
        self.history = []
        self.all_outputs = []
        self.pending_interrupts = []
        self.last_graph_usage = {}
        self.graph_rewind_to = ""
        self.graph_drop_thread = False
        self.stop_sig = False
        self.handler = None
        self.workspace_dir = self.workspace_root or self.default_workspace
        return {"thread_id": "", "workspace": self.workspace_dir}

    def switch_session(self, thread_id: str):
        """切到已有会话；历史上下文由 LangGraph checkpoint 提供。"""
        from core import sessions
        record = sessions.get(thread_id)
        if not record:
            raise ValueError(f"会话不存在: {thread_id}")
        self.graph_thread_id = thread_id
        self.workspace_dir = record.get("workspace_dir") or self.default_workspace
        self.workspace_root = record.get("workspace") or os.path.dirname(self.workspace_dir)
        self.history = []
        self.all_outputs = []
        self.pending_interrupts = []
        # 切会话不丢该 thread 最近一次任务的用量（/cost 与上下文面板可恢复）
        self.last_graph_usage = sessions.load_usage(thread_id) or {}
        self.graph_rewind_to = ""
        self.graph_drop_thread = False
        self.stop_sig = False
        self.handler = None
        return record

    # 我知道这很危险，但 raw_query 本身已经足够危险，不会扩大攻击面
    def _handle_slash_cmd(self, raw_query, display_queue):
        if not raw_query.startswith('/'): return raw_query
        if raw_query.strip().startswith('/session.'):
            display_queue.put({'done': "⚠️ /session.* 已随 legacy 引擎移除；请在 mykey.py 的 graph_config 中调整参数。", 'source': 'system'})
            return None
        # 斜杠命令一次可能 emit 多行；合并成一个 done，避免 RPC pump 读到第一条就 break
        messages = []
        emit = lambda msg: messages.append(str(msg))
        try:
            result = core_commands.handle(self, raw_query, emit)
        except SystemExit:
            raise
        except Exception as e:
            messages.append(f'[命令错误] {format_error(e)}')
            result = None
        if messages:
            display_queue.put({'done': "\n".join(messages), 'source': 'system'})
        return result

    def run(self):
        while True:
            task = self.task_queue.get()
            if isinstance(task, str): break
            raw_query, source, display_queue = task["query"], task["source"], task["output"]
            full_resp = ""; last_pos = 0; curr_turn = 0; turn_resps = []
            try:
                # 斜杠命令先处理：此时 is_running 仍为 False。
                raw_query = self._handle_slash_cmd(raw_query, display_queue)
                if raw_query is None: continue
                self.is_running = True; self._current_queue = display_queue
                # FIX-S：首次接任务时注册会话并绑定工作目录；handler cwd 跟随注册表
                from core import sessions as _sessions
                if not self.graph_thread_id:
                    self.graph_thread_id = f"cli-{time.time_ns()}"
                    _root = self.workspace_root or self.default_workspace
                    _title = smart_format(raw_query.replace(chr(10), ' '), max_str_len=10)
                    self.workspace_dir = _sessions.register(
                        self.graph_thread_id, _root, title=_title,
                        exact=getattr(self, 'workspace_exact', False))
                if len(raw_query) > 2000:
                    task_file = os.path.join(script_dir, 'temp', f'user_prompt_{os.getpid()}_{time.time_ns()}.md')
                    with open(task_file, 'w', encoding='utf-8') as f: f.write(raw_query)
                    raw_query = f'Long user prompt saved to {task_file}. Read and execute.'
                self.all_outputs.append({"input": raw_query, "outputs": turn_resps})
                if len(self.all_outputs) > 10000: self.all_outputs = self.all_outputs[-5000:]
                rquery = smart_format(raw_query.replace('\n', ' '), max_str_len=200)
                self.history.append(f"[USER]: {rquery}")
                sys_prompt = get_system_prompt() + '\n'.join(self.extra_sys_prompts)
                if self.peer_hint: sys_prompt += f"\n[Peer] 用户提及其他会话/后台任务状态时: temp/model_responses/ (只找近期修改的文件尾部)\n"
                _ws = self.get_workspace()
                handler = ZicatAgentHandler(self, self.history, _ws)
                if getattr(self, 'no_print', False): handler.print = lambda *a, **k: None
                if self.handler and 'key_info' in self.handler.working:
                    ki = re.sub(r'\n\[SYSTEM\] 此为.*?工作记忆[。\n]*', '', self.handler.working['key_info'])  # 去旧
                    handler.working['key_info'] = ki
                    handler.working['passed_sessions'] = ps = self.handler.working.get('passed_sessions', 0) + 1
                    if ps > 0: handler.working['key_info'] += f'\n[SYSTEM] 此为 {ps} 个对话前设置的key_info，若已在新任务，先更新或清除工作记忆。\n'
                self.handler = handler
                from engine.runner import run_graph_task
                bridge = getattr(self, '_rpc_bridge', None)
                final_text, usage, _tid = run_graph_task(
                    self, raw_query, display_queue, handler, sys_prompt, source=source,
                    interrupt_handler=(bridge.ask if bridge is not None else None))
                full_resp = final_text
                turn_resps = [final_text]
                self.history = handler.history_info
                if usage.get('requests'):
                    display_queue.put({'next': f"\n[usage] req={usage['requests']} in={usage['input']} out={usage['output']}\n",
                                       'source': source})
                display_queue.put({'done': full_resp, 'source': source, 'turn': 1, 'outputs': turn_resps.copy()})
            except Exception as e:
                print(f"Backend Error: {format_error(e)}")
                display_queue.put({'done': full_resp + f'\n```\n{format_error(e)}\n```', 'source': source, 'turn': curr_turn, 'outputs': turn_resps.copy()})
            finally:
                if self.stop_sig: print('User aborted the task.')
                if self.handler is not None: self.handler.code_stop_signal.append(1)
                self.is_running = self.stop_sig = False  # 保留 _current_queue 以便取回最终输出
                self.task_queue.task_done()


if __name__ == '__main__':
    import argparse
    from datetime import datetime
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', metavar='IODIR', help='一次性任务模式，先看subagent.md')
    parser.add_argument('--func', metavar='PROMPT_FILE', help='纯函数模式：读prompt文件→结果写prompt.out.txt→退出')
    parser.add_argument('--reflect', metavar='SCRIPT', help='反射模式：加载监控脚本，check()触发时发任务')
    parser.add_argument('--input', help='prompt')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--nobg', action='store_true')
    parser.add_argument('--nolog', action='store_true')
    parser.add_argument('--no-user-tools', action='store_true')
    parser.add_argument('--rpc', action='store_true',
                        help='JSONL 协议模式（给 TypeScript CLI 用）：stdout 只输出事件')
    parser.add_argument('--workspace', metavar='DIR',
                        help='指定工作空间（默认：当前目录下的 temp，不存在则创建）')
    args, _unknown = parser.parse_known_args()
    _extra_args = dict(zip([k.lstrip('-') for k in _unknown[::2]], _unknown[1::2])) if _unknown else {}

    # RPC 模式：Agent 的所有 print 改走 stderr，stdout 留给 JSONL 事件
    rpc_out = sys.stdout if args.rpc else None
    if args.rpc:
        sys.stdout = sys.stderr

    if (args.func or args.task) and not args.nobg:
        import subprocess, platform
        cmd = [sys.executable, os.path.abspath(__file__)] + [a for a in sys.argv[1:]] + ['--nobg']
        if args.task:
            d = os.path.join(script_dir, f'temp/{args.task}'); os.makedirs(d, exist_ok=True)
            out = open(os.path.join(d, 'stdout.log'), 'w', encoding='utf-8')
            err = open(os.path.join(d, 'stderr.log'), 'w', encoding='utf-8')
        else: out, err = subprocess.DEVNULL, subprocess.DEVNULL
        p = subprocess.Popen(cmd, cwd=script_dir,
            creationflags=0x08000000 if platform.system() == 'Windows' else 0,
            stdout=out, stderr=err)
        print('PID:', p.pid); sys.exit(0)

    agent = ZicatAgent()
    if args.workspace:
        agent.set_workspace(args.workspace, exact=True)
    if args.nolog: agent.log_path = False
    agent.verbose = args.verbose
    threading.Thread(target=agent.run, daemon=True).start()

    if args.rpc:
        from core.rpc import rpc_main
        rpc_main(agent, rpc_out or sys.stderr)
        sys.exit(0)

    if args.task:
        agent.task_dir = d = os.path.join(script_dir, f'temp/{args.task}'); nround = ''
        infile = os.path.join(d, 'input.txt'); outfile = f'{d}/output{nround}.txt'
        if args.input:
            os.makedirs(d, exist_ok=True)
            [os.remove(f) for f in glob.glob(os.path.join(d, 'output*.txt'))]
            with open(infile, 'w', encoding='utf-8') as f: f.write(args.input)
    elif args.func:
        infile = args.func; outfile = os.path.splitext(args.func)[0] + '.out.txt'

    if args.func or args.task:
        agent.peer_hint = False
        with open(infile, encoding='utf-8') as f: raw = f.read()
        while True:
            dq = agent.put_task(raw, source='func' if args.func else 'task')
            while 'done' not in (item := dq.get(timeout=2200)):
                if 'next' in item:
                    with open(outfile, 'w', encoding='utf-8') as f: f.write(item.get('next', ''))
            with open(outfile, 'w', encoding='utf-8') as f: f.write(item['done'] + '\n\n[ROUND END]\n')
            if not args.task: break
            consume_file(d, '_stop')  # 已经成功停下来了，避免打断下次reply
            for _ in range(300):  # 等reply.txt，10分钟超时
                time.sleep(2)
                if (raw := consume_file(d, 'reply.txt')): break
            else: break
            nround = nround + 1 if isinstance(nround, int) else 1
            outfile = f'{d}/output{nround}.txt'
    elif args.reflect:
        agent.peer_hint = False
        import importlib.util
        spec = importlib.util.spec_from_file_location('reflect_script', args.reflect)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        if hasattr(mod, 'init'): mod.init(_extra_args)
        _mt = os.path.getmtime(args.reflect)
        print(f'[Reflect] loaded {args.reflect}' + (f' args={_extra_args}' if _extra_args else ''))
        while True:
            if os.path.getmtime(args.reflect) != _mt:
                try:
                    spec.loader.exec_module(mod); _mt = os.path.getmtime(args.reflect)
                    if hasattr(mod, 'init'): mod.init(_extra_args)
                    print('[Reflect] reloaded')
                except Exception as e: print(f'[Reflect] reload error: {e}')
            try: task = mod.check()
            except Exception as e: 
                print(f'[Reflect] check() error: {e}'); task = None
            if task and task == '/exit': break
            if task:
                print(f'[Reflect] triggered: {task[:80]}')
                dq = agent.put_task(task, source='reflect')
                try:
                    while 'done' not in (item := dq.get(timeout=2200)): pass
                    result = item['done']
                    print(result)
                except Exception as e:
                    if getattr(mod, 'ONCE', False): raise
                    print(f'[Reflect] drain error: {e}'); result = f'[ERROR] {e}'
                log_dir = os.path.join(script_dir, 'temp/reflect_logs'); os.makedirs(log_dir, exist_ok=True)
                script_name = os.path.splitext(os.path.basename(args.reflect))[0]
                open(os.path.join(log_dir, f'{script_name}_{datetime.now():%Y-%m-%d}.log'), 'a', encoding='utf-8').write(f'[{datetime.now():%m-%d %H:%M}]\n{result}\n\n')
                if (on_done := getattr(mod, 'on_done', None)):
                    try: on_done(result)
                    except Exception as e: print(f'[Reflect] on_done error: {e}')
                if getattr(mod, 'ONCE', False): print('[Reflect] ONCE=True, exiting.'); break
            time.sleep(getattr(mod, 'INTERVAL', 5))
    else:
        print("zicatAgent 只保留 Web UI：请运行 `node ui/server.mjs` 后打开 "
              "http://127.0.0.1:8765/。", file=sys.stderr)
        sys.exit(2)
