"""web_scan 双场景基准:每轮 B=全冷(杀光 master 后), A=紧接重启。输出逐轮与汇总。"""
import json, subprocess, sys, time, socket
import psutil

PY = '.venv/Scripts/python.exe'
SCRIPT = 'temp/test_web_scan.py'


def port_alive(port=18766):
    s = socket.socket(); s.settimeout(0.3)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def kill_masters():
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cl = p.info['cmdline'] or []
            if any('TMWebDriver.py' in c for c in cl):
                p.kill()
        except Exception:
            pass
    for _ in range(40):
        if not port_alive():
            return True
        time.sleep(0.25)
    return False


def run_one():
    r = subprocess.run([PY, SCRIPT], capture_output=True, text=True, timeout=180)
    lines = [l for l in r.stdout.strip().splitlines() if l.startswith('{')]
    if not lines:
        return {'ok': False, 'time_s': None, 'error': (r.stdout + r.stderr)[-200:]}
    return json.loads(lines[-1])


def main(n=5):
    rows = []
    for i in range(1, n + 1):
        kill_masters(); time.sleep(0.5)
        b = run_one()   # 场景 B:全冷(产线首启)
        a = run_one()   # 场景 A:agent 进程重启(master 状态取决于版本)
        rows.append((b, a))
        print(f"轮{i}: B(全冷) ok={b['ok']} {b['time_s']}s tabs={b.get('tabs')}"
              f" | A(重启) ok={a['ok']} {a['time_s']}s tabs={a.get('tabs')}", flush=True)

    for name, idx in (("B 全冷", 0), ("A 重启", 1)):
        ts = [r[idx]['time_s'] for r in rows if r[idx].get('ok')]
        if ts:
            print(f"{name}: 成功 {len(ts)}/{n} 平均 {sum(ts)/len(ts):.2f}s 最快 {min(ts)}s 最慢 {max(ts)}s")
        else:
            print(f"{name}: 0/{n} 全部失败")


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
