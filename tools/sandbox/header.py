"""sandbox_run 审计钩子护栏（拼接在用户代码前执行）。

占位符由 do_sandbox_run 替换：__SANDBOX_DIR__ / __NETWORK__ / __ROOT__。
定位：防 agent 误操作（删文件/写系统/起进程/偷读密钥/乱联网）的进程级护栏，
非对抗性安全边界（PEP 578 审计机制，理论上存在绕过面；诚实边界见工具描述）。
"""
import os
import sys
import sysconfig
import tempfile

sys.dont_write_bytecode = True

_SANDBOX_DIR = os.path.abspath(r"__SANDBOX_DIR__")
_ROOT = os.path.abspath(r"__ROOT__")
_NETWORK = __NETWORK__

# 敏感环境变量剥离（密钥不进沙箱进程）
for _k in list(os.environ):
    if any(t in _k.upper() for t in ("ZICAT", "APIKEY", "APIBASE", "TOKEN", "SECRET", "PASSWORD")):
        os.environ.pop(_k, None)

# 读白名单：标准库/site-packages（保 import）、系统临时目录、沙箱目录
_READ_OK = []
for _p in ("stdlib", "purelib", "platstdlib", "platlib"):
    _v = sysconfig.get_paths().get(_p)
    if _v:
        _READ_OK.append(os.path.abspath(_v))
_READ_OK += [os.path.dirname(os.path.abspath(sys.executable)),
             os.path.abspath(tempfile.gettempdir()), _SANDBOX_DIR]


def _rel_ok(path, roots):
    try:
        ap = os.path.abspath(path)
    except Exception:
        return False
    return any(ap == r or ap.startswith(r + os.sep) for r in roots)


def _deny(event, why):
    raise PermissionError(f"[sandbox] 禁止操作（{event}）: {why}")


def _hook(event, args):
    # 文件读写
    if event == "open":
        path, mode = args[0], (args[1] if len(args) > 1 else "") or ""
        writing = any(c in mode for c in ("w", "a", "x", "+"))
        if writing:
            if not _rel_ok(path, [_SANDBOX_DIR, os.path.abspath(tempfile.gettempdir())]):
                _deny(event, f"写仅限沙箱目录: {path}")
        else:
            low = str(path).replace("\\", "/").lower()
            if ".env" in low.split("/")[-1:] or "mykey" in low:
                _deny(event, f"敏感文件拒读: {path}")
            if _rel_ok(path, [_ROOT]) and not _rel_ok(path, [_SANDBOX_DIR]):
                _deny(event, f"仓库源码拒读（沙箱内不可见）: {path}")
            if not _rel_ok(path, _READ_OK) and os.path.exists(path) and not _rel_ok(path, [_SANDBOX_DIR]):
                # 允许读不存在/白名单路径的探测；存在但不在白名单的读取拒（如用户主目录文件）
                home = os.path.abspath(os.path.expanduser("~"))
                if _rel_ok(path, [home]):
                    _deny(event, f"用户目录拒读: {path}")
    # 子进程
    elif event in ("subprocess.Popen", "os.system", "os.popen", "os.posix_spawn",
                   "os.spawn", "os.fork", "winexec"):
        _deny(event, "沙箱内禁止再起进程")
    # 网络
    elif not _NETWORK and event in ("socket.connect", "socket.bind", "socket.getaddrinfo",
                                    "socket.sendto", "socket.gethostbyname"):
        _deny(event, "网络默认禁用；确需联网请传 network=true 并征得用户同意")
    # C 层/动态库
    elif event in ("ctypes.dlopen", "ctypes.dlsym", "ctypes.dlsym/handle", "ctypes.cdata",
                   "ctypes.cdata/buffer", "_winapi.CreateProcess"):
        _deny(event, "ctypes/C 层调用禁用")
    # 文件系统改动：限沙箱目录
    elif event in ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.symlink",
                   "os.link", "os.truncate", "os.replace"):
        target = args[0] if args else ""
        if not _rel_ok(target, [_SANDBOX_DIR]):
            _deny(event, f"文件系统改动仅限沙箱目录: {target}")


sys.addaudithook(_hook)
