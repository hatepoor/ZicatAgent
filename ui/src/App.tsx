import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import ConfirmDialog from "./components/Confirm";
import HistorySidebar from "./components/History";
import { Composer } from "./components/composer/Composer";
import { ChatView } from "./components/layout/ChatView";
import { RightPanel } from "./components/layout/RightPanel";
import { StatusBar } from "./components/layout/StatusBar";
import { TopBar } from "./components/layout/TopBar";
import { ModelSettings, WorkspaceSettings } from "./components/Settings";
import { useAgentSession } from "./hooks/useAgentSession";
import { useClock } from "./hooks/useClock";
import { useComposer } from "./hooks/useComposer";
import { useTheme } from "./hooks/useTheme";
import type { Theme } from "./themes";

function themeVars(theme: Theme): CSSProperties {
  return {
    "--bg": theme.bg,
    "--bgGlow": theme.bgGlow,
    "--panel": theme.panel,
    "--panelSoft": theme.panelSoft,
    "--border": theme.border,
    "--fg": theme.fg,
    "--dim": theme.dim,
    "--faint": theme.faint,
    "--accent": theme.accent,
    "--accent2": theme.accent2,
    "--green": theme.green,
    "--yellow": theme.yellow,
    "--red": theme.red,
    "--blue": theme.blue,
    "--magenta": theme.magenta,
    "--cyan": theme.cyan,
    "--selection": theme.selection,
  } as CSSProperties;
}

/**
 * 组合根：只负责把深模块（会话/输入/主题/时钟）接到原子组件上。
 * 业务状态与 RPC 协议在 hooks 内，展示结构在 components 内。
 */
export default function App() {
  const [panelOpen, setPanelOpen] = useState(true);
  const now = useClock();
  const theme = useTheme();
  const session = useAgentSession({ onTheme: theme.next });
  const composer = useComposer({
    commands: session.kernelCommands,
    busy: session.busy,
    hasPendingQuestion: session.hasPendingQuestion,
    onSubmit: session.submitUserText,
  });

  // 全局快捷键：Esc 先关弹层/菜单，否则中断；Ctrl+L 清屏。
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (session.pendingDelete) {
          session.closeConfirm();
          return;
        }
        if (session.modal) {
          session.closeModal();
          return;
        }
        if (theme.menu) {
          theme.setMenu(false);
          return;
        }
        session.doAbort();
        return;
      }
      if (
        event.ctrlKey &&
        event.key.toLowerCase() === "l" &&
        !session.modal &&
        !session.pendingDelete
      ) {
        event.preventDefault();
        session.clearChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    session.closeConfirm,
    session.closeModal,
    session.doAbort,
    session.clearChat,
    session.modal,
    session.pendingDelete,
    theme.menu,
    theme.setMenu,
  ]);

  const vars = themeVars(theme.theme);

  return (
    <div
      style={{
        ...vars,
        background: "radial-gradient(ellipse 80% 60% at 50% -10%, var(--bgGlow), var(--bg))",
      }}
      className="flex h-screen w-screen flex-col overflow-hidden text-[13px]"
    >
      <TopBar
        session={session}
        theme={theme}
        panelOpen={panelOpen}
        onTogglePanel={() => setPanelOpen((prev) => !prev)}
      />

      <div className="flex min-h-0 flex-1">
        <HistorySidebar
          sessions={session.sessions}
          workspaces={session.workspaces}
          activeThreadId={session.activeThreadId}
          onOpenSession={session.openSession}
          onAddWorkspace={session.openWorkspace}
          onNewSession={session.newSession}
          onDeleteSession={session.requestDeleteSession}
          onDeleteWorkspace={session.requestDeleteWorkspace}
        />
        <ChatView
          session={session}
          onPickCandidate={composer.pickCandidate}
          onFillCommand={composer.fillCommand}
        />
        <RightPanel
          session={session}
          theme={theme}
          now={now}
          panelOpen={panelOpen}
          onFillCommand={composer.fillCommand}
        />
      </div>

      <Composer
        composer={composer}
        busy={session.busy}
        hasPendingQuestion={session.hasPendingQuestion}
        modalOpen={session.modal !== null}
      />
      <StatusBar session={session} theme={theme} now={now} />

      {session.modal === "model" && (
        <ModelSettings
          models={session.models}
          active={session.activeModel}
          onClose={session.closeModal}
          onSave={session.saveModelConfig}
          onSwitch={session.switchModel}
          onReveal={session.revealModels}
        />
      )}
      {session.modal === "workspace" && (
        <WorkspaceSettings
          current={session.workspace}
          root={session.workspaceRoot}
          defaultPath={session.defaultWorkspace}
          onClose={session.closeModal}
          onSave={session.saveWorkspace}
        />
      )}
      {session.pendingDelete && (
        <ConfirmDialog
          title={
            session.pendingDelete.kind === "session" ? "删除会话" : "删除工作区"
          }
          message={session.confirmMessage}
          confirmLabel={
            session.pendingDelete.kind === "session" ? "删除会话" : "删除工作区"
          }
          onCancel={session.closeConfirm}
          onConfirm={session.confirmDelete}
        />
      )}
    </div>
  );
}
