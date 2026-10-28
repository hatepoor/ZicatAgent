import { useState } from "react";
import type { Entry } from "../../core/types";
import Rich from "../Rich";

/** thinking 折叠块：默认收起；流式时标题呼吸，结束后静态。 */
export function ThinkingBlock({
  entry,
}: {
  entry: Extract<Entry, { kind: "thinking" }>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="my-1 flex gap-2">
      <span className="shrink-0" style={{ color: "var(--magenta)" }}>
        ✦
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          className="flex cursor-pointer items-center gap-2 border-none bg-transparent p-0 text-[12px]"
          style={{ color: "var(--dim)" }}
        >
          <span className={entry.done ? "" : "tui-shimmer"}>thinking</span>
          {!entry.done && <span className="tui-shimmer" style={{ color: "var(--faint)" }}>…</span>}
          <span style={{ color: "var(--faint)" }}>{open ? "▾ 收起" : "▸ 展开"}</span>
        </button>
        {open && (
          <div
            className="mt-1 border-l pl-3 text-[12px]"
            style={{ borderColor: "var(--faint)", color: "var(--dim)" }}
          >
            <Rich text={entry.text} />
          </div>
        )}
      </div>
    </div>
  );
}
