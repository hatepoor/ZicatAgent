"""浏览器工具：web_scan / web_execute_js（TMWebDriver 桥）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from agent_types import json_default
from tools.registry import register
from tools.util import format_error, smart_format

driver = None


def _master_alive(port=18766, timeout=0.3):
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def _ensure_master(timeout=15):
    """优先接入常驻 master；没有则后台拉起一个，避免每个 agent 进程各自起服务导致扩展反复重连。"""
    if _master_alive():
        return True
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    entry = os.path.join(root, "TMWebDriver.py")
    flags = 0
    if sys.platform == 'win32':
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                 | subprocess.CREATE_NO_WINDOW)
    try:
        subprocess.Popen([sys.executable, entry], cwd=root, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags)
    except Exception:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _master_alive():
            return True
        time.sleep(0.25)
    return False


def first_init_driver(max_wait=60):
    global driver
    from TMWebDriver import TMWebDriver
    _ensure_master()
    driver = TMWebDriver()
    opened = False
    for i in range(max_wait):
        time.sleep(1)
        try:
            sess = driver.get_all_sessions()
        except Exception:
            sess = []
        if len(sess) > 0:
            break
        if not opened and i >= 2:
            import webbrowser
            webbrowser.open("https://example.com")
            opened = True


NO_TAB_HINT = ("没有可用的浏览器标签页:浏览器扩展(TMWD CDP Bridge)未连上 master。"
               "排查:1)浏览器已打开普通网页(chrome://页不可注入);"
               "2)扩展已加载且未停用(assets/tmwd_cdp_bridge);"
               "3)18765/18766端口未被残留进程占用;若仍失败,查L3记忆分析原因。")


def _web_scan(tabs_only=False, switch_tab_id=None, text_only=False, maxlen=35000):
    """获取当前页面的简化HTML内容和标签页列表。"""
    global driver
    import simphtml
    try:
        if driver is None:
            first_init_driver()
        if len(driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": NO_TAB_HINT}
        tabs = []
        for sess in driver.get_all_sessions():
            sess.pop('connected_at', None)
            sess.pop('type', None)
            sess['url'] = sess.get('url', '')[:50] + ("..." if len(sess.get('url', '')) > 50 else "")
            tabs.append(sess)
        if switch_tab_id:
            driver.set_default_session(switch_tab_id)
        result = {
            "status": "success",
            "metadata": {
                "tabs_count": len(tabs), "tabs": tabs,
                "active_tab": driver.default_session_id
            }
        }
        if not tabs_only:
            result["content"] = simphtml.get_html(driver, cutlist=True, maxchars=maxlen,
                                                  text_only=text_only)
            if text_only:
                result['content'] = smart_format(result['content'], max_str_len=maxlen // 3,
                                                 omit_str='\n\n[omitted long content]\n\n')
        return result
    except Exception as e:
        return {"status": "error", "msg": format_error(e)}


def _web_execute_js(script, switch_tab_id=None, no_monitor=False):
    """执行 JS 脚本来控制浏览器，并捕获结果和页面变化"""
    global driver
    import simphtml
    try:
        if driver is None:
            first_init_driver()
        if len(driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": NO_TAB_HINT}
        if switch_tab_id:
            driver.set_default_session(switch_tab_id)
        result = simphtml.execute_js_rich(script, driver, no_monitor=no_monitor)
        return result
    except Exception as e:
        return {"status": "error", "msg": format_error(e)}


@register("web_scan")
def do_web_scan(ctx, args, response):
    """获取当前页面内容和标签页列表。也可用于切换标签页。
    注意：HTML经过简化，边栏/浮动元素等可能被过滤。如需查看被过滤的内容请用execute_js。
    tabs_only=true时仅返回标签页列表，不获取HTML（省token）"""
    from tools.util import _arg
    tabs_only = _arg(args, "tabs_only", False, bool)
    switch_tab_id = args.get("switch_tab_id", None)
    text_only = _arg(args, "text_only", False, bool)
    maxlen = ctx.get_tool_maxlen(35000, args, growth_rate=0.5)
    result = _web_scan(tabs_only=tabs_only, switch_tab_id=switch_tab_id, text_only=text_only,
                       maxlen=maxlen)
    content = result.pop("content", None)
    yield f'[Info] {str(result)}\n'
    if content:
        result = (json.dumps(result, ensure_ascii=False, default=json_default)
                  + f"\n```html\n{content}\n```")
    next_prompt = "\n"
    from agent_types import StepOutcome
    return StepOutcome(result, next_prompt=next_prompt)


@register("web_execute_js")
def do_web_execute_js(ctx, args, response):
    """web情况下的优先使用工具，执行任何js达成对浏览器的*完全*控制。支持将结果保存到文件供后续读取分析。"""
    from tools.util import _arg
    script = args.get("script", "") or ctx.extract_code_block(response, "javascript")
    if not script:
        return __import__('agent_types').StepOutcome(
            "[Error] Script missing. Use ```javascript block or 'script' arg.", next_prompt="\n")
    abs_path = ctx.get_abs_path(script.strip())
    if os.path.isfile(abs_path):
        with open(abs_path, 'r', encoding='utf-8') as f:
            script = f.read()
    save_to_file = args.get("save_to_file", "")
    switch_tab_id = args.get("switch_tab_id") or args.get("tab_id")
    no_monitor = _arg(args, "no_monitor", False, bool)
    result = _web_execute_js(script, switch_tab_id=switch_tab_id, no_monitor=no_monitor)
    if save_to_file and "js_return" in result:
        content = str(result["js_return"] or '')
        abs_path = ctx.get_abs_path(save_to_file)
        result["js_return"] = smart_format(content, max_str_len=170)
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(str(content))
            result["js_return"] += f"\n\n[已保存完整内容到 {abs_path}]"
        except Exception:
            result['js_return'] += f"\n\n[保存失败，无法写入文件 {abs_path}]"
    show = smart_format(json.dumps(result, ensure_ascii=False, indent=2, default=json_default),
                        max_str_len=300)
    ctx.print("Web Execute JS Result:", show)
    yield f"JS 执行结果:\n{show}\n"
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    result = json.dumps(result, ensure_ascii=False, default=json_default)
    maxlen = ctx.get_tool_maxlen(8000, args)
    from agent_types import StepOutcome
    return StepOutcome(smart_format(result, max_str_len=maxlen), next_prompt=next_prompt)
