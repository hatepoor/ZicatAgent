import { useMemo, useState } from "react";
import { baseName, timeAgo } from "../core/format";
import type { SessionItem } from "../core/types";

type HistorySidebarProps = {
  sessions: SessionItem[];
  workspaces: string[];
  activeThreadId: string;
  onOpenSession: (session: SessionItem) => void;
  onAddWorkspace: () => void;
  onNewSession: () => void;
  onDeleteSession: (session: SessionItem) => void;
  onDeleteWorkspace: (workspace: string) => void;
};

export default function HistorySidebar({
  sessions,
  workspaces,
  activeThreadId,
  onOpenSession,
  onAddWorkspace,
  onNewSession,
  onDeleteSession,
  onDeleteWorkspace,
}: HistorySidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const groups = useMemo(() => {
    const map = new Map<string, SessionItem[]>();
    for (const workspace of workspaces) map.set(workspace, []);
    for (const session of sessions) {
      const workspace = session.workspace || session.workspace_dir || "其他";
      if (!map.has(workspace)) map.set(workspace, []);
      map.get(workspace)!.push(session);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [sessions, workspaces]);

  const toggle = (workspace: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(workspace)) next.delete(workspace);
      else next.add(workspace);
      return next;
    });
  };

  return (
    <aside
      className="hidden w-[248px] shrink-0 flex-col border-r md:flex"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2.5" style={{ borderColor: "var(--border)" }}>
        <span className="text-[11px] font-bold tracking-widest" style={{ color: "var(--accent)" }}>
          历史
        </span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onNewSession}
          className="cursor-pointer rounded border px-1.5 py-0.5 text-[11px] hover:opacity-80"
          style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
          title="新建会话（/new）"
        >
          ＋会话
        </button>
        <button
          type="button"
          onClick={onAddWorkspace}
          className="cursor-pointer rounded border px-1.5 py-0.5 text-[11px] hover:opacity-80"
          style={{ borderColor: "var(--border)", color: "var(--accent)", background: "var(--panelSoft)" }}
          title="添加工作区"
        >
          ＋工作区
        </button>
      </div>

      <div className="tui-scroll min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {groups.length === 0 && (
          <div className="px-2 py-3 text-[11px]" style={{ color: "var(--faint)" }}>
            暂无会话。发送第一条任务后会自动出现在这里。
          </div>
        )}
        {groups.map(([workspace, items]) => {
          const closed = collapsed.has(workspace);
          return (
            <div key={workspace} className="mb-2">
              <div className="group mb-1 flex items-center gap-1 rounded px-1 py-1 text-[11px]">
                <button
                  type="button"
                  onClick={() => toggle(workspace)}
                  className="flex min-w-0 flex-1 cursor-pointer items-center gap-1 text-left hover:opacity-80"
                  title={workspace}
                  style={{ color: "var(--dim)" }}
                >
                  <span style={{ color: "var(--faint)" }}>{closed ? "▸" : "▾"}</span>
                  <span className="truncate">{baseName(workspace)}</span>
                </button>
                <span className="shrink-0 text-[10px]" style={{ color: "var(--faint)" }}>
                  {items.length}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteWorkspace(workspace);
                  }}
                  className="shrink-0 cursor-pointer whitespace-nowrap rounded px-1 text-[10px] opacity-0 transition-opacity hover:opacity-100 group-hover:opacity-80"
                  style={{ color: "var(--red)" }}
                  title="删除工作区（含会话与全部文件）"
                >
                  删除
                </button>
              </div>
              {!closed && (
                <div className="ml-1">
                  {items.length === 0 && (
                    <div className="px-2 py-1 text-[10px]" style={{ color: "var(--faint)" }}>
                      暂无会话
                    </div>
                  )}
                  {items.map((session) => {
                    const active = session.thread_id === activeThreadId;
                    return (
                      <div
                        key={session.thread_id}
                        className="group mb-0.5 flex items-center gap-1 rounded px-1 py-0.5 transition-colors"
                        style={{ background: active ? "var(--selection)" : "transparent" }}
                      >
                        <button
                          type="button"
                          onClick={() => onOpenSession(session)}
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded px-1 py-1 text-left text-[11px] hover:opacity-80"
                          style={{ color: active ? "var(--fg)" : "var(--dim)" }}
                          title={session.workspace_dir}
                        >
                          <span
                            className="shrink-0"
                            style={{ color: active ? "var(--green)" : "var(--faint)" }}
                          >
                            {active ? "●" : "○"}
                          </span>
                          <span className="min-w-0 flex-1 truncate">{session.title}</span>
                          <span className="shrink-0 text-[10px]" style={{ color: "var(--faint)" }}>
                            {timeAgo(session.updated_at)}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteSession(session);
                          }}
                          className="shrink-0 cursor-pointer whitespace-nowrap rounded px-1 text-[10px] opacity-0 transition-opacity hover:opacity-100 group-hover:opacity-80"
                          style={{ color: "var(--red)" }}
                          title="删除会话（含独占文件）"
                        >
                          删除
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
