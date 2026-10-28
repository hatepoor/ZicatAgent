import { memo } from "react";
import type { Entry } from "../../core/types";
import { AssistantBlock } from "./AssistantBlock";
import { InterruptBlock } from "./InterruptBlock";
import { ThinkingBlock } from "./ThinkingBlock";
import { ToolBlock } from "./ToolBlock";

function EntryViewInner({
  entry,
  onPickCandidate,
}: {
  entry: Entry;
  onPickCandidate: (text: string) => void;
}) {
  switch (entry.kind) {
    case "user":
      return (
        <div className="mt-4 mb-1 flex gap-2">
          <span className="font-bold" style={{ color: "var(--green)" }}>
            ❯
          </span>
          <span
            className="font-medium break-all whitespace-pre-wrap"
            style={{ color: "var(--fg)" }}
          >
            {entry.text}
          </span>
        </div>
      );
    case "assistant":
      return <AssistantBlock entry={entry} />;
    case "thinking":
      return <ThinkingBlock entry={entry} />;
    case "tool":
      return <ToolBlock entry={entry} />;
    case "system":
      return (
        <div
          className="my-2 rounded-md border px-3 py-2 text-[12px] leading-5 whitespace-pre-wrap"
          style={{
            borderColor: "var(--border)",
            background: "var(--panel)",
            color: "var(--dim)",
          }}
        >
          {entry.text}
        </div>
      );
    case "interrupt":
      return <InterruptBlock entry={entry} onPick={onPickCandidate} />;
    case "error":
      return (
        <div className="my-1 flex gap-2" style={{ color: "var(--red)" }}>
          <span>✗</span>
          <span className="whitespace-pre-wrap">{entry.text}</span>
        </div>
      );
  }
}

export const EntryView = memo(EntryViewInner);
