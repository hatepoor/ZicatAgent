import { useState } from "react";
import type { Entry } from "../../core/types";
import Rich from "../Rich";
import { Spinner } from "./Spinner";

type ToolPayload = {
  status?: string;
  stdout?: string;
  msg?: string;
  exit_code?: number;
  result?: unknown;
  [key: string]: unknown;
};

const CONTENT_KEYS = new Set([
  "stdout",
  "msg",
  "result",
  "body",
  "content",
  "text",
  "markdown",
  "js_return",
]);
const MARKDOWN_KEYS = new Set(["body", "content", "text", "markdown"]);

function parseToolPayload(lines: string[]): ToolPayload | null {
  const raw = lines.join("\n").trim();
  if (!raw) return null;
  try {
    const data = JSON.parse(raw);
    return data && typeof data === "object" && !Array.isArray(data)
      ? (data as ToolPayload)
      : null;
  } catch {
    return null;
  }
}

function ToolResult({ payload, raw }: { payload: ToolPayload | null; raw: string }) {
  if (!payload) {
    return (
      <pre
        className="whitespace-pre-wrap break-words text-[11.5px] leading-5"
        style={{ color: "var(--fg)" }}
      >
        {raw}
      </pre>
    );
  }

  const meta = Object.entries(payload).filter(
    ([key, value]) =>
      !CONTENT_KEYS.has(key) &&
      key !== "status" &&
      key !== "exit_code" &&
      value !== null &&
      ["string", "number", "boolean"].includes(typeof value),
  );
  const markdown = [...MARKDOWN_KEYS]
    .filter((key) => typeof payload[key] === "string" && String(payload[key]).trim())
    .map((key) => [key, String(payload[key])] as const);

  return (
    <div className="text-[11.5px] leading-5">
      {meta.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px]">
          {meta.map(([key, value]) => (
            <span key={key}>
              <span style={{ color: "var(--faint)" }}>{key}</span>{" "}
              <span style={{ color: "var(--fg)" }}>{String(value)}</span>
            </span>
          ))}
        </div>
      )}
      {payload.stdout ? (
        <div
          className="max-h-[52vh] overflow-auto rounded border px-2 py-1.5"
          style={{ borderColor: "var(--border)", background: "var(--panelSoft)" }}
        >
          <pre className="whitespace-pre-wrap break-words" style={{ color: "var(--fg)" }}>
            {String(payload.stdout).replace(/\s+$/, "")}
          </pre>
        </div>
      ) : null}
      {payload.msg ? (
        <pre className="whitespace-pre-wrap break-words" style={{ color: "var(--red)" }}>
          {String(payload.msg)}
        </pre>
      ) : null}
      {markdown.map(([key, text]) => (
        <div key={key} className="mt-1">
          <div className="mb-0.5 text-[10px]" style={{ color: "var(--faint)" }}>
            {key}
          </div>
          <div
            className="max-h-[52vh] overflow-auto rounded border px-2 py-1.5"
            style={{ borderColor: "var(--border)", background: "var(--panelSoft)" }}
          >
            <Rich text={text} />
          </div>
        </div>
      ))}
      {typeof payload.js_return === "string" && payload.js_return.trim() ? (
        <pre
          className="max-h-[52vh] overflow-auto whitespace-pre-wrap break-words"
          style={{ color: "var(--fg)" }}
        >
          {String(payload.js_return)}
        </pre>
      ) : null}
      {payload.result !== undefined ? (
        <pre
          className="max-h-[52vh] overflow-auto whitespace-pre-wrap break-words"
          style={{ color: "var(--fg)" }}
        >
          {typeof payload.result === "string"
            ? payload.result
            : JSON.stringify(payload.result, null, 2)}
        </pre>
      ) : null}
      {Object.entries(payload).some(
        ([key]) =>
          !CONTENT_KEYS.has(key) &&
          key !== "status" &&
          key !== "exit_code" &&
          meta.every(([metaKey]) => metaKey !== key),
      ) ? (
        <pre
          className="max-h-[52vh] overflow-auto whitespace-pre-wrap break-words"
          style={{ color: "var(--fg)" }}
        >
          {JSON.stringify(
            Object.fromEntries(
              Object.entries(payload).filter(
                ([key]) =>
                  !CONTENT_KEYS.has(key) &&
                  key !== "status" &&
                  key !== "exit_code" &&
                  meta.every(([metaKey]) => metaKey !== key),
              ),
            ),
            null,
            2,
          )}
        </pre>
      ) : null}
      {!payload.stdout &&
      !payload.msg &&
      markdown.length === 0 &&
      payload.result === undefined &&
      !payload.js_return &&
      meta.length === 0 ? (
        <pre className="whitespace-pre-wrap break-words" style={{ color: "var(--fg)" }}>
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export function ToolBlock({
  entry,
}: {
  entry: Extract<Entry, { kind: "tool" }>;
}) {
  const running = entry.status === "running";
  const failed = entry.status === "error";
  const [open, setOpen] = useState(false);
  const payload = (entry.payload ?? parseToolPayload(entry.lines)) as ToolPayload | null;
  const statusText = running
    ? "运行中"
    : failed || payload?.status === "error"
      ? "失败"
      : "成功";
  const statusColor = running
    ? "var(--yellow)"
    : failed || payload?.status === "error"
      ? "var(--red)"
      : "var(--green)";
  const hasBody = entry.lines.length > 0;

  return (
    <div className="my-1.5">
      <div
        className={`flex items-center gap-2 ${hasBody ? "cursor-pointer" : ""}`}
        onClick={() => hasBody && setOpen((prev) => !prev)}
      >
        <span style={{ color: "var(--faint)" }}>╭─</span>
        {running ? (
          <Spinner color="var(--yellow)" />
        ) : failed ? (
          <span style={{ color: "var(--red)" }}>✗</span>
        ) : (
          <span style={{ color: "var(--green)" }}>✓</span>
        )}
        <span className="font-bold" style={{ color: "var(--magenta)" }}>
          {entry.name}
        </span>
        <span className="truncate" style={{ color: "var(--dim)" }}>
          {entry.args}
        </span>
        {!running && (
          <span className="shrink-0 text-[11px]" style={{ color: statusColor }}>
            {statusText}
          </span>
        )}
        {typeof payload?.exit_code === "number" && (
          <span className="shrink-0 text-[10px]" style={{ color: "var(--faint)" }}>
            exit {payload.exit_code}
          </span>
        )}
        {!running && entry.duration !== undefined && (
          <span className="shrink-0 text-[11px]" style={{ color: "var(--faint)" }}>
            {(entry.duration / 1000).toFixed(1)}s
          </span>
        )}
        {hasBody && (
          <span className="ml-auto shrink-0 text-[11px]" style={{ color: "var(--faint)" }}>
            {open ? "▾ 收起" : "▸ 详情"}
          </span>
        )}
      </div>
      {open && hasBody && (
        <div className="ml-[3px] border-l pl-4" style={{ borderColor: "var(--faint)" }}>
          <ToolResult payload={payload} raw={entry.lines.join("\n")} />
        </div>
      )}
      <div style={{ color: "var(--faint)" }}>╰─</div>
    </div>
  );
}
