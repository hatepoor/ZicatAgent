import { QUICK_COMMANDS } from "../../core/config";
import type { RpcCommand } from "../../core/types";

export function Welcome({
  model,
  cwd,
  commands,
  onPick,
}: {
  model: string;
  cwd: string;
  commands: RpcCommand[];
  onPick: (text: string) => void;
}) {
  const quick = QUICK_COMMANDS.map(
    (command) =>
      commands.find((item) => item.cmd === command) || { cmd: command, desc: "" },
  );
  return (
    <div className="select-none">
      <pre
        className="text-[26px] leading-8 font-bold tracking-wide"
        style={{ color: "var(--accent)" }}
      >
        {"  ▄▀█ █▀▀ █▀▀ █▄░█ ▀█▀   ▀█▀ █░█ █\n  █▀█ █▄█ ██▄ █░▀█ ░█░   ░█░ █▄█ █"}
      </pre>
      <div className="mt-1 text-[12px]" style={{ color: "var(--dim)" }}>
        <span style={{ color: "var(--accent2)" }}>◆</span> zicatAgent Web UI v0.1.1
        · 模型 <span style={{ color: "var(--cyan)" }}>{model}</span>
        {cwd && (
          <>
            {" "}· 工作目录 <span style={{ color: "var(--cyan)" }}>{cwd}</span>
          </>
        )}
      </div>
      <div
        className="mt-4 rounded-md border px-3 py-2 text-[12px] leading-5"
        style={{
          borderColor: "var(--border)",
          background: "var(--panel)",
          color: "var(--dim)",
        }}
      >
        <div>
          <span style={{ color: "var(--yellow)" }}>✱</span> 在下方输入任务，智能体会调用工具、读写文件并给出结论
        </div>
        <div>
          <span style={{ color: "var(--yellow)" }}>✱</span> 斜杠命令与内核一致，输入{" "}
          <span style={{ color: "var(--fg)" }}>/</span> 可见补全；命令按钮点击后填入输入框，补全参数再发送
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {quick.map((command) => (
          <button
            key={command.cmd}
            type="button"
            onClick={() => onPick(command.cmd)}
            title={command.desc}
            className="cursor-pointer rounded-md border px-3 py-1.5 text-[12px] transition-colors hover:opacity-80"
            style={{
              borderColor: "var(--border)",
              background: "var(--panel)",
              color: "var(--accent)",
            }}
          >
            {command.cmd}
          </button>
        ))}
      </div>
    </div>
  );
}
