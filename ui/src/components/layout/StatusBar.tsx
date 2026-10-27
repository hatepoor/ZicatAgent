import { UI_CONFIG } from "../../core/config";
import { compactNumber } from "../../core/format";
import type { ThemeState } from "../../core/types";
import type { AgentSession } from "../../hooks/useAgentSession";
import { StatusCell } from "../common/StatusCell";

 type Props = {
  session: AgentSession;
  theme: ThemeState;
  now: Date;
};

export function StatusBar({ session, theme, now }: Props) {
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
