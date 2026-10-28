import { UI_CONFIG } from "../../core/config";
import { compactNumber } from "../../core/format";
import type { ThemeState } from "../../core/types";
import type { AgentSession } from "../../hooks/useAgentSession";
import { useClock } from "../../hooks/useClock";
import { StatusCell } from "../common/StatusCell";

 type Props = {
  session: AgentSession;
  theme: ThemeState;
};

export function StatusBar({ session, theme }: Props) {
  const now = useClock();
  const active =
    session.models[session.activeModel] ??
    session.models.find((item) => item.model === session.model);
  const effort = active?.reasoning_effort || "默认";
  const provider = active?.provider || "openai";
  const effortColor =
    effort === "默认"
      ? "var(--faint)"
      : effort === "off"
        ? "var(--dim)"
        : effort === "low"
          ? "var(--cyan)"
          : effort === "medium"
            ? "var(--green)"
            : effort === "high"
              ? "var(--yellow)"
              : "var(--red)";
  const configured = Number(session.models[session.activeModel]?.context_window);
  const contextLimit =
    configured > 0 ? configured : UI_CONFIG.fallbackContextWindow;
  const ctxPct = Math.min(
    99,
    Math.round((session.contextTokens / contextLimit) * 100),
  );
  const state = session.busy
    ? "WORKING"
    : session.connected
      ? "READY"
      : "OFFLINE";

  return (
    <div
      className="flex shrink-0 items-center gap-0 border-t text-[11px] select-none"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <StatusCell bg="var(--accent)" fg="var(--bg)" bold>
        {state}
      </StatusCell>
      <StatusCell>
        <span style={{ color: "var(--cyan)" }}>⬢</span> {session.model}
      </StatusCell>
      <StatusCell>
        <span title={`接口: ${provider}；用 /effort 调整`}>
          <span style={{ color: "var(--magenta)" }}>✦</span>{" "}
          <span style={{ color: "var(--faint)" }}>思考</span>{" "}
          <span style={{ color: effortColor }}>{effort}</span>
        </span>
      </StatusCell>
      <StatusCell>
        <span style={{ color: "var(--yellow)" }}>◧</span> {theme.theme.label}
      </StatusCell>
      <div className="flex-1" />
      <StatusCell>≈ {session.tokens.toLocaleString()} tok</StatusCell>
      <StatusCell>
        ctx {compactNumber(session.contextTokens)}/{compactNumber(contextLimit)} ·{" "}
        {ctxPct}%
      </StatusCell>
      <StatusCell>{now.toLocaleTimeString("zh-CN", { hour12: false })}</StatusCell>
    </div>
  );
}
