import { useEffect } from "react";
import { COMPOSER_COPY, UI_CONFIG } from "../../core/config";
import type { Composer as ComposerState } from "../../hooks/useComposer";

type Props = {
  composer: ComposerState;
  busy: boolean;
  hasPendingQuestion: boolean;
  modalOpen: boolean;
};

export function Composer({
  composer,
  busy,
  hasPendingQuestion,
  modalOpen,
}: Props) {
  useEffect(() => {
    if (!modalOpen) requestAnimationFrame(composer.focus);
    // focus 只在弹层关闭/首挂载时触发，不依赖每次输入变化
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modalOpen]);

  return (
    <div
      className="relative shrink-0 border-t px-6 py-3"
      style={{ borderColor: "var(--border)" }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) composer.focus();
      }}
    >
      {composer.suggestions.length > 0 && (
        <div
          className="absolute bottom-full left-6 mb-1 overflow-hidden rounded-md border shadow-xl"
          style={{
            width: UI_CONFIG.suggestWidth,
            maxWidth: "calc(100vw - 3rem)",
            borderColor: "var(--border)",
            background: "var(--panelSoft)",
          }}
        >
          <div
            ref={composer.suggestListRef}
            className="tui-scroll overflow-y-auto"
            style={{ maxHeight: UI_CONFIG.suggestMaxHeight }}
          >
            {composer.suggestions.map((suggestion, index) => (
              <div
                key={suggestion.cmd}
                data-suggest-idx={index}
                className="flex cursor-pointer justify-between px-3 py-1.5 text-[12px]"
                style={{
                  background:
                    index === composer.activeSuggestIdx
                      ? "var(--selection)"
                      : "transparent",
                }}
                onMouseEnter={() => composer.setSuggestIdx(index)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  composer.fillCommand(suggestion.cmd);
                }}
              >
                <span className="shrink-0" style={{ color: "var(--accent)" }}>
                  {suggestion.cmd}
                </span>
                <span className="truncate pl-2" style={{ color: "var(--dim)" }}>
                  {suggestion.desc}
                </span>
              </div>
            ))}
          </div>
          <div
            className="border-t px-3 py-1 text-[10px]"
            style={{ borderColor: "var(--border)", color: "var(--faint)" }}
          >
            {composer.hint} · 共 {composer.suggestions.length} 条
          </div>
        </div>
      )}

      <div className="flex items-start gap-2">
        <span
          className="shrink-0 leading-5 font-bold select-none"
          style={{ color: busy ? "var(--yellow)" : "var(--green)" }}
        >
          {busy ? "◌" : "❯"}
        </span>
        <textarea
          ref={composer.inputRef}
          value={composer.value}
          rows={1}
          onChange={(event) => {
            composer.setValue(event.target.value);
            composer.autoResize(event.target);
          }}
          onKeyDown={composer.onKeyDown}
          autoFocus
          spellCheck={false}
          autoComplete="off"
          placeholder={
            hasPendingQuestion
              ? COMPOSER_COPY.pending
              : busy
                ? COMPOSER_COPY.busy
                : COMPOSER_COPY.idle
          }
          className="tui-scroll block w-full resize-none bg-transparent p-0 leading-5 outline-none"
          style={{
            color: "var(--fg)",
            caretColor: "var(--accent)",
            maxHeight: UI_CONFIG.maxTextareaHeight,
          }}
        />
        <button
          type="button"
          onClick={composer.submit}
          disabled={busy || !composer.value.trim()}
          className={`mt-0.5 shrink-0 rounded-md border px-3 py-1.5 text-[12px] transition-colors ${
            busy || !composer.value.trim()
              ? "cursor-not-allowed opacity-40"
              : "cursor-pointer hover:opacity-80"
          }`}
          style={{
            borderColor: "var(--border)",
            color: "var(--accent)",
            background: "var(--panelSoft)",
          }}
        >
          {COMPOSER_COPY.send}
        </button>
      </div>
    </div>
  );
}
