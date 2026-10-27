import { useDeferredValue } from "react";
import type { Entry } from "../../core/types";
import Rich from "../Rich";

export function AssistantBlock({
  entry,
}: {
  entry: Extract<Entry, { kind: "assistant" }>;
}) {
  const text = useDeferredValue(entry.text);
  if (!text && !entry.summary) return null;
  return (
    <div className="my-1 flex gap-2">
      <span className="shrink-0 font-bold" style={{ color: "var(--accent2)" }}>
        ◆
      </span>
      <div className="min-w-0 flex-1" style={{ color: "var(--fg)" }}>
        {entry.summary && (
          <div
            className="mb-1 text-[12px] leading-5 italic select-none"
            style={{ color: "var(--dim)", opacity: 0.62 }}
          >
            • {entry.summary}
          </div>
        )}
        <Rich text={text} />
        {!entry.done && (
          <span
            className="ml-0.5 inline-block h-[14px] w-[7px] translate-y-[2px] animate-pulse"
            style={{ background: "var(--accent)" }}
          />
        )}
      </div>
    </div>
  );
}
