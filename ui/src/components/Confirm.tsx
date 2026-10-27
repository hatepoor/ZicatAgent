import { useEffect, useRef } from "react";

type ConfirmDialogProps = {
  title: string;
  message: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

/** 危险操作确认框：默认焦点在“取消”，Esc/遮罩关闭。 */
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = "确认删除",
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,.62)" }}
      onMouseDown={onCancel}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border shadow-2xl"
        style={{ borderColor: "var(--red)", background: "var(--panel)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--red)" }}>⚠ {title}</span>
        </div>
        <div
          className="max-h-[55vh] overflow-y-auto px-4 py-3 text-[12px] leading-6 whitespace-pre-wrap"
          style={{ color: "var(--fg)" }}
        >
          {message}
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="cursor-pointer rounded border px-3 py-1.5 text-[12px] hover:opacity-80"
            style={{ borderColor: "var(--border)", color: "var(--fg)", background: "var(--panelSoft)" }}
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="cursor-pointer rounded border px-3 py-1.5 text-[12px] font-bold hover:opacity-80"
            style={{ borderColor: "var(--red)", color: "var(--red)", background: "var(--panelSoft)" }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
