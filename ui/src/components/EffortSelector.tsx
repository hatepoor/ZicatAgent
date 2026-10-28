import { useEffect, useMemo, useRef, useState } from "react";
import type { ModelConfig } from "../core/types";

type Props = {
  models: ModelConfig[];
  active: number;
  onClose: () => void;
  onConfirm: (value: string) => void;
};

const FALLBACK_LEVELS = ["off", "low", "medium", "high", "xhigh", "max"];

/** /effort 选择页：左右方向键移动，Enter 确认，Esc 取消。 */
export function EffortSelector({ models, active, onClose, onConfirm }: Props) {
  const model = models[active] ?? models[0];
  const levels = useMemo(() => {
    const options = model?.reasoning_effort_options;
    return options && options.length ? options : FALLBACK_LEVELS;
  }, [model]);
  const current = model?.reasoning_effort || "";
  const initial = levels.indexOf(current);
  const [index, setIndex] = useState(
    initial >= 0 ? initial : Math.max(0, levels.indexOf("medium")),
  );
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    rootRef.current?.focus();
  }, []);

  useEffect(() => {
    const next = levels.indexOf(current);
    setIndex(next >= 0 ? next : Math.max(0, levels.indexOf("medium")));
  }, [levels, current]);

  useEffect(() => {
    if (!model) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        event.stopPropagation();
        setIndex((prev) => Math.max(0, prev - 1));
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        event.stopPropagation();
        setIndex((prev) => Math.min(levels.length - 1, prev + 1));
      } else if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        onConfirm(levels[index]);
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [index, levels, model, onClose, onConfirm]);

  if (!model) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: "rgba(0,0,0,.62)" }}
        onMouseDown={onClose}
      >
        <div
          className="rounded-lg border px-6 py-4 text-[12px]"
          style={{ borderColor: "var(--border)", background: "var(--panel)", color: "var(--dim)" }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          正在读取模型配置…
        </div>
      </div>
    );
  }

  const marker = levels.length > 1 ? ((index + 0.5) / levels.length) * 100 : 50;
  const looksDeepSeek = /deepseek/i.test(`${model.model || ""} ${model.name || ""}`);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,.65)" }}
      onMouseDown={onClose}
    >
      <div
        ref={rootRef}
        tabIndex={-1}
        className="w-full max-w-4xl rounded-lg border px-8 py-7 shadow-2xl outline-none"
        style={{ borderColor: "var(--border)", background: "var(--panel)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center gap-3 text-[11px]" style={{ color: "var(--dim)" }}>
          <span className="font-bold" style={{ color: "var(--accent)" }}>思考强度</span>
          <span className="truncate">{model.name || model.model || "当前模型"}</span>
          <span style={{ color: "var(--faint)" }}>· {model.provider || "openai"}</span>
          <div className="flex-1" />
          <span>当前: {current || "未设置"}</span>
        </div>

        {model.provider !== "deepseek" && looksDeepSeek && (
          <div
            className="mt-4 rounded border px-3 py-2 text-[11px]"
            style={{ borderColor: "var(--yellow)", color: "var(--yellow)", background: "var(--panelSoft)" }}
          >
            当前接口是 OpenAI Chat Completions。到 /mode 把接口改为 DeepSeek，才能使用 off / xhigh / max 档位。
          </div>
        )}

        <div
          className="mt-10 flex items-center justify-between text-[13px] font-bold"
          style={{ color: "var(--fg)" }}
        >
          <span>Faster</span>
          <span>Smarter</span>
        </div>

        <div className="relative mt-4 pb-2">
          <div
            className="absolute left-0 right-0 top-[6px] h-px"
            style={{ background: "var(--faint)" }}
          />
          <div
            className="relative grid"
            style={{ gridTemplateColumns: `repeat(${levels.length}, minmax(0, 1fr))` }}
          >
            {levels.map((level, i) => {
              const selected = i === index;
              return (
                <button
                  key={level}
                  type="button"
                  onClick={() => setIndex(i)}
                  className="flex cursor-pointer flex-col items-center gap-2 border-none bg-transparent"
                >
                  <span
                    className="h-3 w-px"
                    style={{ background: selected ? "var(--accent2)" : "var(--faint)" }}
                  />
                  <span
                    className="text-[12px]"
                    style={{
                      color: selected ? "var(--accent2)" : "var(--dim)",
                      fontWeight: selected ? 700 : 400,
                    }}
                  >
                    {level}
                  </span>
                </button>
              );
            })}
          </div>
          <div
            className="pointer-events-none absolute -top-1"
            style={{ left: `calc(${marker}% - 5px)` }}
          >
            <span
              style={{
                display: "inline-block",
                width: 0,
                height: 0,
                borderLeft: "5px solid transparent",
                borderRight: "5px solid transparent",
                borderBottom: "6px solid var(--accent2)",
              }}
            />
          </div>
        </div>

        <div className="mt-8 flex items-center justify-between text-[11px]" style={{ color: "var(--faint)" }}>
          <span>← → 选择 · Enter 确认 · Esc 取消</span>
          <button
            type="button"
            onClick={() => onConfirm(levels[index])}
            className="cursor-pointer rounded border px-3 py-1.5 text-[11px] hover:opacity-80"
            style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--panelSoft)" }}
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}
