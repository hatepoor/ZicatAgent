"""代码执行工具：code_run（生成器执行器）+ sandbox_run。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from tools.registry import register
from tools.util import smart_format

HEADER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sandbox', 'header.py')

SANDBOX_NETWORK_PATTERNS = ("socket.", "requests.", "urllib.request", "http.client",
                            "urlopen", "smtplib", "ftplib", "webbrowser")
SANDBOX_DANGER_PATTERNS = ("subprocess", "os.system", "os.popen", "os.exec", "os.spawn",
                           "ctypes.", "shutil.rmtree", "_winapi", "winreg")


def sandbox_scan(code: str, network: bool) -> list:
    """静态扫描高危模式；network=true 时网络类不再计入（已获用户放行）。"""
    patterns = list(SANDBOX_DANGER_PATTERNS)
    if not network:
        patterns += list(SANDBOX_NETWORK_PATTERNS)
    return sorted({p for p in patterns if p in code})


def code_run(code, code_type="python", timeout=60, cwd=None, code_cwd=None,
             stop_signal=None, maxlen=10000, myprint=None, script_dir=None):
    """代码执行器。python: 文件模式；powershell/bash: 命令模式。"""
    from tools.util import safe_print
    myprint = myprint or safe_print
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    preview = (code[:60].replace('\n', ' ') + '...') if len(code) > 60 else code.strip()
    yield f"[Action] Running {code_type} in {os.path.basename(cwd)}: {preview}\n"
    cwd = cwd or os.path.join(root, 'temp')
    tmp_path = None
    if code_type in ["python", "py"]:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".ai.py", delete=False, mode='w',
                                               encoding='utf-8', dir=code_cwd)
        cr_header = os.path.join(root, 'assets', 'code_run_header.py')
        if os.path.exists(cr_header):
            tmp_file.write(open(cr_header, encoding='utf-8').read())
        tmp_file.write(code)
        tmp_path = tmp_file.name
        tmp_file.close()
        cmd = [sys.executable, "-X", "utf8", "-u", tmp_path]
    elif code_type in ["powershell", "bash", "sh", "shell", "ps1", "pwsh"]:
        if os.name == 'nt':
            _ps = "pwsh" if shutil.which("pwsh") else "powershell"
            utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            cmd = [_ps, "-NoProfile", "-NonInteractive", "-Command", utf8_prefix + code]
        else:
            cmd = ["bash", "-c", code]
    else:
        return {"status": "error", "msg": f"不支持的类型: {code_type}"}
    myprint("code run output:")
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    full_stdout = []

    def stream_reader(proc, logs):
        try:
            for line_bytes in iter(proc.stdout.readline, b''):
                try:
                    line = line_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    line = line_bytes.decode('gbk', errors='ignore')
                logs.append(line)
                myprint(line, end="")
        except Exception:
            pass

    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, cwd=cwd, startupinfo=startupinfo,
            creationflags=0x08000000 if os.name == 'nt' else 0
        )
        start_t = time.time()
        t = threading.Thread(target=stream_reader, args=(process, full_stdout), daemon=True)
        t.start()

        while t.is_alive():
            istimeout = time.time() - start_t > timeout
            if istimeout or stop_signal:
                process.kill()
                myprint("[Debug] Process killed due to timeout or stop signal.")
                if istimeout:
                    full_stdout.append("\n[Timeout Error] 超时强制终止")
                else:
                    full_stdout.append("\n[Stopped] 用户强制终止")
                break
            time.sleep(1)

        t.join(timeout=1)
        exit_code = process.poll()

        stdout_str = "".join(full_stdout)
        status = "success" if exit_code == 0 else "error"
        status_icon = "✅" if exit_code == 0 else "❌"
        if exit_code is None:
            status_icon = "⏳"
        output_snippet = smart_format(stdout_str, max_str_len=600,
                                      omit_str='\n\n[omitted long output]\n\n')
        output_snippet = re.sub(r'`{4,}', lambda m: m.group(0)[:3] + '\u200b' + m.group(0)[3:],
                                output_snippet)
        yield f"[Status] {status_icon} Exit Code: {exit_code}\n[Stdout]\n{output_snippet}\n"
        if process.stdout:
            threading.Thread(target=process.stdout.close, daemon=True).start()
        return {
            "status": status,
            "stdout": smart_format(stdout_str, max_str_len=maxlen,
                                   omit_str='\n\n[omitted long output]\n\n'),
            "exit_code": exit_code
        }
    except Exception as e:
        if 'process' in locals():
            process.kill()
        return {"status": "error", "msg": str(e)}
    finally:
        if code_type == "python" and tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@register("code_run")
def do_code_run(ctx, args, response):
    """执行代码片段，有长度限制，不允许代码中放大量数据，如有需要应当通过文件读取进行。"""
    code_type = args.get("type") or "python"
    code = args.get("code") or args.get("script")
    if not code:
        code = ctx.extract_code_block(response, code_type)
        if not code:
            return __import__('agent_types').StepOutcome(
                "[Error] Code missing. Must use reply code block or 'script' arg.", next_prompt="\n")
    if not args.get("type") and re.match(r"^\s*(ls|cd|pwd|dir|echo|cat|git|pip|npm|curl|ssh)(\s|$)", code):
        code_type = "shell"
    timeout = args.get("timeout", 60)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 60
    raw_path = os.path.join(ctx.cwd, args.get("cwd", './'))
    cwd = os.path.normpath(os.path.abspath(raw_path))
    code_cwd = os.path.normpath(ctx.cwd)
    maxlen = ctx.get_tool_maxlen(10000, args)
    if timeout > 600:
        result = ('[ERROR] Timeout must be <= 600 seconds; code not executed. Run time-consuming '
                  'code in the background instead of waiting for it to finish in the foreground, '
                  'verify it started successfully, and monitor it until completion or failure.')
    elif code_type == 'python' and args.get("inline_eval", False):
        ns = {'handler': ctx.handler, 'parent': ctx.parent,
              'history': json.dumps(list(getattr(ctx.parent, 'history', []))[-50:], ensure_ascii=False)}
        old_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            try:
                try:
                    result = repr(eval(code, ns))
                except SyntaxError:
                    exec(code, ns)
                    result = ns.get('_r', 'OK')
            except Exception as e:
                result = f'Error: {e}'
        finally:
            os.chdir(old_cwd)
    else:
        result = yield from code_run(code, code_type, timeout, cwd, code_cwd=code_cwd,
                                     stop_signal=ctx.code_stop_signal, maxlen=maxlen,
                                     myprint=ctx.print)
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    from agent_types import StepOutcome
    return StepOutcome(result, next_prompt=next_prompt)


@register("sandbox_run")
def do_sandbox_run(ctx, args, response):
    """护栏沙箱内执行 python（调研计算/数据处理/不可信临时代码）。

    双阶段确认：静态扫描命中高危模式且未 confirmed 时，要求先 ask_user。
    本地开发/需直接操作仓库与用户文件请走 code_run。
    """
    from agent_types import StepOutcome
    code = args.get("code") or args.get("script") or ctx.extract_code_block(response, "python")
    if not code:
        return StepOutcome("[Error] code missing (use 'code' arg or reply python code block)",
                           next_prompt="\n")
    if args.get("type") and args["type"] != "python":
        return StepOutcome({"status": "error",
                            "msg": "sandbox_run 仅支持 python；shell/系统操作用 code_run"},
                           next_prompt="\n")
    network = bool(args.get("network", False))
    confirmed = bool(args.get("confirmed", False))
    dangerous = sandbox_scan(code, network)
    if dangerous and not confirmed:
        return StepOutcome({
            "status": "confirm_required", "patterns": dangerous,
            "msg": "检测到高危模式：须先 ask_user 征得用户明确同意，再带 confirmed=true 重试",
        }, next_prompt="\n")
    sb_dir = os.path.join(ctx.cwd, "sandbox")
    os.makedirs(sb_dir, exist_ok=True)
    header_path = HEADER_PATH
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        header = open(header_path, encoding='utf-8').read()
    except OSError as e:
        return StepOutcome({"status": "error", "msg": f"sandbox header 缺失: {e}"}, next_prompt="\n")
    header = (header
              .replace("__SANDBOX_DIR__", sb_dir.replace("\\", "\\\\"))
              .replace("__ROOT__", root.replace("\\", "\\\\"))
              .replace("__NETWORK__", "True" if network else "False"))
    full_code = header + "\n\n# ===== sandbox user code =====\n" + code
    timeout = args.get("timeout", 120)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 120
    result = yield from code_run(full_code, "python", timeout, sb_dir, code_cwd=sb_dir,
                                 stop_signal=ctx.code_stop_signal,
                                 maxlen=ctx.get_tool_maxlen(10000, args), myprint=ctx.print)
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    return StepOutcome(result, next_prompt=next_prompt)
