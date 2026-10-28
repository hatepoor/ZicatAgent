import type { Entry, HistoryItem } from "./types";
import { cleanAssistant, extractSummary } from "./text";

/** checkpoint 历史 → 前端 Entry；文本继续走同样的净化与 summary 提取。 */
export function historyToEntries(
  items: HistoryItem[],
  nextId: () => number,
): Entry[] {
  const out: Entry[] = [];
  for (const item of items) {
    if (item.kind === "user") {
      const text = (item.text || "").trim();
      if (text) out.push({ id: nextId(), kind: "user", text });
      continue;
    }
    if (item.kind === "thinking") {
      const text = item.text || "";
      if (text.trim()) {
        out.push({ id: nextId(), kind: "thinking", text, done: true });
      }
      continue;
    }
    if (item.kind === "assistant") {
      const raw = item.text || "";
      const text = cleanAssistant(raw).trim();
      const summary = extractSummary(raw);
      if (text || summary) {
        out.push({
          id: nextId(),
          kind: "assistant",
          text,
          shown: text.length,
          done: true,
          summary,
          raw,
        });
      }
      continue;
    }
    const raw = item.text || "";
    out.push({
      id: nextId(),
      kind: "tool",
      name: item.name || "",
      args: item.args || "",
      lines: raw ? raw.split("\n") : [],
      payload: item.payload ?? null,
      status: item.status === "error" ? "error" : "done",
    });
  }
  return out;
}
