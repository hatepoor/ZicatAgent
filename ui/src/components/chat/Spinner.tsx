import { useEffect, useState } from "react";

const FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

export function Spinner({ color = "var(--accent)" }: { color?: string }) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setFrame((prev) => (prev + 1) % FRAMES.length),
      80,
    );
    return () => clearInterval(timer);
  }, []);
  return <span style={{ color }}>{FRAMES[frame]}</span>;
}
