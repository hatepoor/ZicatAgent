import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LOCAL_COMMANDS, SLASH_HINT, UI_CONFIG } from "../core/config";
import type { RpcCommand } from "../core/types";

type Options = {
  commands: RpcCommand[];
  busy: boolean;
  hasPendingQuestion: boolean;
  onSubmit: (text: string) => void;
};

/**
 * 输入框深模块：文本、slash 补全、键盘选择、光标/高度。
 * 对外只暴露 value/suggestions/onKeyDown/submit/pickCandidate/fillCommand。
 */
export function useComposer({ commands, busy, hasPendingQuestion, onSubmit }: Options) {
  const [value, setValue] = useState("");
  const [suggestIdx, setSuggestIdx] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const suggestListRef = useRef<HTMLDivElement>(null);

  const allCommands = useMemo(
    () => [...commands, ...LOCAL_COMMANDS],
    [commands],
  );
  const suggestions = useMemo(() => {
    if (!value.startsWith("/") || value.includes(" ")) return [];
    return allCommands.filter((command) => command.cmd.startsWith(value));
  }, [value, allCommands]);
  const activeSuggestIdx = Math.min(
    suggestIdx,
    Math.max(0, suggestions.length - 1),
  );

  useEffect(() => {
    setSuggestIdx(0);
  }, [value]);

  useEffect(() => {
    const list = suggestListRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLElement>(
      `[data-suggest-idx="${activeSuggestIdx}"]`,
    );
    active?.scrollIntoView({ block: "nearest" });
  }, [activeSuggestIdx, suggestions.length]);

  const autoResize = useCallback((el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(
      el.scrollHeight,
      UI_CONFIG.maxTextareaHeight,
    )}px`;
  }, []);

  const focus = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.style.height = "auto";
    el.style.height = `${Math.min(
      el.scrollHeight,
      UI_CONFIG.maxTextareaHeight,
    )}px`;
    const end = el.value.length;
    el.setSelectionRange(end, end);
  }, []);

  /** 把命令填进输入框（不发送）；光标落在末尾，方便继续补参数 */
  const fillCommand = useCallback(
    (command: string) => {
      const next = command.endsWith(" ") ? command : `${command} `;
      setValue(next);
      setSuggestIdx(0);
      requestAnimationFrame(focus);
    },
    [focus],
  );

  const pickCandidate = useCallback(
    (text: string) => {
      setValue(text);
      requestAnimationFrame(focus);
    },
    [focus],
  );

  const isExactCommand = useCallback(
    (text: string) =>
      text === "/mode" || allCommands.some((command) => command.cmd === text),
    [allCommands],
  );

  const submit = useCallback(() => {
    const text = value.trim();
    if (!text) return;
    if (busy && !hasPendingQuestion) return;
    setValue("");
    onSubmit(text);
  }, [busy, hasPendingQuestion, onSubmit, value]);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        // 半截命令先补全，完整命令才直接发送。
        if (suggestions.length > 0 && !isExactCommand(value.trim())) {
          fillCommand(suggestions[activeSuggestIdx].cmd);
          return;
        }
        submit();
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        if (suggestions.length > 0) {
          fillCommand(suggestions[activeSuggestIdx].cmd);
        }
        return;
      }
      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        if (suggestions.length === 0) return;
        event.preventDefault();
        const delta = event.key === "ArrowUp" ? -1 : 1;
        setSuggestIdx((prev) => {
          const current = Math.min(prev, suggestions.length - 1);
          return (current + delta + suggestions.length) % suggestions.length;
        });
      }
    },
    [
      activeSuggestIdx,
      fillCommand,
      isExactCommand,
      submit,
      suggestions,
      value,
    ],
  );

  return {
    value,
    setValue,
    inputRef,
    suggestListRef,
    suggestions,
    activeSuggestIdx,
    setSuggestIdx,
    fillCommand,
    pickCandidate,
    submit,
    onKeyDown,
    autoResize,
    focus,
    hint: SLASH_HINT,
  };
}

export type Composer = ReturnType<typeof useComposer>;
