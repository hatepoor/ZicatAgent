import { useEffect, useRef, useState } from "react";
import type { ModelConfig } from "../core/types";

type ModelSettingsProps = {
  models: ModelConfig[];
  active: number;
  onClose: () => void;
  onSave: (index: number, config: Record<string, string>) => void;
  onSwitch: (index: number) => void;
  onReveal: () => void;
};

const blankModel = (): ModelConfig => ({
  index: -1,
  name: "",
  model: "",
  base_url: "",
  api_key: "",
  context_window: "",
  max_tokens: "",
  temperature: "",
  provider: "openai",
  reasoning_effort: "",
});

const maskKey = (value: string) => {
  const text = value || "";
  return text.length > 8 ? `${text.slice(0, 4)}…${text.slice(-4)}` : "*".repeat(text.length);
};

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  hint?: string;
}) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px]" style={{ color: "var(--dim)" }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        className="w-full rounded border bg-transparent px-2 py-1.5 text-[12px] outline-none"
        style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
      />
      {hint && <span className="mt-1 block text-[10px]" style={{ color: "var(--faint)" }}>{hint}</span>}
    </label>
  );
}

export function ModelSettings({ models, active, onClose, onSave, onSwitch, onReveal }: ModelSettingsProps) {
  const [selected, setSelected] = useState(models.length ? Math.max(0, Math.min(active, models.length - 1)) : 0);
  const [draft, setDraft] = useState<ModelConfig>(() => models[selected] ?? blankModel());
  const [keyTouched, setKeyTouched] = useState(false);
  const [keyValue, setKeyValue] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  const isNew = selected >= models.length;

  useEffect(() => {
    const current = models[selected];
    if (current) {
      setDraft({ ...current });
      setKeyTouched(false);
      setKeyValue("");
    } else {
      setDraft(blankModel());
      setKeyTouched(true);
      setKeyValue("");
    }
    setError("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, models]);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const update = (field: keyof ModelConfig, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  };

  const save = () => {
    if (!draft.base_url.trim()) {
      setError("Base URL 不能为空");
      return;
    }
    if (!draft.model.trim()) {
      setError("模型名不能为空");
      return;
    }
    const config: Record<string, string> = {
      name: draft.name || draft.model,
      model: draft.model,
      base_url: draft.base_url,
      provider: draft.provider || "openai",
      context_window: String(draft.context_window ?? ""),
      max_tokens: String(draft.max_tokens ?? ""),
      temperature: String(draft.temperature ?? ""),
    };
    if (keyTouched && keyValue.trim()) config.api_key = keyValue.trim();
    setError("");
    onSave(selected, config);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,.55)" }}
      onMouseDown={onClose}
    >
      <div
        className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border shadow-2xl"
        style={{ borderColor: "var(--border)", background: "var(--panel)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--accent)" }}>◈ 模型配置</span>
          <span className="text-[11px]" style={{ color: "var(--faint)" }}>保存到 .env，下个任务生效</span>
          <div className="flex-1" />
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded border px-2 py-0.5 text-[12px] hover:opacity-80"
            style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
            title="关闭（Esc）"
          >
            ✕
          </button>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="w-52 shrink-0 overflow-y-auto border-r p-2" style={{ borderColor: "var(--border)" }}>
            {models.map((m, i) => (
              <button
                key={`${m.index}-${i}`}
                type="button"
                onClick={() => setSelected(i)}
                className="mb-1 w-full cursor-pointer rounded px-2 py-1.5 text-left text-[11px] hover:opacity-80"
                style={{
                  background: selected === i ? "var(--selection)" : "transparent",
                  color: "var(--fg)",
                }}
              >
                <div className="truncate">
                  <span style={{ color: "var(--cyan)" }}>{m.name || m.model || `模型 ${i + 1}`}</span>
                  {i === active && <span style={{ color: "var(--green)" }}> ← 当前</span>}
                </div>
                <div className="truncate" style={{ color: "var(--faint)" }}>{m.model}</div>
              </button>
            ))}
            <button
              type="button"
              onClick={() => setSelected(models.length)}
              className="mt-1 w-full cursor-pointer rounded border border-dashed px-2 py-1.5 text-[11px] hover:opacity-80"
              style={{ borderColor: "var(--border)", color: "var(--accent)" }}
            >
              ＋ 新增模型
            </button>
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto p-4">
            <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
              <div>
                <Field label="名称" value={String(draft.name ?? "")} onChange={(v) => update("name", v)} placeholder="deepseek-v4.1-flash" />
              </div>
              <div>
                <Field label="模型名" value={String(draft.model ?? "")} onChange={(v) => update("model", v)} placeholder="deepseek/deepseek-v4.1-flash" />
              </div>
              <div>
                <label className="mb-3 block">
                  <span className="mb-1 block text-[11px]" style={{ color: "var(--dim)" }}>接口类型</span>
                  <select
                    value={draft.provider || "openai"}
                    onChange={(e) => update("provider", e.target.value)}
                    className="w-full rounded border bg-transparent px-2 py-1.5 text-[12px] outline-none"
                    style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
                  >
                    <option value="openai">OpenAI Chat Completions（通用）</option>
                    <option value="deepseek">DeepSeek（reasoning 回传）</option>
                  </select>
                  <span className="mt-1 block text-[10px]" style={{ color: "var(--faint)" }}>
                    DeepSeek 模型走工具调用时请选 DeepSeek 接口
                  </span>
                </label>
              </div>
              <div className="md:col-span-2">
                <Field label="Base URL" value={String(draft.base_url ?? "")} onChange={(v) => update("base_url", v)} placeholder="https://api.example.com/v1" />
              </div>
              <div className="md:col-span-2">
                <label className="mb-3 block">
                  <span className="mb-1 block text-[11px]" style={{ color: "var(--dim)" }}>API Key</span>
                  <div className="flex gap-2">
                    <input
                      ref={nameRef}
                      type={showKey ? "text" : "password"}
                      value={keyTouched ? keyValue : ""}
                      onChange={(e) => { setKeyTouched(true); setKeyValue(e.target.value); }}
                      placeholder={isNew ? "输入 API Key" : `已设置 ${showKey ? (draft.api_key || "—") : (maskKey(String(draft.api_key || "")) || "—")}，留空不修改`}
                      spellCheck={false}
                      autoComplete="off"
                      className="w-full rounded border bg-transparent px-2 py-1.5 text-[12px] outline-none"
                      style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((p) => !p)}
                      className="shrink-0 cursor-pointer rounded border px-2 text-[11px] hover:opacity-80"
                      style={{ borderColor: "var(--border)", color: "var(--dim)", background: "var(--panelSoft)" }}
                    >
                      {showKey ? "隐藏" : "显示"}
                    </button>
                    <button
                      type="button"
                      onClick={onReveal}
                      className="shrink-0 cursor-pointer rounded border px-2 text-[11px] hover:opacity-80"
                      style={{ borderColor: "var(--border)", color: "var(--accent)", background: "var(--panelSoft)" }}
                      title="从 .env 读取原始 Key（仅本地）"
                    >
                      读取原值
                    </button>
                  </div>
                  <span className="mt-1 block text-[10px]" style={{ color: "var(--faint)" }}>
                    留空表示保持原 Key；修改后保存会写入 .env
                  </span>
                </label>
              </div>
              <div>
                <Field label="上下文窗口（tokens）" value={String(draft.context_window ?? "")} onChange={(v) => update("context_window", v)} placeholder="128000" />
              </div>
              <div>
                <Field label="最大输出（tokens）" value={String(draft.max_tokens ?? "")} onChange={(v) => update("max_tokens", v)} placeholder="8192" />
              </div>
              <div>
                <Field label="temperature" value={String(draft.temperature ?? "")} onChange={(v) => update("temperature", v)} placeholder="0.7" />
              </div>
              <div className="md:col-span-2 text-[10px]" style={{ color: "var(--faint)" }}>
                思考强度：{draft.reasoning_effort || "未设置"}（保存后可用 /effort 调整）
              </div>
            </div>

            {error && <div className="mb-2 text-[11px]" style={{ color: "var(--red)" }}>{error}</div>}

            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={save}
                className="cursor-pointer rounded border px-3 py-1.5 text-[12px] hover:opacity-80"
                style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--panelSoft)" }}
              >
                保存配置
              </button>
              {!isNew && (
                <button
                  type="button"
                  onClick={() => onSwitch(selected)}
                  disabled={selected === active}
                  className={`rounded border px-3 py-1.5 text-[12px] ${selected === active ? "cursor-not-allowed opacity-40" : "cursor-pointer hover:opacity-80"}`}
                  style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
                >
                  {selected === active ? "当前使用中" : "设为当前模型"}
                </button>
              )}
              <span className="text-[10px]" style={{ color: "var(--faint)" }}>
                Esc 关闭 · 点击遮罩关闭
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type WorkspaceSettingsProps = {
  current: string;
  root: string;
  defaultPath: string;
  onClose: () => void;
  onSave: (path: string) => void;
};

export function WorkspaceSettings({ current, root, defaultPath, onClose, onSave }: WorkspaceSettingsProps) {
  const [path, setPath] = useState(current || defaultPath);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,.55)" }}
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-lg border shadow-2xl"
        style={{ borderColor: "var(--border)", background: "var(--panel)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--accent)" }}>◈ 工作空间</span>
          <span className="text-[11px]" style={{ color: "var(--faint)" }}>不存在会自动创建</span>
          <div className="flex-1" />
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded border px-2 py-0.5 text-[12px] hover:opacity-80"
            style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
            title="关闭（Esc）"
          >
            ✕
          </button>
        </div>

        <div className="p-4">
          <label className="mb-2 block">
            <span className="mb-1 block text-[11px]" style={{ color: "var(--dim)" }}>工作目录</span>
            <input
              ref={inputRef}
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  onSave(path.trim() || defaultPath);
                }
              }}
              spellCheck={false}
              autoComplete="off"
              className="w-full rounded border bg-transparent px-2 py-1.5 text-[12px] outline-none"
              style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
              placeholder={defaultPath}
            />
          </label>
          <div className="mb-3 text-[10px]" style={{ color: "var(--faint)" }}>
            <div>当前：{current || "—"}</div>
            <div>根目录：{root || "—"}</div>
            <div>默认：{defaultPath || "当前目录/temp"}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onSave(path.trim() || defaultPath)}
              className="cursor-pointer rounded border px-3 py-1.5 text-[12px] hover:opacity-80"
              style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--panelSoft)" }}
            >
              切换工作空间
            </button>
            <button
              type="button"
              onClick={() => setPath(defaultPath)}
              className="cursor-pointer rounded border px-3 py-1.5 text-[12px] hover:opacity-80"
              style={{ borderColor: "var(--border)", color: "var(--dim)", background: "var(--panelSoft)" }}
            >
              使用默认
            </button>
            <span className="text-[10px]" style={{ color: "var(--faint)" }}>Esc 关闭</span>
          </div>
        </div>
      </div>
    </div>
  );
}
