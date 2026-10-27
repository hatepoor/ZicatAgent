import type { ReactNode } from "react";

export function PanelSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-5">
      <div
        className="mb-2 text-[11px] font-bold tracking-widest"
        style={{ color: "var(--accent)" }}
      >
        ── {title} ──
      </div>
      {children}
    </div>
  );
}

export function PanelRow({ k, v, vc }: { k: string; v: string; vc?: string }) {
  return (
    <div className="mb-1 flex justify-between text-[12px]">
      <span style={{ color: "var(--dim)" }}>{k}</span>
      <span style={{ color: vc ?? "var(--fg)" }}>{v}</span>
    </div>
  );
}
