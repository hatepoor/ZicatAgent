import { useMemo } from "react";
import { KEYBOARD_SHORTCUTS, UI_CONFIG } from "../../core/config";
import { formatDuration } from "../../core/format";
import type { ThemeState } from "../../core/types";
import type { AgentSession } from "../../hooks/useAgentSession";
import { useClock } from "../../hooks/useClock";
import { PanelRow, PanelSection } from "../common/Panel";

type Props = {
  session: AgentSession;
  theme: ThemeState;
  panelOpen: boolean;
  onFillCommand: (command: string) => void;
};

export function RightPanel({
  session,
  theme,
  panelOpen,
  onFillCommand,
}: Props) {
  const now = useClock();
  const msgCount = useMemo(
    () => session.entries.filter((entry) => entry.kind === "user").length,
    [session.entries],
  );
  const toolCount = useMemo(
    () => session.entries.filter((entry) => entry.kind === "tool").length,
    [session.entries],
  );
  const recentTools = useMemo(
    () => session.entries
      .filter((entry) => entry.kind === "tool")
      .slice(-UI_CONFIG.maxRecentTools),
    [session.entries],
  );
  const uptime = Math.max(0, Math.floor((now.getTime() - session.startedAt) / 1000));
  const configured = Number(session.models[session.activeModel]?.context_window);
  const contextLimit =
    configured > 0 ? configured : UI_CONFIG.fallbackContextWindow;
  const ctxPct = Math.min(
    99,
    Math.round((session.contextTokens / contextLimit) * 100),
  );

  return (
    <div
      className={`hidden shrink-0 overflow-hidden border-l transition-all duration-300 ease-in-out md:block ${
        panelOpen
          ? "w-[280px] opacity-100"
          : "w-0 opacity-0 pointer-events-none"
      }`}
      style={{
        borderColor: panelOpen ? "var(--border)" : "transparent",
        background: "var(--panel)",
      }}
    >
      <div className="tui-scroll h-full w-[280px] overflow-y-auto px-4 py-4">
        <PanelSection title="会话">
          <div
            className="mb-1 flex cursor-pointer justify-between text-[12px] hover:opacity-80"
            title="打开模型配置"
            onClick={session.openModels}
          >
            <span style={{ color: "var(--dim)" }}>模型</span>
            <span style={{ color: "var(--cyan)" }}>{session.model} ›</span>
          </div>
          <div
            className="mb-1 flex cursor-pointer justify-between gap-2 text-[12px] hover:opacity-80"
            title={session.workspace}
            onClick={session.openWorkspace}
          >
            <span className="shrink-0" style={{ color: "var(--dim)" }}>
              工作空间
            </span>
            <span className="truncate" style={{ color: "var(--cyan)" }}>
              {(session.workspace || session.cwd)
                .split(/[\\/]/)
                .filter(Boolean)
                .pop() || "—"}{" "}
              ›
            </span>
          </div>
          <PanelRow k="主题" v={theme.theme.label} />
          <PanelRow k="消息" v={String(msgCount)} />
          <PanelRow k="工具调用" v={String(toolCount)} />
          <PanelRow
            k="tokens"
            v={`≈ ${session.tokens.toLocaleString()}`}
            vc="var(--yellow)"
          />
          <PanelRow k="运行时长" v={formatDuration(uptime)} />
        </PanelSection>

        <PanelSection title="上下文">
          <div
            className="mb-1 flex justify-between text-[11px]"
            style={{ color: "var(--dim)" }}
          >
            <span>当前上下文（近似）</span>
            <span>{ctxPct}%</span>
          </div>
          <div
            className="h-[6px] overflow-hidden rounded"
            style={{ background: "var(--selection)" }}
          >
            <div
              className="h-full rounded transition-all duration-500"
              style={{
                width: `${ctxPct}%`,
                background: "linear-gradient(90deg, var(--accent), var(--accent2))",
              }}
            />
          </div>
          <div className="mt-1.5 text-[10px]" style={{ color: "var(--faint)" }}>
            {session.contextTokens.toLocaleString()} /{" "}
            {contextLimit.toLocaleString()} tok
          </div>
          {session.contextCharCap > 0 && (
            <div className="text-[10px]" style={{ color: "var(--faint)" }}>
              引擎视图预算 {session.contextCharCap.toLocaleString()} 字符
            </div>
          )}
        </PanelSection>

        <PanelSection title="最近工具">
          {recentTools.length === 0 && (
            <div className="text-[11px]" style={{ color: "var(--faint)" }}>
              暂无调用记录
            </div>
          )}
          {recentTools.map(
            (tool) =>
              tool.kind === "tool" && (
                <div
                  key={tool.id}
                  className="mb-1 flex items-center gap-1.5 text-[11px]"
                >
                  <span
                    style={{
                      color:
                        tool.status === "done"
                          ? "var(--green)"
                          : tool.status === "error"
                            ? "var(--red)"
                            : "var(--yellow)",
                    }}
                  >
                    {tool.status === "done" ? "✓" : tool.status === "error" ? "✗" : "●"}
                  </span>
                  <span style={{ color: "var(--magenta)" }}>{tool.name}</span>
                  <span className="truncate" style={{ color: "var(--faint)" }}>
                    {tool.args}
                  </span>
                </div>
              ),
          )}
        </PanelSection>

        <PanelSection title="内核命令">
          {session.kernelCommands.length === 0 && (
            <div className="text-[11px]" style={{ color: "var(--faint)" }}>
              等待后端就绪…
            </div>
          )}
          {session.kernelCommands.map((command) => (
            <div
              key={command.cmd}
              className="mb-0.5 cursor-pointer rounded px-1.5 py-0.5 text-[11px] transition-colors hover:bg-[var(--selection)]"
              title={`${command.desc}（点击填入输入框）`}
              onClick={() => onFillCommand(command.cmd)}
            >
              <span style={{ color: "var(--accent)" }}>{command.cmd}</span>
              <span className="ml-1.5" style={{ color: "var(--faint)" }}>
                {command.desc}
              </span>
            </div>
          ))}
        </PanelSection>

        <PanelSection title="快捷键">
          {KEYBOARD_SHORTCUTS.map(([key, value]) => (
            <div key={key} className="mb-1 flex justify-between text-[11px]">
              <span
                className="rounded border px-1.5"
                style={{ borderColor: "var(--border)", color: "var(--accent)" }}
              >
                {key}
              </span>
              <span style={{ color: "var(--dim)" }}>{value}</span>
            </div>
          ))}
        </PanelSection>

      </div>
    </div>
  );
}
