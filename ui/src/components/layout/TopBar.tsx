import { ABOUT_TEXT, UI_CONFIG } from "../../core/config";
import type { ThemeState } from "../../core/types";
import type { AgentSession } from "../../hooks/useAgentSession";

type Props = {
  session: AgentSession;
  theme: ThemeState;
  panelOpen: boolean;
  onTogglePanel: () => void;
};

export function TopBar({ session, theme, panelOpen, onTogglePanel }: Props) {
  return (
    <div
      className="flex shrink-0 items-center gap-3 border-b px-4 py-2 select-none"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <span className="font-bold" style={{ color: "var(--accent)" }}>
        ◆ {UI_CONFIG.appTitle}
      </span>
      <span
        className="text-[11px]"
        style={{ color: session.connected ? "var(--green)" : "var(--red)" }}
      >
        ● {session.connected ? "已连接" : "连接断开"}
      </span>
      <span
        className="truncate text-[11px]"
        title={`工作空间根目录: ${session.workspaceRoot}`}
        style={{ color: "var(--faint)" }}
      >
        ws: {session.workspace || session.cwd}
      </span>
      <div className="flex-1" />
      <div className="relative">
        <button
          type="button"
          onClick={() => theme.setMenu(!theme.menu)}
          className="cursor-pointer rounded border px-2 py-1 text-[11px] transition-colors hover:opacity-80"
          style={{
            borderColor: "var(--border)",
            color: "var(--fg)",
            background: "var(--panelSoft)",
          }}
        >
          ◧ {theme.theme.label} ▾
        </button>
        {theme.menu && (
          <div
            className="absolute right-0 top-full z-10 mt-1 w-44 overflow-hidden rounded-md border shadow-xl"
            style={{ borderColor: "var(--border)", background: "var(--panelSoft)" }}
          >
            {theme.options.map((option, index) => (
              <div
                key={option.id}
                className="cursor-pointer px-3 py-1.5 text-[12px] hover:opacity-80"
                style={{
                  background:
                    index === theme.themeIdx ? "var(--selection)" : "transparent",
                  color: "var(--fg)",
                }}
                onClick={() => {
                  theme.setThemeIdx(index);
                  theme.setMenu(false);
                }}
              >
                <span style={{ color: option.accent }}>◧</span> {option.label}
              </div>
            ))}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onTogglePanel}
        className="cursor-pointer rounded border px-2 py-1 text-[11px] transition-colors hover:opacity-80"
        style={{
          borderColor: "var(--border)",
          color: "var(--fg)",
          background: "var(--panelSoft)",
        }}
      >
        {panelOpen ? "收起面板" : "展开面板"}
      </button>
      <button
        type="button"
        onClick={session.doAbort}
        disabled={!session.busy}
        className={`rounded border px-2 py-1 text-[11px] transition-colors ${
          session.busy
            ? "cursor-pointer hover:opacity-80"
            : "cursor-not-allowed opacity-40"
        }`}
        style={{
          borderColor: session.busy ? "var(--red)" : "var(--border)",
          color: session.busy ? "var(--red)" : "var(--faint)",
          background: "var(--panelSoft)",
        }}
      >
        ■ 中断
      </button>
      <button
        type="button"
        onClick={() => session.pushSystem(ABOUT_TEXT)}
        className="cursor-pointer rounded border px-2 py-1 text-[11px] transition-colors hover:opacity-80"
        style={{
          borderColor: "var(--border)",
          color: "var(--fg)",
          background: "var(--panelSoft)",
        }}
      >
        关于
      </button>
    </div>
  );
}
