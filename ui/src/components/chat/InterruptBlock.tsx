import type { Entry } from "../../core/types";

export function InterruptBlock({
  entry,
  onPick,
}: {
  entry: Extract<Entry, { kind: "interrupt" }>;
  onPick: (text: string) => void;
}) {
  return (
    <div
      className={`my-2 rounded-md border px-3 py-2 text-[12px] leading-5 ${
        entry.answered ? "opacity-50" : ""
      }`}
      style={{
        borderColor: entry.answered ? "var(--border)" : "var(--yellow)",
        background: "var(--panel)",
      }}
    >
      <div style={{ color: entry.answered ? "var(--faint)" : "var(--yellow)" }}>
        <span className="font-bold">{entry.answered ? "✓" : "？"}</span>{" "}
        {entry.answered ? "已回答，等待智能体继续…" : "智能体需要你的回答："}
      </div>
      <div className="mt-1 whitespace-pre-wrap" style={{ color: "var(--fg)" }}>
        {entry.question}
      </div>
      {!entry.answered && entry.candidates.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {entry.candidates.map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => onPick(candidate)}
              className="cursor-pointer rounded border px-2 py-0.5 text-[12px] transition-colors hover:opacity-80"
              style={{
                borderColor: "var(--border)",
                color: "var(--accent)",
                background: "var(--panelSoft)",
              }}
            >
              {candidate}
            </button>
          ))}
        </div>
      )}
      {!entry.answered && (
        <div className="mt-2" style={{ color: "var(--faint)" }}>
          在下方输入回答后回车；按 Esc 放弃并中断任务
        </div>
      )}
    </div>
  );
}
