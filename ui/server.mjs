// ─── zicatAgent Web TUI 桥服务 ───
//
// 职责：spawn Python 内核（agentmain.py --rpc），把 JSONL 事件经 SSE 推给浏览器，
// 把浏览器指令经 stdin 写回内核；同时托管 ui/dist 的构建产物。
// 仅用 Node 内置模块，零 npm 依赖。
//
// 用法：
//   node ui/server.mjs            # 先 npm run build 或手动建 dist，否则只有 API
//   ZICAT_UI_PORT=9000 node ui/server.mjs

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createInterface } from "node:readline";
import { stat, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const DIST = path.join(HERE, "dist");
const PORT = Number(process.env.ZICAT_UI_PORT || 8765);

const PYTHON =
  process.env.ZICAT_PYTHON ??
  path.join(ROOT, ".venv", process.platform === "win32" ? "Scripts" : "bin",
            process.platform === "win32" ? "python.exe" : "python");

// ── 内核子进程 ──
const child = spawn(PYTHON, ["-X", "utf8", path.join(ROOT, "agentmain.py"), "--rpc"], {
  cwd: ROOT,
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
});

const sseClients = new Set();
let lastReady = null; // ready 是启动时一次性事件，新连上的页面需要重放
let kernelAlive = true;

function broadcast(obj) {
  const frame = `data: ${JSON.stringify(obj)}\n\n`;
  for (const res of sseClients) {
    try {
      res.write(frame);
    } catch { /* 客户端已断开 */ }
  }
  if (obj?.event === "ready") lastReady = obj;
}

// 内核死后写 stdin 会触发 EPIPE 并崩掉桥进程，必须吞掉
child.stdin.on("error", () => {});

child.on("error", (err) => {
  console.error(`[bridge] 无法启动 Python 后端: ${err.message}`);
});
child.on("exit", (code) => {
  kernelAlive = false;
  lastReady = null;
  console.error(`[bridge] 后端退出 code=${code}`);
  broadcast({ event: "exit" });
});
child.stderr.on("data", (buf) => {
  const text = buf.toString().trim();
  if (text) console.error(`[kernel] ${text.split("\n").join("\n[kernel] ")}`);
});

// 内核 stdout：每行一个 JSON 事件，原样转发
createInterface({ input: child.stdout, crlfDelay: Infinity }).on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  try {
    broadcast(JSON.parse(trimmed));
  } catch {
    broadcast({ event: "notice", text: trimmed }); // 非协议行兜底显示
  }
});

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 1e6) reject(new Error("body too large"));
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

async function serveStatic(url, res) {
  if (!existsSync(DIST)) {
    res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("前端未构建：先在 ui/ 下执行 npm install && npm run build");
    return;
  }
  const rel = url === "/" ? "index.html" : url.replace(/^\//, "");
  let file = path.normalize(path.join(DIST, rel));
  if (!file.startsWith(DIST)) file = path.join(DIST, "index.html"); // 防目录穿越
  try {
    const info = await stat(file);
    if (info.isDirectory()) file = path.join(file, "index.html");
    const body = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch {
    const body = await readFile(path.join(DIST, "index.html"));
    res.writeHead(200, { "Content-Type": MIME[".html"] });
    res.end(body);
  }
}

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/events") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.on("error", () => sseClients.delete(res)); // 断连写入异常，防止崩桥
    res.write(": connected\n\n");
    if (!kernelAlive) res.write(`data: ${JSON.stringify({ event: "exit" })}\n\n`);
    else if (lastReady) res.write(`data: ${JSON.stringify(lastReady)}\n\n`);
    sseClients.add(res);
    req.on("close", () => sseClients.delete(res));
    return;
  }

  if (req.method === "POST" && req.url === "/send") {
    if (!kernelAlive) {
      res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("内核已退出，请重启 ui/server.mjs");
      return;
    }
    try {
      const body = (await readBody(req)).trim();
      if (body) child.stdin.write(body + "\n");
      res.writeHead(204);
      res.end();
    } catch (err) {
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
      res.end(String(err?.message || err));
    }
    return;
  }

  if (req.method === "GET") return void (await serveStatic(req.url || "/", res));

  res.writeHead(405);
  res.end();
});

// SSE 保活，防代理断连
setInterval(() => {
  for (const res of sseClients) res.write(": ping\n\n");
}, 15000).unref();

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[bridge] zicatAgent TUI → http://127.0.0.1:${PORT}`);
  console.log(`[bridge] 内核: ${PYTHON} agentmain.py --rpc`);
});

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    try {
      child.stdin.write(JSON.stringify({ type: "exit" }) + "\n");
    } catch { /* 已退出 */ }
    setTimeout(() => {
      child.kill();
      process.exit(0);
    }, 500);
  });
}
