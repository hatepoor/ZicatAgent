// 显示层文本净化：只处理内核事件里的展示文本，不含请求/状态逻辑。

/** 去掉 summary 标签本身；内容另行提取为斜体摘要。 */
export const stripTags = (text: string) =>
  text
    .replace(/<summary>[\s\S]*?<\/summary>\s*/gi, "")
    .replace(/<summary[\s\S]*$/i, "")
    .replace(/<\/summary>/gi, "");

export const extractSummary = (text: string) => {
  const matches = [...text.matchAll(/<summary>([\s\S]*?)<\/summary>/gi)];
  return matches.length ? matches[matches.length - 1][1].trim() : "";
};

const INTERNAL_LINE =
  /^\s*(\[TIPS\]|\[SYSTEM TIPS\]|\[DANGER\]|\[WORKING MEMORY\]|###\s*\[WORKING MEMORY\]|\[MASTER\]|\[ROUND END\]|\[usage\])/i;
const TOOL_PAYLOAD_HINT =
  /"(status|stdout|msg|result|body|layer|content|items|hits)"\s*:/;

const isToolJsonLine = (line: string) => {
  const text = line.trim();
  return text.startsWith("{") && TOOL_PAYLOAD_HINT.test(text);
};

const looksLikeToolPayload = (text: string) => {
  const value = text.trim();
  if (value.length < 120) return false;
  if (value.startsWith("{") && TOOL_PAYLOAD_HINT.test(value.slice(0, 500))) return true;
  return /^["']?(name|layer|kind|body)["']?\s*:/i.test(value) &&
    TOOL_PAYLOAD_HINT.test(value.slice(0, 500));
};

// 轮末注入的内部提示（<global_memory> + L1 索引 + RULES）绝不能当助手正文。
// 后端已按消息类型过滤；这里再兜一层，兼容旧会话历史。
const looksLikeInternalPrompt = (text: string) =>
  /<\/?global_memory>/i.test(text) ||
  (/\[Global Memory Insight\]/i.test(text) && /\[RULES\]/i.test(text));

export const cleanAssistant = (text: string) => {
  const stripped = stripTags(text);
  const fenced = stripped.trim().match(/^```(?:json)?\s*([\s\S]*?)```$/i);
  if (looksLikeToolPayload(fenced ? fenced[1] : stripped)) return "";
  if (looksLikeInternalPrompt(stripped)) return "";
  return stripped
    .split("\n")
    .filter((line) => !INTERNAL_LINE.test(line) && !isToolJsonLine(line))
    .join("\n");
};

export const stripInternal = (text: string) => cleanAssistant(text).trim();
