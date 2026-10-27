import type { ReactNode } from "react";

export function StatusCell({
  children,
  bg,
  fg,
  bold,
}: {
  children: ReactNode;
  bg?: string;
  fg?: string;
  bold?: boolean;
}) {
  return (
    <div
      className={`border-r px-3 py-1.5 ${bold ? "font-bold tracking-wider" : ""}`}
      style={{
        borderColor: "var(--border)",
        background: bg ?? "transparent",
        color: fg ?? "var(--dim)",
      }}
    >
      {children}
    </div>
  );
}
