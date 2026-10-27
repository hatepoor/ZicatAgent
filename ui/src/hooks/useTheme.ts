import { useCallback, useMemo, useState } from "react";
import { THEMES } from "../themes";
import type { ThemeState } from "../core/types";

export function useTheme(): ThemeState {
  const [themeIdx, setThemeIdx] = useState(0);
  const [menu, setMenu] = useState(false);
  const theme = THEMES[themeIdx];
  const next = useCallback(
    () => setThemeIdx((prev) => (prev + 1) % THEMES.length),
    [],
  );
  return useMemo(
    () => ({ theme, options: THEMES, themeIdx, setThemeIdx, menu, setMenu, next }),
    [theme, themeIdx, menu, next],
  );
}
