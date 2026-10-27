import { useEffect, useRef } from "react";
import type { AgentSession } from "../../hooks/useAgentSession";
import { EntryView } from "../chat/EntryView";
import { Welcome } from "../chat/Welcome";

type Props = {
  session: AgentSession;
  onPickCandidate: (text: string) => void;
  onFillCommand: (command: string) => void;
};

export function ChatView({ session, onPickCandidate, onFillCommand }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [session.entries]);

  return (
    <div
      ref={scrollRef}
      className="tui-scroll min-w-0 flex-1 overflow-y-auto px-6 py-4"
    >
      {session.entries.length === 0 ? (
        <Welcome
          model={session.model}
          cwd={session.workspace || session.cwd}
          commands={session.kernelCommands}
          onPick={onFillCommand}
        />
      ) : (
        session.entries.map((entry) => (
          <EntryView
            key={entry.id}
            entry={entry}
            onPickCandidate={onPickCandidate}
          />
        ))
      )}
      {session.busy && !session.hasPendingQuestion && (
        <div className="my-2 flex items-center gap-2" style={{ color: "var(--dim)" }}>
          <span className="tui-shimmer" style={{ color: "var(--accent)" }}>
            智能体工作中…
          </span>
          <span className="text-[11px]" style={{ color: "var(--faint)" }}>
            (可点顶栏「中断」或按 Esc)
          </span>
        </div>
      )}
    </div>
  );
}
